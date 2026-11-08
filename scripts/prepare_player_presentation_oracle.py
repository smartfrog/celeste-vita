#!/usr/bin/env python3
"""Compile unchanged private presentation bodies with the tracked recording harness."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from check_native_oracle import ROOT, PRIVATE, oracle_environment, verify_extraction
from native_room_textures import atlas_metadata
from prepare_room_visuals import MEMBERS
from read_player_presentation_sources import SOURCE_PINS

SUPPORT = ("Shims.cs", "Runner.cs", "Replay.cs", "Geometry.cs")
RECIPE_FILES = ("scripts/read_player_presentation_sources.py", "scripts/prepare_player_presentation_oracle.py",
                "scripts/compare_player_presentation.py", "scripts/fixture_protocol.py")


def source_block(data, ranges, expected):
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("Pinned source identity changed")
    lines = data.splitlines(keepends=True)
    if any(start < 1 or end < start or end > len(lines) for start, end in ranges):
        raise ValueError("Missing executable source range")
    return [b"".join(lines[start - 1:end]) for start, end in ranges]


def support_hashes():
    maintained = ROOT / "tests/native/oracle/presentation"
    return {name: hashlib.sha256((maintained / name).read_bytes()).hexdigest() for name in SUPPORT}


def prepare(source, output):
    source, output = source.resolve(), output.resolve()
    if not source.is_relative_to(ROOT / ".audit") or not output.is_relative_to(ROOT / ".audit") or output.exists():
        raise ValueError("Source must be private and oracle output must be fresh beneath .audit")
    provenance = json.loads((source / "provenance.json").read_text())
    if {entry["file"]: entry["sha256"] for entry in provenance["sources"]} != SOURCE_PINS:
        raise ValueError("Original source closure is incomplete or unrecognized")
    for name, expected in SOURCE_PINS.items():
        source_block((source / name).read_bytes(), [], expected)
    for name, member in (("Sprites.xml", "Content/Graphics/Sprites.xml"), ("Gameplay.meta", "Content/Graphics/Atlases/Gameplay.meta")):
        if hashlib.sha256((source / name).read_bytes()).hexdigest() != MEMBERS[member]:
            raise ValueError("Pinned bank/atlas metadata changed")
    output.mkdir(parents=True)
    manifest = {"input_sha256": MEMBERS["Celeste.exe"], "extractions": [], "source_directory": str(source),
                "source_provenance_sha256": hashlib.sha256((source / "provenance.json").read_bytes()).hexdigest(),
                "support_sha256": support_hashes(), "recipe_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in RECIPE_FILES},
                "stub_boundaries": [
                    "Source-local FNA Vector2/Color/MathHelper/Draw/GenerateVertexInfo bodies, not the original x86 assembly or whole-game CIL execution",
                    "Metadata-only VirtualTexture, recording SpriteBatch at the sole GPU boundary; original FNA draw and vertex methods still execute",
                    "Original Atlas indexed lookup/cache, bank, metadata, Sprite/PlayerSprite/PlayerHair bodies",
                    "Read-only bounded physics projections and exact point/full-body probe truth; no native pose/frame/timer/node/color/RNG/vertex inputs",
                    "Explicit static-world absence of holding/wind/water/ClimbBlockers, other modes/states, cutscenes, and assists",
                    "Audio/surface/audio-collision and dust boundaries excluded from parity; recorded callback invocation still executes the original delegates",
                    "Bundled original mscorlib Random under a tracing subclass, explicit diagnostic seed 0, no original startup RNG parity",
                    "Phase glue supplies the bounded scene interval/ownership services and invokes unchanged original cosmetic statements in source order",
                ]}

    def extract(name, ranges):
        path = source / name
        blocks = source_block(path.read_bytes(), ranges, SOURCE_PINS[name])
        manifest["extractions"].append({"file": name, "source_path": str(path.relative_to(ROOT)), "source_sha256": SOURCE_PINS[name],
                                        "lines_inclusive": ranges, "blocks_sha256": [hashlib.sha256(block).hexdigest() for block in blocks]})
        return "\n".join(block.decode() for block in blocks)

    def whole(name, namespace):
        lines = (source / name).read_text().splitlines()
        start = next(index + 2 for index, line in enumerate(lines) if line == f"namespace {namespace};")
        return f"namespace {namespace} {{\n" + extract(name, [(start, len(lines))]) + "\n}\n"

    content = "using System;\nusing System.Collections;\nusing System.Collections.Generic;\nusing System.Globalization;\nusing System.Text;\nusing System.Xml;\nusing Microsoft.Xna.Framework;\nusing Microsoft.Xna.Framework.Graphics;\nusing Monocle;\n"
    content += "namespace PrivateRuntime {\n" + extract("System.Random.cs", [(7, 144)]) + "\n}\n"
    content += "namespace Microsoft.Xna.Framework { public struct Vector2 : IEquatable<Vector2> {\n"
    content += extract("Microsoft.Xna.Framework.Vector2.cs", [(13, 90), (434, 503)]) + "\n}\n"
    content += "public struct Color : IEquatable<Color> {\n"
    content += extract("Microsoft.Xna.Framework.Color.cs", [(15, 505), (525, 569), (581, 585), (597, 648)]) + "\n}\n"
    content += whole("Microsoft.Xna.Framework.MathHelper.cs", "Microsoft.Xna.Framework").replace("namespace Microsoft.Xna.Framework {\n", "", 1)
    content += "namespace Microsoft.Xna.Framework { public struct Rectangle {\n" + extract("Microsoft.Xna.Framework.Rectangle.cs", [(13, 29), (62, 68)]) + "\n} }\n"
    content += whole("Microsoft.Xna.Framework.Graphics.SpriteEffects.cs", "Microsoft.Xna.Framework.Graphics")
    for name in ("Sprite", "Image", "SpriteData", "SpriteBank", "Chooser_1", "GraphicsComponent", "SpriteDataSource"):
        content += whole("Monocle." + name + ".cs", "Monocle")
    for name in ("PlayerSprite", "PlayerHair", "PlayerSpriteMode", "PlayerAnimMetadata", "Facings"):
        content += whole("Celeste." + name + ".cs", "Celeste")
    content += "namespace Monocle { using Random = PresentationOracle.TracedRandom; public static partial class Calc {\n"
    content += extract("Monocle.Calc.cs", [(19, 21), (405, 418), (542, 572), (641, 644), (776, 804), (874, 881), (1017, 1020),
                                          (1027, 1030), (1042, 1055), (1222, 1260), (1472, 1517), (1607, 1610), (1696, 1699), (1802, 1805)])
    content += "\n} public partial class Atlas {\n" + extract("Monocle.Atlas.cs", [(24, 40), (310, 313), (324, 376)]) + "\n} "
    content += "public class MTexture {\n" + extract("Monocle.MTexture.cs", [(9, 98), (140, 154), (186, 199)]) + "\n} }\n"
    content += "namespace Celeste { public partial class Player : Entity {\n"
    content += extract("Celeste.Player.cs", [(459, 459), (469, 475), (541, 545), (575, 575), (621, 631), (635, 647), (934, 954), (1062, 1072)])
    content += "\npublic void BindCallbacks() {\n" + extract("Celeste.Player.cs", [(1183, 1251)]) + "\n}\n"
    content += extract("Celeste.Player.cs", [(1985, 2250)])
    for method, ranges in (("PreambleIdle", [(1482, 1490)]), ("GroundPhase", [(1543, 1554)]), ("JumpPhase", [(2466, 2466)]),
                           ("StandPhase", [(3620, 3620)]), ("DuckPhase", [(3643, 3643)]), ("FastFallPhase", [(3716, 3717), (3730, 3736)]),
                           ("LandingPhase", [(3328, 3334)])):
        content += f"\npublic void {method}() {{\n" + extract("Celeste.Player.cs", ranges) + "\n}\n"
    content += "public void RenderBounded() {\n" + extract("Celeste.Player.cs", [(1366, 1367), (1374, 1384), (1390, 1390)])
    content += "\nHair.Render(); Sprite.Render();\n" + extract("Celeste.Player.cs", [(1406, 1406), (1413, 1413)]) + "\n}\n\n} }\n"
    content += "namespace PresentationOracle { public unsafe partial class OriginalSpriteBatch {\n"
    content += extract("Microsoft.Xna.Framework.Graphics.SpriteBatch.cs", [(128, 130), (335, 361), (744, 784)]) + "\n} }\n"
    (output / "Extracted.cs").write_text(content)
    manifest["extracted_sha256"] = hashlib.sha256(content.encode()).hexdigest()
    manifest["caller_anchors"] = []
    for name, ranges in (("Celeste.PlayerInventory.cs", [(8, 20), (30, 36)]), ("Celeste.AreaData.cs", [(145, 151), (867, 887)]),
                          ("Celeste.Level.cs", [(1314, 1318), (1909, 1926)]), ("Monocle.ComponentList.cs", [(199, 223)]),
                          ("Celeste.Player.cs", [(1116, 1138), (1705, 1736)])):
        blocks = source_block((source / name).read_bytes(), ranges, SOURCE_PINS[name])
        manifest["caller_anchors"].append({"file": name, "source_sha256": SOURCE_PINS[name], "lines_inclusive": ranges,
                                           "blocks_sha256": [hashlib.sha256(block).hexdigest() for block in blocks]})
    (output / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    identity = verify_extraction(output)
    (output / "source-identity.json").write_text(json.dumps(identity, indent=2) + "\n")
    (output / "atlas.json").write_text(json.dumps(atlas_metadata((source / "Gameplay.meta").read_bytes())))
    for name in SUPPORT:
        (output / name).write_bytes((ROOT / "tests/native/oracle/presentation" / name).read_bytes())
    (output / "Oracle.csproj").write_text('''<Project Sdk="Microsoft.NET.Sdk">
<PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework><EnableDefaultCompileItems>false</EnableDefaultCompileItems><UseAppHost>false</UseAppHost><AllowUnsafeBlocks>true</AllowUnsafeBlocks><CheckForOverflowUnderflow>false</CheckForOverflowUnderflow><NuGetAudit>false</NuGetAudit></PropertyGroup>
<ItemGroup><Compile Include="Extracted.cs"/><Compile Include="Shims.cs"/><Compile Include="Runner.cs"/><Compile Include="Replay.cs"/><Compile Include="Geometry.cs"/></ItemGroup></Project>''')
    (output / "NuGet.Config").write_text('<configuration><packageSources><clear/></packageSources></configuration>')
    sdk = PRIVATE / "tools/dotnet-8.0.425/dotnet"
    commands = []
    for arguments, log in ((["--version"], "sdk.log"), (["--list-runtimes"], "runtime.log"),
                            (["restore", output / "Oracle.csproj", "--configfile", output / "NuGet.Config"], "restore.log"),
                            (["build", output / "Oracle.csproj", "--no-restore", "-c", "Release", "-p:UseSharedCompilation=false", "--disable-build-servers"], "build.log"),
                            ([output / "bin/Release/net8.0/Oracle.dll", output / "atlas.json", source / "Sprites.xml", output], "execution.log")):
        command = list(map(str, [sdk, *arguments]))
        with (output / log).open("x") as stream:
            result = subprocess.run(command, cwd=ROOT, env=oracle_environment(sdk), stdout=stream, stderr=subprocess.STDOUT)
        commands.append({"command": command, "exit_code": result.returncode, "log": log})
        (output / "commands-run.json").write_text(json.dumps(commands, indent=2) + "\n")
        if result.returncode:
            raise RuntimeError("Unchanged source compile/execution failed: " + str(output / log))
        if log == "sdk.log" and (output / log).read_text().strip() != "8.0.425":
            raise ValueError("Pinned offline SDK changed")
        if log == "runtime.log" and "Microsoft.NETCore.App 8.0.31 [" not in (output / log).read_text():
            raise ValueError("Pinned offline runtime changed")
    return identity


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.output), indent=2))
