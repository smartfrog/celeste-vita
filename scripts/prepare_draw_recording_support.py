#!/usr/bin/env python3
"""Compile and self-check the strict draw recorder for the separate update+DRAW profile.

Reuses pinned private decompile sources and the pinned .NET SDK in place; generated
harness text (framework spans already cached in the pinned decompiles) and logs go only
to a fresh --output directory. The accepted CPU/presentation oracles are untouched.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from check_native_oracle import ROOT
from native_oracle_sdk import sdk_path
from prepare_decals_oracle import DISCOVERY_PINS as DECALS_DISCOVERY_PINS, FRAMEWORK_PINS as DECALS_FRAMEWORK_PINS

DISCOVERY_PINS = {name: DECALS_DISCOVERY_PINS[name] for name in
                  ("Monocle.MTexture.cs", "Monocle.Atlas.cs", "Monocle.Calc.cs")}
FRAMEWORK_PINS = dict(DECALS_FRAMEWORK_PINS)
SHEET_SPANS = {
    "System.Random.cs": [(7, 144)],
    "Microsoft.Xna.Framework.Vector2.cs": [(13, 90), (434, 503)],
    "Microsoft.Xna.Framework.Color.cs": [(15, 505), (525, 569), (581, 585), (597, 648)],
    "Microsoft.Xna.Framework.MathHelper.cs": [(5, 161)],
    "Microsoft.Xna.Framework.Rectangle.cs": [(13, 29), (62, 68)],
    "Microsoft.Xna.Framework.Graphics.SpriteEffects.cs": [(5, 11)],
    "Microsoft.Xna.Framework.Graphics.SpriteBatch.cs": [(128, 130), (335, 361), (744, 784)],
    "Monocle.Calc.cs": [(19, 19), (371, 423), (834, 842), (874, 881)],
    "Monocle.Atlas.cs": [(24, 40)],
    "Monocle.MTexture.cs": [(7, 660)],
}
SUPPORT = (
    "tests/native/oracle/transition/DrawRecording.cs",
    "tests/native/oracle/transition/DrawRecordingRunner.cs",
    "tests/native/oracle/presentation/Geometry.cs",
)
REQUIRED_CHECKS = (
    "sheet-identity-and-real-dimensions",
    "unknown-sheet-fails-loud",
    "conflicting-sheet-registration-fails",
    "scalar-vector-draw-fidelity",
    "real-dimensions-drive-uv",
    "ordered-batch-state-recording",
    "draw-requires-open-batch",
    "non-deferred-sort-rejected-state-unchanged",
    "effect-submission-rejected-state-unchanged",
    "invalid-sort-enum-rejected",
    "no-draw-omitted",
)
DEFAULT_DISCOVERY = Path("/home/fred/projects/celeste-vita/.audit/native-first-room-decals/source-discovery-f4/il")
DEFAULT_PINS = Path("/tmp/opencode/celeste-vita-spike-art/.audit/native-first-room-spike-art/source-pins-01")
CANONICAL = Path("/home/fred/projects/celeste-vita")
AUDIT_NAMESPACE = ROOT / ".audit/native-room-transition-vita/update-draw-contract-01"
CANONICAL_EVIDENCE_NAMESPACE = CANONICAL / ".audit/native-room-transition-vita"
TEMP_NAMESPACE = Path("/tmp/opencode")


def default_sdk():
    for root in (ROOT, CANONICAL):
        sdk = sdk_path(root)
        if sdk.exists():
            return sdk
    raise ValueError("Pinned private .NET SDK is unavailable in both the worktree and the canonical repo")


def oracle_environment(sdk, scratch):
    tools = sdk.parents[1]
    (scratch / "tmp").mkdir(parents=True, exist_ok=True)
    return os.environ | {
        "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1", "DOTNET_NOLOGO": "1",
        "DOTNET_CLI_HOME": str(tools / "cli"), "NUGET_PACKAGES": str(tools / "packages"),
        "DOTNET_ROOT": str(sdk.parent), "DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE": "1", "MSBUILDDISABLENODEREUSE": "1",
        "TMPDIR": str(scratch / "tmp"),
    }


def read_block(base, name, ranges, pins):
    data = (base / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != pins[name]:
        raise ValueError("Pinned source identity changed: " + name)
    lines = data.decode().splitlines(keepends=True)
    if any(start < 1 or end < start or end > len(lines) for start, end in ranges):
        raise ValueError("Missing executable source range: " + name)
    return ["".join(lines[start - 1:end]) for start, end in ranges]


def compose(discovery, pins, output):
    if output.exists():
        raise ValueError("Draw recorder output must be fresh: " + str(output))
    manifest = {"source_discovery": str(discovery), "framework_pins": str(pins),
                "source_pins": {**DISCOVERY_PINS, **FRAMEWORK_PINS},
                "extractions": [], "support_sha256": {}, "stub_boundaries": [
                    "Unchanged original FNA SpriteBatch Draw/GenerateVertexInfo produce the recorded vertex geometry",
                    "Unchanged Monocle MTexture Draw overloads route scalar and uniform vector scales into the recording batch",
                    "Strict sheet registry: AddMetadata fails loudly on unregistered sheets and never synthesizes dimensions",
                    "Ordered batch begin/end state records the transform matrix and per-batch draw ranges",
                    "Submission-order recording only: non-Deferred SpriteSortMode values, invalid enum values and non-null Effect submissions are rejected before any open/States change; no sort GPU is implemented",
                    "Owner attribution and GPU scissor/clip state are unsupported and not observed; the recorded Clip is the atlas source rectangle, not a scissor rect",
                    "Not full source parity: only the currently needed original GameplayRenderer.Begin Deferred/null submission is accepted",
                    "Harness-only Matrix/state/GraphicsResource stubs come from DrawRecordingRunner.cs, never an accepted oracle",
                ]}
    content = ("using System;\nusing System.Collections.Generic;\nusing System.IO;\nusing System.Text;\n"
               "using System.Text.RegularExpressions;\nusing Microsoft.Xna.Framework;\n"
               "using Microsoft.Xna.Framework.Graphics;\nusing Monocle;\n")

    def extract(base, name, ranges, pin_table):
        blocks = read_block(base, name, ranges, pin_table)
        manifest["extractions"].append({"file": name, "source_path": str((base / name).resolve()),
                                        "source_sha256": pin_table[name], "lines_inclusive": ranges,
                                        "blocks_sha256": [hashlib.sha256(value.encode()).hexdigest() for value in blocks]})
        return "\n".join(blocks)

    content += "namespace PrivateRuntime {\n" + extract(pins, "System.Random.cs", SHEET_SPANS["System.Random.cs"], FRAMEWORK_PINS) + "\n}\n"
    content += "namespace Microsoft.Xna.Framework { public struct Vector2 : IEquatable<Vector2> {\n"
    content += extract(pins, "Microsoft.Xna.Framework.Vector2.cs", SHEET_SPANS["Microsoft.Xna.Framework.Vector2.cs"], FRAMEWORK_PINS) + "\n}\n"
    content += "public struct Color : IEquatable<Color> {\n"
    content += extract(pins, "Microsoft.Xna.Framework.Color.cs", SHEET_SPANS["Microsoft.Xna.Framework.Color.cs"], FRAMEWORK_PINS) + "\n}\n"
    content += extract(pins, "Microsoft.Xna.Framework.MathHelper.cs", SHEET_SPANS["Microsoft.Xna.Framework.MathHelper.cs"], FRAMEWORK_PINS) + "\n"
    content += "public struct Rectangle {\n"
    content += extract(pins, "Microsoft.Xna.Framework.Rectangle.cs", SHEET_SPANS["Microsoft.Xna.Framework.Rectangle.cs"], FRAMEWORK_PINS) + "\n}\n}\n"
    content += "namespace Microsoft.Xna.Framework.Graphics {\n"
    content += extract(pins, "Microsoft.Xna.Framework.Graphics.SpriteEffects.cs", SHEET_SPANS["Microsoft.Xna.Framework.Graphics.SpriteEffects.cs"], FRAMEWORK_PINS) + "\n}\n"
    content += "namespace Monocle { using Random = PrivateRuntime.Random; public static partial class Calc {\n"
    content += extract(discovery, "Monocle.Calc.cs", SHEET_SPANS["Monocle.Calc.cs"], DISCOVERY_PINS) + "\n} }\n"
    content += "namespace Monocle { public partial class Atlas {\n"
    content += extract(discovery, "Monocle.Atlas.cs", SHEET_SPANS["Monocle.Atlas.cs"], DISCOVERY_PINS) + "\n} }\n"
    content += "namespace Monocle {\n"
    content += extract(discovery, "Monocle.MTexture.cs", SHEET_SPANS["Monocle.MTexture.cs"], DISCOVERY_PINS) + "\n}\n"
    content += "namespace PresentationOracle { public unsafe partial class OriginalSpriteBatch {\n"
    content += extract(pins, "Microsoft.Xna.Framework.Graphics.SpriteBatch.cs",
                       SHEET_SPANS["Microsoft.Xna.Framework.Graphics.SpriteBatch.cs"], FRAMEWORK_PINS) + "\n} }\n"
    output.mkdir(parents=True)
    (output / "Extracted.cs").write_text(content)
    manifest["extracted_sha256"] = hashlib.sha256(content.encode()).hexdigest()
    for relative in SUPPORT:
        name = Path(relative).name
        shutil.copyfile(ROOT / relative, output / name)
        manifest["support_sha256"][name] = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
    (output / "Oracle.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n'
        '<PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework>'
        '<EnableDefaultCompileItems>false</EnableDefaultCompileItems><UseAppHost>false</UseAppHost>'
        '<AllowUnsafeBlocks>true</AllowUnsafeBlocks><CheckForOverflowUnderflow>false</CheckForOverflowUnderflow>'
        '<NuGetAudit>false</NuGetAudit></PropertyGroup>\n'
        '<ItemGroup><Compile Include="Extracted.cs"/><Compile Include="DrawRecording.cs"/>'
        '<Compile Include="DrawRecordingRunner.cs"/><Compile Include="Geometry.cs"/></ItemGroup></Project>\n')
    (output / "NuGet.Config").write_text('<configuration><packageSources><clear /></packageSources></configuration>\n')
    return manifest


def prepare(discovery, pins, output, sdk):
    discovery, pins, output = map(Path.resolve, (discovery, pins, output))
    if not (output.is_relative_to(AUDIT_NAMESPACE) or output.is_relative_to(TEMP_NAMESPACE)
            or output.is_relative_to(CANONICAL_EVIDENCE_NAMESPACE / "draw-recorder-corrective-01")):
        raise ValueError("Draw recorder output must stay inside the private draw, corrective-evidence or /tmp/opencode namespaces")
    manifest = compose(discovery, pins, output)
    commands = []

    def run(label, argv):
        with (output / (label + ".log")).open("x") as log:
            result = subprocess.run([str(part) for part in argv], cwd=ROOT, env=oracle_environment(sdk, output),
                                    stdout=log, stderr=subprocess.STDOUT)
        commands.append({"label": label, "argv": [str(part) for part in argv], "exit_code": result.returncode, "log": label + ".log"})
        (output / "commands-run.json").write_text(json.dumps(commands, indent=2) + "\n")
        if result.returncode:
            raise RuntimeError("Draw recorder command failed: " + label)

    run("sdk", [sdk, "--version"])
    if (output / "sdk.log").read_text().strip() != "8.0.425":
        raise ValueError("Private SDK or runtime changed")
    run("restore", [sdk, "restore", output / "Oracle.csproj", "--configfile", output / "NuGet.Config"])
    run("build", [sdk, "build", output / "Oracle.csproj", "--no-restore", "-c", "Release",
                  "-p:UseSharedCompilation=false", "--disable-build-servers"])
    run("recorder", [sdk, output / "bin/Release/net8.0/Oracle.dll", output])
    oracle = json.loads((output / "recorder-support.json").read_text())
    names = [check["name"] for check in oracle["checks"]]
    scope = oracle.get("scope", {})
    if (not str(scope.get("owner_attribution", "")).startswith("unsupported-not-observed")
            or not str(scope.get("scissor_state", "")).startswith("unsupported-not-observed")
            or not str(scope.get("sorting", "")).startswith("deferred-submission-order-only")
            or not str(scope.get("camera_source", "")).startswith("recorded matrix is the exact effective transform")
            or scope.get("parity") != "not full source parity; only the currently needed original GameplayRenderer.Begin Deferred/null submission is accepted"):
        raise ValueError("Recorder scope delimitation missing or weakened")
    if oracle["status"] != "draw-recording-support-verified" or oracle["failures"] != []:
        raise ValueError("Strict draw recorder self-check failed: " + str(oracle["failures"]))
    if tuple(names) != REQUIRED_CHECKS:
        raise ValueError("Unexpected recorder self-check set: " + str(names))
    (output / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    result = {"status": oracle["status"], "checks_passed": len(oracle["checks"]), "failures": oracle["failures"],
              "oracle": oracle, "commands": commands,
              "artifacts": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in output.iterdir() if path.is_file()}}
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print("STRICT DRAW RECORDER VERIFIED:", output)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discovery", type=Path, default=DEFAULT_DISCOVERY, help="Pinned source-discovery il directory")
    parser.add_argument("--pins", type=Path, default=DEFAULT_PINS, help="Existing private pinned framework source directory")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.discovery, args.pins, args.output, default_sdk())
