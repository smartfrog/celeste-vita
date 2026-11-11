#!/usr/bin/env python3
"""Compile the narrow unchanged Spikes/Image/Atlas/Random art oracle."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from check_native_oracle import ROOT, oracle_environment, verify_extraction
from native_oracle_sdk import sdk_path
from prepare_room_visuals import MEMBERS
from read_player_presentation_sources import SOURCE_PINS
from native_room_textures import atlas_metadata

SUPPORT = ("tests/native/oracle/spikes/Shims.cs", "tests/native/oracle/spikes/Runner.cs",
           "tests/native/oracle/presentation/Geometry.cs")


def block(source, name, ranges):
    data = (source / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != SOURCE_PINS[name]:
        raise ValueError("Pinned source identity changed: " + name)
    lines = data.splitlines(keepends=True)
    if any(start < 1 or end < start or end > len(lines) for start, end in ranges):
        raise ValueError("Missing executable source range: " + name)
    return [b"".join(lines[start - 1:end]).decode() for start, end in ranges]


def compose(source, output):
    manifest = {"input_sha256": MEMBERS["Celeste.exe"], "source_directory": str(source),
                "source_provenance_sha256": hashlib.sha256((source / "provenance.json").read_bytes()).hexdigest(),
                "extractions": [], "support_sha256": {}, "stub_boundaries": [
                    "Unchanged Celeste.Spikes constructor and Added bodies execute with recording Collider/Add/AreaData shims",
                    "Unchanged Monocle.Calc.Random and bundled mscorlib System.Random with tracing subclass",
                    "Unchanged Monocle.Image/MTexture Draw and FNA GenerateVertexInfo; metadata-only VirtualTexture/recording SpriteBatch at GPU boundary",
                    "Unchanged Atlas GetAtlasSubtextures singleton-family lookup resident in the same class as the metadata shim",
                    "Spike riding/blocker callbacks and tentacle sprites remain declaration-boundary shims and are never invoked",
                ]}
    content = ("using System;\nusing System.Collections.Generic;\nusing System.Text;\nusing Microsoft.Xna.Framework;\n"
               "using Microsoft.Xna.Framework.Graphics;\nusing Monocle;\n")

    def extract(name, ranges):
        blocks = block(source, name, ranges)
        manifest["extractions"].append({"file": name, "source_path": str((source / name).relative_to(ROOT)),
                                        "source_sha256": SOURCE_PINS[name], "lines_inclusive": ranges,
                                        "blocks_sha256": [hashlib.sha256(value.encode()).hexdigest() for value in blocks]})
        return "\n".join(blocks)

    def whole(name, namespace):
        lines = (source / name).read_text().splitlines()
        start = next(index + 2 for index, line in enumerate(lines) if line == f"namespace {namespace};")
        return f"namespace {namespace} {{\n" + extract(name, [(start, len(lines))]) + "\n}\n"

    def w(name):
        return whole(name, "Monocle")

    content += "namespace PrivateRuntime {\n" + extract("System.Random.cs", [(7, 144)]) + "\n}\n"
    content += "namespace Microsoft.Xna.Framework { public struct Vector2 : IEquatable<Vector2> {\n"
    content += extract("Microsoft.Xna.Framework.Vector2.cs", [(13, 90), (434, 503)]) + "\n}\n"
    content += "public struct Color : IEquatable<Color> {\n"
    content += extract("Microsoft.Xna.Framework.Color.cs", [(15, 505), (525, 569), (581, 585), (597, 648)]) + "\n}\n"
    content += whole("Microsoft.Xna.Framework.MathHelper.cs", "Microsoft.Xna.Framework").replace(
        "namespace Microsoft.Xna.Framework {\n", "", 1)
    content += "namespace Microsoft.Xna.Framework { public struct Rectangle {\n"
    content += extract("Microsoft.Xna.Framework.Rectangle.cs", [(13, 29), (62, 68)]) + "\n} }\n"
    content += whole("Microsoft.Xna.Framework.Graphics.SpriteEffects.cs", "Microsoft.Xna.Framework.Graphics")
    for name in ("Image", "GraphicsComponent"):
        content += w("Monocle." + name + ".cs")
    content += "namespace Monocle { using Random = PrivateRuntime.Random; public static partial class Calc {\n"
    content += extract("Monocle.Calc.cs", [(19, 19), (371, 379)]) + "\n} }\n"
    content += "namespace Monocle { public partial class Atlas {\n"
    content += extract("Monocle.Atlas.cs", [(24, 40), (310, 313), (324, 376)]) + "\n} }\n"
    content += "namespace Monocle { public class MTexture {\n"
    content += extract("Monocle.MTexture.cs", [(9, 98), (140, 154), (186, 199)]) + "\n} }\n"
    content += "namespace Celeste {\n" + extract("Celeste.Spikes.cs", [(9, 282)]) + "\n}\n"
    content += "namespace PresentationOracle { public unsafe partial class OriginalSpriteBatch {\n"
    content += extract("Microsoft.Xna.Framework.Graphics.SpriteBatch.cs", [(128, 130), (335, 361), (744, 784)]) + "\n} }\n"
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
    (output / "atlas.json").write_text(json.dumps(atlas_metadata((source / "Gameplay.meta").read_bytes())))
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


def prepare(source, hazards, output):
    source, hazards, output = source.resolve(), hazards.resolve(), output.resolve()
    if not output.is_relative_to(ROOT / ".audit") or output.exists():
        raise ValueError("Spike oracle output must be fresh and private below .audit")
    provenance = json.loads((source / "provenance.json").read_text())
    if {entry["file"]: entry["sha256"] for entry in provenance["sources"]} != SOURCE_PINS:
        raise ValueError("Source closure is incomplete or unrecognized")
    if hazards.name != "hazards.json":
        raise ValueError("Spike oracle consumes the prepared hazards.json")
    output.mkdir(parents=True)
    manifest = compose(source, output)
    sdk = sdk_path(ROOT)
    commands = []

    def run(label, argv):
        with (output / (label + ".log")).open("x") as log:
            result = subprocess.run([str(part) for part in argv], cwd=ROOT, env=oracle_environment(sdk),
                                    stdout=log, stderr=subprocess.STDOUT)
        commands.append({"label": label, "argv": [str(part) for part in argv], "exit_code": result.returncode, "log": label + ".log"})
        (output / "commands-run.json").write_text(json.dumps(commands, indent=2) + "\n")
        if result.returncode:
            raise RuntimeError("Spike oracle command failed: " + label)

    run("sdk", [sdk, "--version"])
    if (output / "sdk.log").read_text().strip() != "8.0.425":
        raise ValueError("Private SDK or runtime changed")
    run("restore", [sdk, "restore", output / "Oracle.csproj", "--configfile", output / "NuGet.Config"])
    run("build", [sdk, "build", output / "Oracle.csproj", "--no-restore", "-c", "Release",
                  "-p:UseSharedCompilation=false", "--disable-build-servers"])
    run("oracle", [sdk, output / "bin/Release/net8.0/Oracle.dll", hazards, output / "atlas.json", output])
    oracle = json.loads((output / "spike-oracle.json").read_text())
    if oracle["status"] != "source-spike-art-executed" or oracle["draws"] != 19 or len(oracle["pieces"]) != 19:
        raise ValueError("Spike oracle did not produce nineteen source pieces")
    if oracle["families"]["up"]["count"] != 1 or oracle["families"]["left"]["count"] != 1:
        raise ValueError("Spike source family is not the pinned singleton")
    for run_row in oracle["runs"]:
        if run_row["rng"]["next_calls"] != 19 or set(run_row["rng"]["next_maximums"]) != {1} or set(run_row["rng"]["results"]) != {0}:
            raise ValueError("Source Choose RNG invariant failed for seed/prefix run")
    result = {"status": "source-spike-art-closed", "identity": verify_extraction(output), "source_manifest": manifest,
              "oracle": oracle, "commands": commands,
              "artifacts": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in output.iterdir() if path.is_file()}}
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"SPIKE SOURCE-ART CLOSED: 19 pieces, 5 hazards, 19x Next(1)->0; {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Fresh read_player_presentation_sources output")
    parser.add_argument("--hazards", type=Path, default=ROOT / ".audit/native-room-hazards/prepared/hazards.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.source, args.hazards, args.output)
