#!/usr/bin/env python3
"""Install only pinned preparation tools locally; never download game files."""

import argparse
import hashlib
from pathlib import Path, PurePosixPath
import stat
import subprocess
import tempfile
import urllib.request
import zipfile

import bootstrap_native_oracle
from check_native_oracle import ROOT, oracle_environment
from native_oracle_sdk import sdk_path, VERSION

ILSPY_VERSION = "9.1.0.7988"
PACKAGE_BYTES = 4183395
PACKAGE_SHA = "2b5058f5ccc164c33b7aabf1a5eb0cf3d3a6af6c145aaf58efd3ed891443af7c"
TOOL_DIRECTORY = ROOT / f".audit/ilspy/tools/ilspycmd-{ILSPY_VERSION}"
PACKAGE_PATH = TOOL_DIRECTORY.parent / f"ilspycmd.{ILSPY_VERSION}.nupkg"
PACKAGE_URL = f"https://api.nuget.org/v3-flatcontainer/ilspycmd/{ILSPY_VERSION}/{PACKAGE_PATH.name}"


def install_ilspy(package_path, destination):
    data = package_path.read_bytes() if package_path.stat().st_size == PACKAGE_BYTES else b""
    if hashlib.sha256(data).hexdigest() != PACKAGE_SHA:
        raise ValueError("ILSpy package identity mismatch: " + str(package_path))
    with zipfile.ZipFile(package_path) as package:
        files = {}
        for entry in package.infolist():
            name = entry.filename
            path = PurePosixPath(name)
            if (not name or path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name or
                    str(path) != name.rstrip("/") or name in files or
                    stat.S_IFMT(entry.external_attr >> 16) not in (0, stat.S_IFDIR, stat.S_IFREG)):
                raise ValueError("Unsafe ILSpy package member: " + name)
            if entry.is_dir():
                continue
            if entry.file_size > 32 * 1024 * 1024:
                raise ValueError("ILSpy member exceeds byte bound")
            files[name] = package.read(entry)
    if destination.exists() or destination.is_symlink():
        actual = {path.relative_to(destination).as_posix() for path in destination.rglob("*") if path.is_file()}
        if destination.is_symlink() or actual != set(files):
            raise ValueError("Existing ILSpy inventory changed; preserve it and use a fresh checkout")
        for name, data in files.items():
            path = destination / name
            if any(parent.is_symlink() for parent in (path, *path.parents)) or path.read_bytes() != data:
                raise ValueError("Existing ILSpy tool changed: " + str(path))
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ilspy-install-", dir=destination.parent) as temporary:
        staging = Path(temporary) / "tool"
        staging.mkdir()
        for name, data in files.items():
            path = staging / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        staging.rename(destination)


def ensure_tools(offline=False):
    sdk = sdk_path(ROOT)
    if not sdk.is_file():
        if offline:
            raise RuntimeError("Pinned .NET SDK missing; rerun without --offline to download preparation tools")
        bootstrap_native_oracle.main()
    version = subprocess.check_output([sdk, "--version"], env=oracle_environment(sdk), text=True).strip()
    if version != VERSION:
        raise RuntimeError("Pinned .NET SDK version changed: " + version)
    if not PACKAGE_PATH.exists():
        if offline:
            raise RuntimeError("Pinned ILSpy package missing; rerun without --offline to download preparation tools")
        PACKAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=PACKAGE_PATH.parent, suffix=".part", delete=False) as stream:
                temporary = Path(stream.name)
                with urllib.request.urlopen(PACKAGE_URL, timeout=120) as response:
                    data = response.read(PACKAGE_BYTES + 1)
                if len(data) != PACKAGE_BYTES or hashlib.sha256(data).hexdigest() != PACKAGE_SHA:
                    raise ValueError("Downloaded ILSpy package identity mismatch")
                stream.write(data)
            temporary.replace(PACKAGE_PATH)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    install_ilspy(PACKAGE_PATH, TOOL_DIRECTORY)
    return sdk


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Use already verified local tools; never download")
    args = parser.parse_args()
    print(ensure_tools(args.offline))
