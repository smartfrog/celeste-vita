# /// script
# requires-python = ">=3.12"
# dependencies = ["dnfile==0.18.0", "dncil==1.0.2", "pefile==2024.8.26"]
# ///

import argparse
from collections import Counter, defaultdict
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import zipfile

import dnfile
from dncil.cil.body.reader import read_method_body_from_bytes
from dncil.clr.token import StringToken, Token


MANAGED_FILES = ("Celeste.exe", "Celeste.Content.dll", "FNA.dll")
IL_METHODS = {
    "Celeste.Celeste": {".ctor", "Main"},
    "Celeste.GFX": {"Load"},
    "Celeste.GameplayBuffers": {"Create"},
    "Celeste.Audio": {"Init"},
    "Celeste.Audio/Banks": {"Load", "LoadMaster"},
    "Monocle.Atlas": {"FromAtlas", "ReadAtlasData"},
    "Monocle.VirtualContent": {"CreateTexture"},
    "Monocle.VirtualTexture": {".ctor", ".cctor", "Reload"},
}


def type_name(row):
    return ".".join(part for part in (str(row.TypeNamespace), str(row.TypeName)) if part)


def assembly_identity(row):
    return {
        "name": str(row.Name),
        "version": ".".join(str(getattr(row, field)) for field in (
            "MajorVersion", "MinorVersion", "BuildNumber", "RevisionNumber"
        )),
    }


def inspect_managed(data, name, il_methods=None):
    if il_methods is None:
        il_methods = IL_METHODS
    pe = dnfile.dnPE(data=data)
    try:
        if pe.net is None or pe.net.mdtables is None:
            raise ValueError(f"{name}: missing CLR metadata")
        tables = pe.net.mdtables
        names = {id(row): type_name(row) for row in tables.TypeDef}
        parents = {
            id(row.NestedClass.row): row.EnclosingClass.row
            for row in tables.NestedClass or []
        }

        def qualified_type(row):
            parent = parents.get(id(row))
            if parent is not None:
                return f"{qualified_type(parent)}/{row.TypeName}"
            return type_name(row)

        for row in tables.TypeDef:
            names[id(row)] = qualified_type(row)
            for member in (*row.MethodList, *row.FieldList):
                names[id(member.row)] = f"{names[id(row)]}::{member.row.Name}"

        def resolve_row(row):
            if id(row) in names:
                return names[id(row)]
            if isinstance(row, dnfile.mdtable.MemberRefRow):
                return f"{resolve_row(row.Class.row)}::{row.Name}"
            if isinstance(row, dnfile.mdtable.MethodSpecRow):
                return f"{resolve_row(row.Method.row)}<generic>"
            if isinstance(row, dnfile.mdtable.TypeRefRow):
                return type_name(row)
            if isinstance(row, dnfile.mdtable.TypeSpecRow):
                return f"TypeSpec[{row.Signature.value.hex()}]"
            raise ValueError(f"{name}: unsupported IL operand row {type(row).__name__}")

        def resolve_operand(operand):
            if isinstance(operand, StringToken):
                value = pe.net.user_strings.get(operand.rid)
                if value is None:
                    raise ValueError(f"{name}: invalid string token {operand}")
                return json.dumps(value.value, ensure_ascii=False)
            if isinstance(operand, Token):
                return resolve_row(tables.tables[operand.table].rows[operand.rid - 1])
            return "" if operand is None else str(operand)

        il = []
        game_version = None
        for row in tables.TypeDef:
            selected = il_methods.get(names[id(row)], set())
            for member in row.MethodList:
                method = member.row
                if str(method.Name) in selected and method.Rva:
                    il.append(f"\n{name}: {names[id(method)]} [RVA 0x{method.Rva:x}]")
                    body = read_method_body_from_bytes(pe.get_data(method.Rva))
                    for index, instruction in enumerate(body.instructions):
                        if (
                            names[id(method)] == "Celeste.Celeste::.ctor"
                            and str(instruction.opcode) == "newobj"
                            and resolve_operand(instruction.operand) == "System.Version::.ctor"
                        ):
                            components = []
                            for part in body.instructions[index - 4:index]:
                                opcode = str(part.opcode)
                                if opcode in ("ldc.i4", "ldc.i4.s"):
                                    components.append(part.operand)
                                elif opcode.startswith("ldc.i4.") and opcode[-1].isdigit():
                                    components.append(int(opcode[-1]))
                                else:
                                    raise ValueError(f"{name}: unsupported game version constructor")
                            if len(components) != 4:
                                raise ValueError(f"{name}: incomplete game version constructor")
                            game_version = ".".join(map(str, components))
                        il.append(
                            f"  body+0x{instruction.offset:04x}: {str(instruction.opcode):<14} "
                            f"{resolve_operand(instruction.operand)}"
                        )

        imports = Counter(str(row.ImportScope.row.Name) for row in tables.ImplMap or [])
        fmod_constants = {}
        for row in tables.Constant or []:
            field = names.get(id(row.Parent.row), "")
            if field == "FMOD.VERSION::number":
                fmod_constants[field] = f"0x{int.from_bytes(row.Value.value, 'little'):08x}"

        framework = None
        for row in tables.CustomAttribute or []:
            constructor = row.Type.row
            if not isinstance(constructor, dnfile.mdtable.MemberRefRow):
                continue
            parent = constructor.Class.row
            if not isinstance(parent, dnfile.mdtable.TypeRefRow):
                continue
            if type_name(parent) != "System.Runtime.Versioning.TargetFrameworkAttribute":
                continue
            blob = row.Value.value
            if len(blob) < 3 or blob[:2] != b"\x01\x00" or blob[2] >= 128:
                raise ValueError(f"{name}: unsupported target framework attribute encoding")
            if len(blob) < 3 + blob[2]:
                raise ValueError(f"{name}: truncated target framework attribute")
            framework = blob[3:3 + blob[2]].decode("utf-8")

        report = {
            "path": name,
            "sha256": hashlib.sha256(data).hexdigest(),
            "assembly": assembly_identity(tables.Assembly.rows[0]),
            "target_framework": framework,
            "clr_metadata_version": pe.net.metadata.struct.Version.rstrip(b"\x00").decode(),
            "clr_flags": f"0x{pe.net.struct.Flags:08x}",
            "il_only": bool(pe.net.Flags.CLR_ILONLY),
            "requires_32bit": bool(pe.net.Flags.CLR_32BITREQUIRED),
            "assembly_references": [assembly_identity(row) for row in tables.AssemblyRef or []],
            "type_count": len(tables.TypeDef.rows),
            "method_count": len(tables.MethodDef.rows) if tables.MethodDef is not None else 0,
            "cil_method_body_count": sum(
                bool(row.Rva and row.ImplFlags.miIL) for row in tables.MethodDef or []
            ),
            "game_version_from_constructor": game_version,
            "pinvoke_declarations_by_library": dict(sorted(imports.items())),
            "external_type_references": sorted(type_name(row) for row in tables.TypeRef or []),
            "fmod_constants": fmod_constants,
            "parser_warnings": pe.get_warnings(),
        }
        return report, il
    finally:
        pe.close()


def inspect_texture_header(path, file_bytes, header):
    if len(header) < 9:
        raise ValueError(f"Truncated texture header: {path}")
    width, height, alpha = struct.unpack("<iiB", header[:9])
    if width <= 0 or height <= 0 or alpha not in (0, 1):
        raise ValueError(f"Invalid texture header: {path}")
    return {
        "path": path,
        "width": width,
        "height": height,
        "has_alpha": bool(alpha),
        "rgba8_bytes": width * height * 4,
        "file_bytes": file_bytes,
    }


def inspect_content(archive):
    hashes = {}
    textures = []
    banks = []
    effects = []
    for entry in sorted(archive.infolist(), key=lambda item: item.filename):
        if entry.is_dir() or not entry.filename.startswith("Content/"):
            continue
        digest = hashlib.sha256()
        with archive.open(entry) as stream:
            header = stream.read(16)
            digest.update(header)
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        hashes[entry.filename] = digest.hexdigest()
        if entry.filename.endswith(".data"):
            textures.append(inspect_texture_header(entry.filename, entry.file_size, header))
        if entry.filename.endswith(".bank"):
            banks.append({"path": entry.filename, "bytes": entry.file_size})
        if entry.filename.startswith("Content/Effects/"):
            effects.append({"path": entry.filename, "bytes": entry.file_size})

    groups = defaultdict(lambda: {"textures": 0, "rgba8_bytes": 0})
    for texture in textures:
        group = str(Path(texture["path"]).parent)
        groups[group]["textures"] += 1
        groups[group]["rgba8_bytes"] += texture["rgba8_bytes"]
    return hashes, {
        "files": len(hashes),
        "texture_count": len(textures),
        "texture_rgba8_bytes_all_files_not_simultaneous_residency": sum(
            texture["rgba8_bytes"] for texture in textures
        ),
        "largest_textures": sorted(textures, key=lambda item: -item["rgba8_bytes"])[:20],
        "root_atlas_textures": [
            texture for texture in textures
            if str(Path(texture["path"]).parent) == "Content/Graphics/Atlases"
        ],
        "textures_exceeding_4096": [
            texture for texture in textures if max(texture["width"], texture["height"]) > 4096
        ],
        "texture_groups": dict(sorted(groups.items())),
        "startup_atlases_selected_by_gfx_load": inspect_startup_atlases(archive, textures),
        "banks": banks,
        "bank_bytes_on_disk": sum(bank["bytes"] for bank in banks),
        "effects": effects,
    }


def inspect_startup_atlases(archive, textures):
    texture_sizes = {item["path"]: item["rgba8_bytes"] for item in textures}
    result = {}
    for atlas, packed in (
        ("Gameplay", True), ("Opening", False), ("Gui", True),
        ("Misc", False), ("Portraits", False)
    ):
        path = Path("Content/Graphics/Atlases") / f"{atlas}.meta"
        stream = io.BytesIO(archive.read(str(path)))

        def read_exact(size):
            value = stream.read(size)
            if len(value) != size:
                raise ValueError(f"Truncated atlas metadata: {path}")
            return value

        def read_string():
            size = 0
            for shift in range(0, 35, 7):
                byte = read_exact(1)[0]
                size |= (byte & 0x7f) << shift
                if byte < 128:
                    return read_exact(size).decode("utf-8").replace("\\", "/")
            raise ValueError(f"Invalid string length in atlas metadata: {path}")

        def read_count():
            count = struct.unpack("<h", read_exact(2))[0]
            if count < 0:
                raise ValueError(f"Negative count in atlas metadata: {path}")
            return count

        version = struct.unpack("<i", read_exact(4))[0]
        if version != 5:
            raise ValueError(f"Unsupported atlas metadata version {version}: {path}")
        read_string()
        read_exact(4)
        sources = []
        for _ in range(read_count()):
            sheet = path.parent / read_string()
            if packed:
                sources.append(f"{sheet}.data")
            for _ in range(read_count()):
                sprite = read_string()
                read_exact(16)
                if not packed:
                    sources.append(str(sheet / f"{sprite}.data"))
        if stream.read(1):
            stream.seek(-1, io.SEEK_CUR)
            if read_string() != "LINKS":
                raise ValueError(f"Unknown atlas metadata trailer: {path}")
            for _ in range(read_count()):
                read_string()
                read_string()
            if stream.read(1):
                raise ValueError(f"Unexpected data after atlas links: {path}")
        result[atlas] = {
            "source_texture_count": len(sources),
            "rgba8_bytes": sum(texture_sizes[source] for source in sources),
        }
    return result


def inspect_archive(path, include_metadata):
    with zipfile.ZipFile(path) as archive:
        filenames = [entry.filename for entry in archive.infolist()]
        if len(set(filenames)) != len(filenames):
            raise ValueError(f"Duplicate archive entries: {path}")
        managed_data = {name: archive.read(name) for name in MANAGED_FILES}
        managed_reports, il = [], []
        if include_metadata:
            for name, data in managed_data.items():
                report, methods = inspect_managed(data, name)
                managed_reports.append(report)
                il.extend(methods)
        hashes, content = inspect_content(archive)
        report = {
            "path": str(path),
            "archive_bytes": path.stat().st_size,
            "expanded_bytes": sum(entry.file_size for entry in archive.infolist()),
            "entry_count_including_directories": len(filenames),
            "managed_file_sha256": {
                name: hashlib.sha256(data).hexdigest() for name, data in managed_data.items()
            },
        }
        return report, managed_reports, content, hashes, il


def main():
    parser = argparse.ArgumentParser(description="Audit Celeste PC archives without extracting them.")
    parser.add_argument("archives", nargs=2, type=Path, metavar=("LINUX_ZIP", "WINDOWS_ZIP"))
    parser.add_argument("--il-output", type=Path, help="Write selected IL methods for local inspection.")
    args = parser.parse_args()
    for path in args.archives:
        if not path.is_file():
            parser.error(f"Archive does not exist: {path}")
    if args.il_output is not None and args.il_output.resolve() in {
        path.resolve() for path in args.archives
    }:
        parser.error("IL output must not overwrite an input archive")
    left, managed, content, left_hashes, il = inspect_archive(args.archives[0], True)
    right, _, _, right_hashes, _ = inspect_archive(args.archives[1], False)
    report = {
        "archives": [left, right],
        "comparison": {
            "managed_files_identical_sha256": left["managed_file_sha256"] == right["managed_file_sha256"],
            "all_content_identical_sha256": left_hashes == right_hashes,
            "content_file_count": len(left_hashes),
            "different_content_paths": sorted(
                name for name in left_hashes.keys() | right_hashes.keys()
                if left_hashes.get(name) != right_hashes.get(name)
            ),
        },
        "managed_assemblies_from_first_archive": managed,
        "content_from_first_archive": content,
    }
    if args.il_output is not None:
        args.il_output.parent.mkdir(parents=True, exist_ok=True)
        args.il_output.write_text("\n".join(il) + "\n", encoding="utf-8")
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
