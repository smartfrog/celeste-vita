#!/usr/bin/env python3
"""Install the pinned, hash-verified private reference SDK without a global install."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / ".audit/native-oracle/tools"
METADATA = "https://builds.dotnet.microsoft.com/dotnet/release-metadata/8.0/releases.json"
VERSION = "8.0.425"


def main():
    TOOLS.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(METADATA, timeout=120) as response:
        metadata = response.read()
    (TOOLS / "releases.json").write_bytes(metadata)
    sdk = next(
        sdk
        for release in json.loads(metadata)["releases"]
        for sdk in release["sdks"]
        if sdk["version"] == VERSION
    )
    if sdk["runtime-version"] != "8.0.31":
        raise RuntimeError("Unexpected SDK/runtime pairing")
    artifact = next(file for file in sdk["files"] if file["rid"] == "linux-arm64")
    archive = TOOLS / f"dotnet-sdk-{VERSION}-linux-arm64.tar.gz"
    download = archive.with_suffix(".part")
    if not archive.exists():
        with urllib.request.urlopen(artifact["url"], timeout=120) as response:
            with download.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
    candidate = archive if archive.exists() else download
    with candidate.open("rb") as package:
        digest = hashlib.file_digest(package, "sha512").hexdigest()
    if digest.lower() != artifact["hash"].lower():
        raise RuntimeError(f"SDK SHA512 mismatch: {candidate}")
    if candidate == download:
        download.replace(archive)
    directory = TOOLS / f"dotnet-{VERSION}"
    directory.mkdir(exist_ok=True)
    with tarfile.open(archive) as package:
        package.extractall(directory, filter="data")
    environment = os.environ | {
        "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
        "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
        "DOTNET_CLI_HOME": str(TOOLS / "cli"),
        "NUGET_PACKAGES": str(TOOLS / "packages"),
    }
    version = subprocess.check_output([directory / "dotnet", "--version"], env=environment, text=True).strip()
    if version != VERSION:
        raise RuntimeError(f"Unexpected installed SDK: {version}")
    receipt = {"metadata": METADATA, "version": version, "runtime": sdk["runtime-version"],
               "artifact": artifact, "bytes": archive.stat().st_size, "sha512": digest}
    (TOOLS / "sdk-verification.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
