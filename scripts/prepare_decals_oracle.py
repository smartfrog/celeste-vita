#!/usr/bin/env python3
"""Compile the narrow unchanged Decal source oracle for the 22 static instances."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

from check_native_oracle import ROOT, oracle_environment, verify_extraction
from native_oracle_sdk import sdk_path
from native_room_textures import atlas_metadata

DISCOVERY_PINS = {
    "Celeste.Decal.cs": "81d04a56cb9b5cb981f3c7823388bed6082db2d5755d364c15c35bbcaf8b7746",
    "Monocle.MTexture.cs": "45847f23970911b07541e4bc367cbd156f3b4b1846b63b33d3fed9c7b65ebf6b",
    "Monocle.Atlas.cs": "95deee77a169baa04e91a5eeca76a7fd0a933ac338f2c17a847e217d7780cf70",
    "Monocle.Calc.cs": "53ba72dc68ea5f6fed05e5394dc2fa0e867ea9317cb1f3271bd0c9c6fec38669",
}
FRAMEWORK_PINS = {
    "System.Random.cs": "4d50e548631225ad23a4f2fbc48e6263e8424ed9033f2e5a4a1fe33c95060c52",
    "Microsoft.Xna.Framework.Vector2.cs": "5029bb0ed057cf28a506168082e78d80d862ec0399935abbd231780ef9a34dc3",
    "Microsoft.Xna.Framework.Color.cs": "2eaf5b1aaafb1acba38bfe46bb3629907b7dfa171248f1db7a9c2aace60a5ed7",
    "Microsoft.Xna.Framework.MathHelper.cs": "b3f8b47286150f786779f5b2362ee29f770efab9f9368283021c9797a519b92c",
    "Microsoft.Xna.Framework.Rectangle.cs": "b3fd25e76f83b62e26dacd78877088ad64b30d8c625347ffca750ddd54e195cc",
    "Microsoft.Xna.Framework.Graphics.SpriteEffects.cs": "f4e1fb57e8f77996ad20c30b76749b3532bbe1f1f95a056d44c6294f406767ec",
    "Microsoft.Xna.Framework.Graphics.SpriteBatch.cs": "00446c9efcf427a01a2a55f0ac23feb22ecbb030842401faf65c77328931bcf2",
}
RAW_ROOM_SHA = "3eefb6d3fae3cc0977583d8f53075da3db98da01795c0ce56f5b799e8bc65eb3"
GAMEPLAY_META_SHA = "1f23b1f35544a3751ffec170b0230c7c9513000ab1549f78ebb9cb9f4203c8d9"
GAMEPLAY_DATA_SHA = "687f3340c937e3baca71758bfb1e6b8e799ad896f2df19bef26ec64968b3490b"
CORRECTIONS_SHA = "f56653b9155553524e9337b7299b6c4fc14577fb1079182154c4ab730385a829"
SUPPORT = ("tests/native/oracle/decals/Shims.cs", "tests/native/oracle/decals/Runner.cs",
           "tests/native/oracle/presentation/Geometry.cs")


def read_block(base, name, ranges, pins):
    data = (base / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != pins[name]:
        raise ValueError("Pinned source identity changed: " + name)
    lines = data.splitlines(keepends=True)
    if any(start < 1 or end < start or end > len(lines) for start, end in ranges):
        raise ValueError("Missing executable source range: " + name)
    return [b"".join(lines[start - 1:end]).decode() for start, end in ranges]


def compose(discovery, pins, archive, output):
    manifest = {"source_discovery": str(discovery), "framework_pins": str(pins),
                "source_pins": {**DISCOVERY_PINS, **FRAMEWORK_PINS},
                "extractions": [], "support_sha256": {}, "stub_boundaries": [
                    "Unchanged Celeste.Decal ctor/Added/Update/Render and nested DecalImage/Banner bodies execute",
                    "Unchanged Monocle MTexture DrawCentered/GetSubtexture and Atlas GetAtlasSubtextures lookup execute",
                    "Unchanged bundled mscorlib System.Random executes behind a tracing subclass",
                    "Unchanged FNA GenerateVertexInfo produces the recorded destination/UV quad",
                    "Monocle Entity/Component/Scene and dormant Decal case dependencies are declaration-only and throw if reached",
                    "Raw room XML JSON supplies source-shaped ordered x/y/scaleX/scaleY/texture placement; no invented world fixture",
                ]}
    content = ("using System;\nusing System.Collections.Generic;\nusing System.IO;\nusing System.Text;\nusing System.Text.RegularExpressions;\n"
               "using Microsoft.Xna.Framework;\nusing Microsoft.Xna.Framework.Graphics;\nusing Monocle;\n")

    def extract(base, name, ranges, pins, label=None):
        blocks = read_block(base, name, ranges, pins)
        manifest["extractions"].append({"file": name, "source_path": str((base / name).resolve()),
                                        "source_sha256": pins[name], "lines_inclusive": ranges,
                                        "blocks_sha256": [hashlib.sha256(value.encode()).hexdigest() for value in blocks],
                                        "label": label or name})
        return "\n".join(blocks)

    content += "namespace PrivateRuntime {\n" + extract(pins, "System.Random.cs", [(7, 144)], FRAMEWORK_PINS) + "\n}\n"
    content += "namespace Microsoft.Xna.Framework { public struct Vector2 : IEquatable<Vector2> {\n"
    content += extract(pins, "Microsoft.Xna.Framework.Vector2.cs", [(13, 90), (434, 503)], FRAMEWORK_PINS) + "\n}\n"
    content += "public struct Color : IEquatable<Color> {\n"
    content += extract(pins, "Microsoft.Xna.Framework.Color.cs", [(15, 505), (525, 569), (581, 585), (597, 648)], FRAMEWORK_PINS) + "\n}\n"
    content += extract(pins, "Microsoft.Xna.Framework.MathHelper.cs", [(5, 161)], FRAMEWORK_PINS) + "\n"
    content += "public struct Rectangle {\n"
    content += extract(pins, "Microsoft.Xna.Framework.Rectangle.cs", [(13, 29), (62, 68)], FRAMEWORK_PINS) + "\n}\n}\n"
    content += "namespace Microsoft.Xna.Framework.Graphics {\n"
    content += extract(pins, "Microsoft.Xna.Framework.Graphics.SpriteEffects.cs", [(5, 11)], FRAMEWORK_PINS) + "\n}\n"
    content += "namespace Monocle { using Random = PrivateRuntime.Random; public static partial class Calc {\n"
    content += extract(discovery, "Monocle.Calc.cs", [(19, 19), (371, 423), (834, 842), (874, 881)], DISCOVERY_PINS) + "\n} }\n"
    content += "namespace Monocle { public partial class Atlas {\n"
    content += extract(discovery, "Monocle.Atlas.cs", [(24, 40), (310, 313), (324, 376)], DISCOVERY_PINS) + "\n} }\n"
    content += "namespace Monocle {\n"
    content += extract(discovery, "Monocle.MTexture.cs", [(7, 660)], DISCOVERY_PINS) + "\n}\n"
    content += "namespace Celeste {\n"
    content += extract(discovery, "Celeste.Decal.cs", [(10, 560)], DISCOVERY_PINS) + "\n}\n"
    content += "namespace PresentationOracle { public unsafe partial class OriginalSpriteBatch {\n"
    content += extract(pins, "Microsoft.Xna.Framework.Graphics.SpriteBatch.cs", [(128, 130), (335, 361), (744, 784)], FRAMEWORK_PINS) + "\n} }\n"
    (output / "Extracted.cs").write_text(content)
    manifest["extracted_sha256"] = hashlib.sha256(content.encode()).hexdigest()
    manifest["stub_boundaries_sha256"] = hashlib.sha256(json.dumps(manifest["stub_boundaries"]).encode()).hexdigest()
    for relative in SUPPORT:
        name = Path(relative).name
        shutil.copyfile(ROOT / relative, output / name)
        manifest["support_sha256"][name] = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
    (output / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    identity = verify_extraction(output)
    (output / "source-identity.json").write_text(json.dumps(identity, indent=2) + "\n")
    with zipfile.ZipFile(archive) as package:
        meta = package.read("Content/Graphics/Atlases/Gameplay.meta")
        data = package.read("Content/Graphics/Atlases/Gameplay0.data")
    if hashlib.sha256(meta).hexdigest() != GAMEPLAY_META_SHA or hashlib.sha256(data).hexdigest() != GAMEPLAY_DATA_SHA:
        raise ValueError("Pinned Gameplay atlas identity changed")
    (output / "atlas.json").write_text(json.dumps(atlas_metadata(meta)))
    (output / "Oracle.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n'
        '<PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework>'
        '<EnableDefaultCompileItems>false</EnableDefaultCompileItems><UseAppHost>false</UseAppHost>'
        '<AllowUnsafeBlocks>true</AllowUnsafeBlocks><CheckForOverflowUnderflow>false</CheckForOverflowUnderflow>'
        '<NuGetAudit>false</NuGetAudit></PropertyGroup>\n'
        '<ItemGroup><Compile Include="Extracted.cs"/><Compile Include="Shims.cs"/><Compile Include="Runner.cs"/>'
        '<Compile Include="Geometry.cs"/></ItemGroup></Project>\n')
    (output / "NuGet.Config").write_text('<configuration><packageSources><clear /></packageSources></configuration>\n')
    return manifest


def prepare(discovery, pins, archive, raw_room, corrections, output):
    discovery, pins, archive, raw_room, corrections, output = map(
        Path.resolve, (discovery, pins, archive, raw_room, corrections, output))
    if not output.is_relative_to(ROOT / ".audit") or output.exists():
        raise ValueError("Decal oracle output must be fresh and private below .audit")
    if hashlib.sha256(raw_room.read_bytes()).hexdigest() != RAW_ROOM_SHA:
        raise ValueError("Raw room placement identity changed")
    if hashlib.sha256(corrections.read_bytes()).hexdigest() != CORRECTIONS_SHA:
        raise ValueError("Corrected source-contract supplement identity changed")
    output.mkdir(parents=True)
    manifest = compose(discovery, pins, archive, output)
    manifest["raw_room"] = {"path": str(raw_room), "sha256": RAW_ROOM_SHA}
    manifest["corrections"] = {"path": str(corrections), "sha256": CORRECTIONS_SHA}
    manifest["provenance_labels"] = {
        "raw_room_fields": {"level_name": "lvl_1", "bounds": [0, 0, 320, 184]},
        "runtime_normalization": {"level_name": "1", "load_seed": 49, "logical_size": [320, 180],
                                  "source": "Celeste.LevelData.cs:113-122 strips the raw prefix; :99-110 sums the runtime Name; source height normalization is not a raw-map field"},
        "note": "room level/bounds are RAW map fields. Decal positions use raw x/y through the unchanged Decal constructor; this is not a runtime LevelData/height-184/seed-478 claim"}
    (output / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    sdk = sdk_path(ROOT)
    commands = []

    def run(label, argv):
        with (output / (label + ".log")).open("x") as log:
            result = subprocess.run([str(part) for part in argv], cwd=ROOT, env=oracle_environment(sdk),
                                    stdout=log, stderr=subprocess.STDOUT)
        commands.append({"label": label, "argv": [str(part) for part in argv], "exit_code": result.returncode, "log": label + ".log"})
        (output / "commands-run.json").write_text(json.dumps(commands, indent=2) + "\n")
        if result.returncode:
            raise RuntimeError("Decal oracle command failed: " + label)

    run("sdk", [sdk, "--version"])
    if (output / "sdk.log").read_text().strip() != "8.0.425":
        raise ValueError("Private SDK or runtime changed")
    run("restore", [sdk, "restore", output / "Oracle.csproj", "--configfile", output / "NuGet.Config"])
    run("build", [sdk, "build", output / "Oracle.csproj", "--no-restore", "-c", "Release",
                  "-p:UseSharedCompilation=false", "--disable-build-servers"])
    run("oracle", [sdk, output / "bin/Release/net8.0/Oracle.dll", raw_room, output / "atlas.json", output])
    oracle = json.loads((output / "decals-oracle.json").read_text())
    if oracle["status"] != "source-static-decals-executed":
        raise ValueError("Decal source oracle did not execute")
    if oracle["static_profile"]["count"] != 22 or oracle["static_profile"]["unique_textures"] != 15:
        raise ValueError("Decal source static profile changed")
    if oracle["static_profile"]["bg"] != 20 or oracle["static_profile"]["fg"] != 2:
        raise ValueError("Decal source layer split changed")
    if oracle["banner_exclusion"]["count"] != 7:
        raise ValueError("Decal banner exclusion count changed")
    result = {"status": "source-static-decals-closed", "identity": verify_extraction(output), "source_manifest": manifest,
              "oracle": oracle, "commands": commands,
              "artifacts": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in output.iterdir() if path.is_file()}}
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"STATIC DECAL SOURCE-ART CLOSED: 22 images (20 BG + 2 FG, 15 unique), 7 banners explicitly omitted; {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discovery", type=Path, required=True, help="Pinned source-discovery il directory")
    parser.add_argument("--pins", type=Path, required=True, help="Existing private pinned framework source directory")
    parser.add_argument("--archive", type=Path, default=ROOT / "game/celeste-linux.zip")
    parser.add_argument("--raw-room", type=Path, required=True, help="Verified raw-room.json from actual room probe")
    parser.add_argument("--corrections", type=Path, required=True, help="Corrected source-contract supplement")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.discovery, args.pins, args.archive, args.raw_room, args.corrections, args.output)
