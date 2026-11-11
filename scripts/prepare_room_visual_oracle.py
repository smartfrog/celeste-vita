#!/usr/bin/env python3
"""Compile/bake unchanged private loader, autotiler and bundled Random bodies offline."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from check_native_oracle import ROOT, oracle_environment, verify_extraction
from native_oracle_sdk import sdk_path
from extract_native_oracle import INPUT_SHA, SOURCE_HASHES
from native_room_textures import atlas_metadata
from prepare_static_tilemap import build_layers, build_mask, mask_text
from prepare_room_visuals import MEMBERS


VISUAL_SOURCES = {
    "Celeste.Autotiler.cs": "e663b8a83c60114ba0fde61c568691fdcad48294e02ce96845c61d86432d2d24",
    "Monocle.VirtualMap.cs": "4603eef86cd00402cdbf8d736f4b5a6b8db935328f5c2b8eed88d62924b58a36",
    "Monocle.Tileset.cs": "0bb90f6f102b0bf46b7f48acf5a379e1516e8bad1de6a72adfb3d5c50c7556cc",
    "System.Random.cs": "4d50e548631225ad23a4f2fbc48e6263e8424ed9033f2e5a4a1fe33c95060c52",
    "Celeste.AnimatedTiles.cs": "46b910aa720a09ed0c0f026dd11573ac4d758263ed74276383b353f40b3e36cd",
    "Celeste.AnimatedTilesBank.cs": "614fc0b61a1214985d7f90ac5ebf8d05c915e9cfecd0283b88f479238a7ee1f9",
}


def prepare(source, output):
    manifest = {"input_sha256": INPUT_SHA, "extractions": [], "stub_boundaries": [
        "Source VirtualMap segmentation retained, not the collision oracle's dense storage shim",
        "Metadata-only MTexture and assignment-recording TileGrid; unchanged Tileset/Autotiler chooses rules and variants",
        "Unchanged bundled mscorlib Random bodies behind tracing subclass; no System.Random/.NET8 RNG substitution",
        "Environment resource-message and TickCount type glue; default random is replaced by unchanged seeded PushRandom before bake",
        "Full AnimatedTiles.Set and bank Add execute even though overlays are not rendered",
        "Rectangle, two-float Vector2 and isolated XML file/Engine content-directory boundary",
        "Synthetic JSON driver reuses accepted all-room/filler scalars; no gameplay or private runtime execution",
    ]}

    def extract(path, ranges, expected):
        data = path.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected:
            raise ValueError(f"Changed pinned source {path}: {actual}")
        lines = data.decode().splitlines(keepends=True)
        blocks = ["".join(lines[start - 1:end]) for start, end in ranges]
        manifest["extractions"].append({"file": path.name, "source_path": str(path.relative_to(ROOT)), "source_sha256": actual,
                                        "lines_inclusive": ranges, "blocks_sha256": [hashlib.sha256(b.encode()).hexdigest() for b in blocks]})
        return "\n".join(blocks)

    def visual(name, ranges):
        return extract(source / name, ranges, VISUAL_SOURCES[name])

    def existing(name, ranges):
        if (source / name).is_file():
            path = source / name
        elif name in {"Celeste.MapData.cs", "Celeste.LevelLoader.cs"}:
            path = ROOT / ".audit/native-static-tilemap" / name
        elif name == "Monocle.Calc.cs":
            path = ROOT / ".audit/native-wall-jumps/closure" / name
        else:
            path = ROOT / ".audit/ilspy/cs" / name
        return extract(path, ranges, SOURCE_HASHES[name])

    content = "using System;\nusing System.IO;\nusing System.Collections.Generic;\nusing System.Text.RegularExpressions;\nusing System.Xml;\nusing Microsoft.Xna.Framework;\nusing Monocle;\n"
    content += "namespace PrivateRuntime {\n" + visual("System.Random.cs", [(7, 144)]) + "\n}\n"
    content += "namespace Monocle {\n" + visual("Monocle.VirtualMap.cs", [(3, 132)]) + "\n"
    content += visual("Monocle.Tileset.cs", [(3, 41)]) + "\n}\n"
    content += "namespace Monocle { using Random = VisualOracle.TracedRandom; public static class Calc {\n"
    content += existing("Monocle.Calc.cs", [(19, 21), (323, 344), (371, 379), (712, 715), (1446, 1452), (1472, 1480), (1552, 1555)]) + "\n} }\n"
    content += "namespace Celeste {\n" + visual("Celeste.Autotiler.cs", [(9, 422)]) + "\n"
    content += visual("Celeste.AnimatedTilesBank.cs", [(7, 42)]) + "\n"
    content += "public class AnimatedTiles : Component {\n" + visual("Celeste.AnimatedTiles.cs", [(10, 17), (27, 56)]) + "\n}\n"
    content += "public partial class LevelData {\n" + existing("Celeste.LevelData.cs", [(76, 76), (113, 138)]) + "\n} } } }\n"
    content += "public partial class MapData {\n" + existing("Celeste.MapData.cs", [(47, 61)])
    content += "\npublic void ComputeBounds() {\n" + existing("Celeste.MapData.cs", [(192, 235)]) + "\n} }\n"
    content += "public class MaskLoader { public LoaderLayers Build(MapData mapData) {\n"
    content += existing("Celeste.LevelLoader.cs", [(95, 266)]) + "\nreturn new LoaderLayers(virtualMap2, virtualMap, position);\n} } }\n"
    (output / "Extracted.cs").write_text(content)
    manifest["extracted_sha256"] = hashlib.sha256(content.encode()).hexdigest()
    (output / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    maintained = ROOT / "tests/native/oracle/visuals"
    (output / "Oracle.csproj").write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework>
    <EnableDefaultCompileItems>false</EnableDefaultCompileItems><UseAppHost>false</UseAppHost>
    <CheckForOverflowUnderflow>false</CheckForOverflowUnderflow><NuGetAudit>false</NuGetAudit>
  </PropertyGroup>
  <ItemGroup><Compile Include="Extracted.cs" /><Compile Include="{maintained / 'Shims.cs'}" /><Compile Include="{maintained / 'Runner.cs'}" /></ItemGroup>
</Project>
''')
    (output / "NuGet.Config").write_text('<configuration><packageSources><clear /></packageSources></configuration>\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / ".audit/native-room-visuals/source-closure-01")
    parser.add_argument("--prepared", type=Path, default=ROOT / ".audit/native-static-tilemap/prepared")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, default=ROOT / ".audit/ilspy/inputs")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / ".audit") or output.exists():
        parser.error("Output must be fresh and private below .audit")
    output.mkdir(parents=True)
    input_identities = {}
    for name in ("Celeste.exe", "FNA.dll", "mscorlib.dll", "Content/Graphics/Atlases/Gameplay.meta",
                 "Content/Graphics/ForegroundTiles.xml", "Content/Graphics/BackgroundTiles.xml", "Content/Graphics/AnimatedTiles.xml", "Content/Graphics/Sprites.xml"):
        path = args.inputs / name if "/" not in name else args.source / name.rsplit("/", 1)[-1]
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != MEMBERS[name]:
            raise ValueError("Changed independent source input: " + name)
        input_identities[name] = {"path": str(path), "bytes": len(data), "sha256": MEMBERS[name]}
    provenance = json.loads((args.prepared / "provenance.json").read_text())
    for name, digest in provenance["files"].items():
        if hashlib.sha256((args.prepared / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Changed accepted preparation: " + name)
    prepare(args.source, output)
    identity = verify_extraction(output)
    (output / "source-identity.json").write_text(json.dumps(identity, indent=2) + "\n")
    atlas_path = args.source / "Gameplay.meta"
    if hashlib.sha256(atlas_path.read_bytes()).hexdigest() != "1f23b1f35544a3751ffec170b0230c7c9513000ab1549f78ebb9cb9f4203c8d9":
        raise ValueError("Changed atlas metadata")
    (output / "atlas.json").write_text(json.dumps(atlas_metadata(atlas_path.read_bytes())))
    sdk = sdk_path(ROOT)
    commands = []

    def run(command, log):
        command = [str(part) for part in command]
        with (output / log).open("x") as out:
            result = subprocess.run(command, cwd=ROOT, env=oracle_environment(sdk), stdout=out, stderr=subprocess.STDOUT)
        commands.append({"command": command, "exit_code": result.returncode, "log": log})
        (output / "commands-run.json").write_text(json.dumps(commands, indent=2) + "\n")
        if result.returncode:
            raise RuntimeError(f"Failed command; see {output / log}")

    run([sdk, "--version"], "sdk.log")
    run([sdk, "--list-runtimes"], "runtime.log")
    if (output / "sdk.log").read_text().strip() != "8.0.425" or "Microsoft.NETCore.App 8.0.31 [" not in (output / "runtime.log").read_text():
        raise ValueError("Private SDK/runtime changed")
    run([sdk, "restore", output / "Oracle.csproj", "--configfile", output / "NuGet.Config"], "restore.log")
    run([sdk, "build", output / "Oracle.csproj", "--no-restore", "-c", "Release", "-p:UseSharedCompilation=false", "--disable-build-servers"], "build.log")
    run([sdk, output / "bin/Release/net8.0/Oracle.dll", args.prepared / "driver.json", output / "atlas.json", args.source, output], "bake.log")
    layers = json.loads((output / "layers.json").read_text())
    driver = json.loads((args.prepared / "driver.json").read_text())
    x, y, fg, bg, bounds = build_layers(driver)
    expected = dict(origin=[x, y], columns=fg.columns, rows=fg.rows, foreground="".join(fg.data), background="".join(bg.data), bounds=[list(b) for b in bounds])
    if layers != expected:
        raise ValueError("Source character grids/bounds differ from host preparation")
    if mask_text(build_mask(driver)) != (args.prepared / "global.mask").read_text():
        raise ValueError("Existing collision mask changed")
    bake = json.loads((output / "bake.json").read_text())
    if bake["seed"] != 553 or layers["columns"] != 541 or layers["rows"] != 440 or len(bounds) != 38:
        raise ValueError("Actual full-map bake acceptance changed")
    rng = json.loads((output / "rng.json").read_text())
    if rng[0]["api"] != ".ctor" or rng[0]["arguments"] != [553] or any(r["api"] == ".ctor" for r in rng[1:]):
        raise ValueError("Shared seeded RNG stream was not preserved")
    result = {"status": "source-closed-compile-and-bake", "identity": identity, "inputs": input_identities, "bake": bake,
              "all_fg_bg_cells_compared": fg.columns * fg.rows * 2, "all_level_bounds_compared": len(bounds),
              "collision_mask": "byte-unchanged", "commands": commands,
              "artifacts": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}}
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"SOURCE-CLOSED COMPILED/BAKED: {bake}; all {result['all_fg_bg_cells_compared']} character cells + 38 bounds; collision mask unchanged; {output}")


if __name__ == "__main__":
    main()
