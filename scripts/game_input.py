"""Read only bounded, hash-pinned game files; never execute the original game."""

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import zipfile


MAX_MEMBER_BYTES = 32 * 1024 * 1024


def verified_data(stream, name, expected, max_bytes):
    data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("Game member exceeds byte bound: " + name)
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("Unsupported PC 1.4.0.0 member identity: " + name)
    return data


def archive_inventory(package):
    entries = package.infolist()
    if len(entries) > 10000:
        raise ValueError("Game archive exceeds entry bound")
    files = {}
    names = set()
    for entry in entries:
        name = entry.filename
        path = PurePosixPath(name)
        if not name or path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name or str(path) != name.rstrip("/"):
            raise ValueError("Unsafe archive member: " + name)
        if name.rstrip("/") in names:
            raise ValueError("Duplicate archive member: " + name)
        names.add(name.rstrip("/"))
        kind = stat.S_IFMT(entry.external_attr >> 16)
        if kind not in (0, stat.S_IFREG, stat.S_IFDIR) or (kind == stat.S_IFDIR) != entry.is_dir() and kind:
            raise ValueError("Archive member must be a regular file or directory: " + name)
        if not entry.is_dir():
            files[name] = entry
    roots = [name.removesuffix("Celeste.exe") for name in files if PurePosixPath(name).name == "Celeste.exe"]
    if len(roots) != 1:
        raise ValueError("Game archive must contain exactly one Celeste.exe root")
    return files, roots[0]


def directory_member(source, name):
    path = source
    for part in PurePosixPath(name).parts:
        path /= part
        if path.is_symlink():
            raise ValueError("Game member must not use a symlink: " + name)
    if not path.is_file():
        raise ValueError("Missing required game file: " + name)
    return path


@contextmanager
def game_source(source, pins, max_bytes=MAX_MEMBER_BYTES):
    source = Path(source)
    if source.is_symlink():
        raise ValueError("Game source must not be a symlink")
    if source.is_dir():
        yield {name: directory_member(source, name) for name in pins}, None
    else:
        with zipfile.ZipFile(source) as package:
            files, prefix = archive_inventory(package)
            selected = {}
            for name in pins:
                if prefix + name not in files:
                    raise ValueError("Missing required game file: " + name)
                entry = files[prefix + name]
                if entry.file_size > max_bytes:
                    raise ValueError("Game member exceeds byte bound: " + name)
                selected[name] = entry
            yield selected, package


def read_members(source, pins, max_bytes=MAX_MEMBER_BYTES):
    for name in pins:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or str(path) != name or "\\" in name or ":" in name:
            raise ValueError("Unsafe required member name: " + name)
    result = {}
    with game_source(source, pins, max_bytes) as (files, package):
        for name, expected in pins.items():
            entry = files[name]
            if package is None and entry.stat().st_size > max_bytes:
                raise ValueError("Game member exceeds byte bound: " + name)
            with package.open(entry) if package else entry.open("rb") as stream:
                result[name] = verified_data(stream, name, expected, max_bytes)
    return result


def normalize_game(source, output, pins):
    members = read_members(source, pins)
    output.mkdir(parents=True, exist_ok=False)
    archive_path = output / "game.zip"
    with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_STORED) as package:
        for name, data in sorted(members.items()):
            package.writestr(zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), data)
            if "/" not in name:
                path = output / "inputs" / name
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(data)
    receipt = {"source": str(Path(source).resolve()), "members": {
        name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in members.items()}}
    (output / "input-provenance.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return archive_path


def archive_identity(path):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest,
            "hash_source": "Archive hashed locally; required member identities verified independently"}
