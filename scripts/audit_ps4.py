# /// script
# requires-python = ">=3.12"
# dependencies = ["dnfile==0.18.0", "dncil==1.0.2", "pefile==2024.8.26"]
# ///

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import zipfile

from audit_game import IL_METHODS, inspect_managed, inspect_texture_header


PS4_METHODS = {
    **IL_METHODS,
    "Celeste.Celeste": {".ctor", "Main", "LoadContent"},
    "Celeste.GameLoader": {"LoadThread"},
    "Celeste.GFX": {
        "LoadGame", "UnloadGame", "LoadGui", "UnloadGui", "LoadOverworld",
        "UnloadOverworld", "LoadMountain", "UnloadMountain", "LoadOther",
        "UnloadOther", "LoadPortraits", "UnloadPortraits", "LoadData", "LoadFx",
    },
    "Celeste.Audio": {"Init", "GetEventDescription"},
    "Celeste.UserIO": {"Serialize", "Deserialize", "GetHandle"},
    "Monocle.Engine": {"get_ContentDirectory"},
    "Microsoft.Xna.Framework.Graphics.Texture2D": {"PlatformConstruct", "PlatformSetData"},
    "Microsoft.Xna.Framework.Graphics.Shader": {".ctor"},
}


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inspect_sfo(path):
    data = path.read_bytes()
    magic, _, keys, values, count = struct.unpack_from("<5I", data)
    if magic != 0x46535000 or 20 + count * 16 > keys or not keys < values <= len(data):
        raise ValueError(f"Invalid SFO header: {path}")
    result = {}
    for index in range(count):
        key_offset, kind, size, capacity, value_offset = struct.unpack_from(
            "<HHIII", data, 20 + index * 16
        )
        if keys + key_offset >= values or size > capacity or values + value_offset + capacity > len(data):
            raise ValueError(f"Invalid SFO entry: {index}")
        key = data[keys + key_offset:values].split(b"\0", 1)[0].decode()
        value = data[values + value_offset:values + value_offset + size]
        if kind == 0x404:
            value = struct.unpack("<I", value)[0]
        elif kind == 0x204:
            value = value.rstrip(b"\0").decode()
        else:
            value = value.hex()
        if key in result:
            raise ValueError(f"Duplicate SFO key: {key}")
        result[key] = value
    return result


def inspect_self(path):
    data = path.read_bytes()
    if data[:4] != b"\x4f\x15\x3d\x1d":
        raise ValueError(f"Invalid SELF magic: {path}")
    entry_count = struct.unpack_from("<H", data, 0x18)[0]
    elf_offset = 0x20 + entry_count * 0x20
    if data[elf_offset:elf_offset + 6] != b"\x7fELF\x02\x01":
        raise ValueError(f"Expected embedded ELF64 little endian header: {path}")
    entries = [struct.unpack_from("<4Q", data, 0x20 + i * 0x20) for i in range(entry_count)]
    if any(offset + size > len(data) for _, offset, size, _ in entries):
        raise ValueError(f"SELF segment outside file: {path}")
    markers = []
    patterns = (b"/app0/Celeste.exe", b"mini-orbis.c", b"aot-runtime.c", b"Mono JIT compiler version")
    for match in re.finditer(rb"[ -~]{6,}", data):
        if any(pattern in match.group() for pattern in patterns):
            markers.append({"file_offset": hex(match.start()), "text": match.group().decode()})
    return {
        "path": path.name,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "embedded_elf_offset": hex(elf_offset),
        "elf_machine": struct.unpack_from("<H", data, elf_offset + 18)[0],
        "elf_section_count": struct.unpack_from("<H", data, elf_offset + 60)[0],
        "encrypted_segment_count": sum(bool(flags & 2) for flags, *_ in entries),
        "runtime_markers": markers,
    }


def inspect_fsb_headers(data):
    result = []
    for match in re.finditer(b"FSB5", data):
        offset = match.start()
        if offset + 0x3c > len(data):
            continue
        version, samples, headers, names, payload, mode = struct.unpack_from("<6I", data, offset + 4)
        if version not in (0, 1) or not 0 < samples <= headers // 8:
            continue
        header_size = 0x3c if version == 1 else 0x40
        if offset + header_size + headers + names + payload > len(data):
            continue
        result.append({
            "offset": hex(offset), "version": version, "samples": samples,
            "mode": mode, "codec": {13: "ATRAC9", 15: "Vorbis"}.get(mode, "unclassified"),
            "sample_data_bytes": payload,
        })
    return result


def compare_content(root, archive):
    ps4 = {p.relative_to(root).as_posix(): p for p in (root / "Content").rglob("*") if p.is_file()}
    pc = {i.filename: i for i in archive.infolist() if i.filename.startswith("Content/") and not i.is_dir()}
    if len(pc) != sum(i.filename.startswith("Content/") and not i.is_dir() for i in archive.infolist()):
        raise ValueError("Duplicate PC content paths")
    identical = []
    different = []
    for name in sorted(ps4.keys() & pc.keys()):
        with archive.open(name) as stream:
            pc_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        (identical if file_hash(ps4[name]) == pc_hash else different).append(name)
    textures = []
    metadata_versions = Counter()
    effects = []
    banks = []
    for name, path in sorted(ps4.items()):
        with path.open("rb") as stream:
            header = stream.read(16)
        if path.suffix == ".data":
            textures.append(inspect_texture_header(name, path.stat().st_size, header))
        if path.suffix == ".meta":
            metadata_versions[str(struct.unpack_from("<I", header)[0])] += 1
        if name.startswith("Content/Effects/"):
            data = path.read_bytes()
            if data[:3] != b"XNB" or struct.unpack_from("<I", data, 6)[0] != len(data):
                raise ValueError(f"Invalid XNB header: {name}")
            effects.append({
                "path": name, "bytes": len(data), "platform_tag": chr(data[3]),
                "orbis_shader_marker_count": data.count(b"OrbShdr"),
            })
        if path.suffix == ".bank":
            pc_name = "Content/FMOD/Desktop/" + path.name
            banks.append({
                "path": name, "bytes": path.stat().st_size,
                "fsb_headers": inspect_fsb_headers(path.read_bytes()),
                "pc_counterpart_bytes": pc[pc_name].file_size if pc_name in pc else None,
                "pc_fsb_headers": inspect_fsb_headers(archive.read(pc_name)) if pc_name in pc else [],
            })
    return {
        "ps4_file_count": len(ps4), "pc_file_count": len(pc),
        "identical_sha256_count": len(identical), "different_sha256_count": len(different),
        "identical_by_extension": dict(sorted(Counter(Path(p).suffix for p in identical).items())),
        "different_paths": different,
        "ps4_only_paths": sorted(ps4.keys() - pc.keys()),
        "pc_only_paths": sorted(pc.keys() - ps4.keys()),
        "ps4_texture_count": len(textures),
        "ps4_rgba8_catalog_bytes_not_simultaneous_residency": sum(t["rgba8_bytes"] for t in textures),
        "ps4_root_atlas_textures": [t for t in textures if Path(t["path"]).parent.name == "Atlases"],
        "ps4_textures_exceeding_4096": [t for t in textures if max(t["width"], t["height"]) > 4096],
        "ps4_metadata_versions": dict(metadata_versions),
        "ps4_effects": effects, "ps4_banks": banks,
        "ps4_bank_bytes_on_disk": sum(b["bytes"] for b in banks),
    }


def main():
    parser = argparse.ArgumentParser(description="Compare an extracted Celeste PS4 package with the PC ZIP.")
    parser.add_argument("extracted", type=Path, help="pkg_pfs_tool output containing Image0/ and Sc0/.")
    parser.add_argument("pc_archive", type=Path)
    parser.add_argument("--il-output", type=Path)
    args = parser.parse_args()
    root = args.extracted / "Image0"
    sfo = args.extracted / "Sc0/param.sfo"
    for path in (root / "Celeste.exe", root / "eboot.bin", sfo, args.pc_archive):
        if not path.is_file():
            parser.error(f"Input does not exist: {path}")
    if not (root / "Content").is_dir():
        parser.error(f"Missing content directory: {root / 'Content'}")
    if args.il_output is not None and (
        args.il_output.resolve().is_relative_to(args.extracted.resolve())
        or args.il_output.resolve() == args.pc_archive.resolve()
    ):
        parser.error("IL output must not overwrite game inputs")
    assemblies = []
    il = []
    for path in sorted([*root.glob("*.exe"), *root.glob("*.dll")]):
        report, methods = inspect_managed(path.read_bytes(), path.name, PS4_METHODS)
        assemblies.append(report)
        il.extend(methods)
    native = [inspect_self(p) for p in sorted(root.rglob("*")) if p.suffix in (".prx", ".sprx") or p.name == "eboot.bin"]
    files = [p for p in root.rglob("*") if p.is_file()]
    with zipfile.ZipFile(args.pc_archive) as archive:
        content = compare_content(root, archive)
    report = {
        "ps4_extracted_path": str(args.extracted), "pc_archive_path": str(args.pc_archive),
        "package_metadata": inspect_sfo(sfo),
        "image_file_count": len(files), "image_bytes": sum(p.stat().st_size for p in files),
        "image_extensions": dict(sorted(Counter(p.suffix for p in files).items())),
        "managed_assemblies": assemblies, "native_executables": native,
        "content_comparison": content,
        "executed_on_ps4_vita_or_emulator": False,
    }
    if args.il_output is not None:
        args.il_output.parent.mkdir(parents=True, exist_ok=True)
        args.il_output.write_text("\n".join(il) + "\n", encoding="utf-8")
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
