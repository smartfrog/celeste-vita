#!/usr/bin/env python3
"""Compile unchanged private lifecycle bodies; fail closed at unsupported services."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from check_native_oracle import ROOT, oracle_environment, verify_extraction
from native_oracle_sdk import sdk_path
from prepare_player_presentation_oracle import source_block
from read_player_death_sources import SOURCE_PINS, EXTRA_PINS, PRESENTATION_PINS, ILSPY_SHA
from prepare_room_visuals import MEMBERS
from native_room_textures import atlas_metadata
from native_room_revision import source_state

TRACE_IDS = {"up", "left", "ordering", "corpse", "boundaries", "freeze-input", "reload", "cycles"}
CALLBACKS = {"DeathRoutine", "End", "Reload", "IntroRespawnBegin", "IntroRespawnEnd"}
RECIPE_FILES = ("scripts/read_player_death_sources.py", "scripts/prepare_player_death_oracle.py",
    "scripts/read_player_presentation_sources.py", "scripts/prepare_player_presentation_oracle.py",
    "scripts/extract_native_oracle.py", "scripts/check_native_oracle.py", "scripts/native_room_textures.py",
    "scripts/prepare_room_visuals.py", "scripts/native_room_revision.py")


def validate_profile(profile):
    if set(profile) != {"inventory", "backpack", "mode", "states"}:
        raise ValueError("Incomplete static profile")
    if profile["states"] != [0, 1, 2, 14] or any(type(state) is not int for state in profile["states"]):
        raise ValueError("Unsupported state profile")
    if type(profile["inventory"]) is not int or profile["inventory"] != 1 or profile["backpack"] is not True or profile["mode"] != "Madeline":
        raise ValueError("Unsupported inventory/sprite profile")


def required_callbacks(callbacks):
    missing = CALLBACKS - callbacks
    if missing:
        raise ValueError("Missing required callbacks: " + ", ".join(sorted(missing)))


def validate_coverage(report):
    traces = report.get("traces", [])
    if len(traces) != 8 or {trace["id"] for trace in traces} != TRACE_IDS:
        raise ValueError("Exactly eight lifecycle traces are required")
    if any(not trace.get("events") for trace in traces):
        raise ValueError("Empty lifecycle events cannot establish coverage")
    if any(trace.get("status") != "source-executed" for trace in traces):
        raise ValueError("Blocked or synthetic lifecycle traces cannot establish closure")
    required_callbacks(set(report.get("callbacks", [])))
    if report.get("coherentLifecycleClosure") is not True:
        raise ValueError("Coherent lifecycle execution has not been proved")


def validate_provenance(receipt, pins):
    sources = receipt.get("sources", [])
    if len(sources) != len(pins) or {entry["file"]: entry["sha256"] for entry in sources} != pins:
        raise ValueError("Source provenance is incomplete or unrecognized")
    identities = receipt.get("inputs", {})
    if set(identities) != {"Celeste.exe", "FNA.dll", "mscorlib.dll"}:
        raise ValueError("Pinned private input inventory changed")
    for name, identity in identities.items():
        digest = identity["sha256"] if isinstance(identity, dict) else identity
        if digest != MEMBERS[name]:
            raise ValueError("Pinned private input identity changed")
    if receipt.get("tool_sha256") != ILSPY_SHA:
        raise ValueError("Pinned ILSpy identity changed")


def prepare(source, output, probe_load_level=False):
    source, output = source.resolve(), output.resolve()
    if not source.is_relative_to(ROOT / ".audit") or not output.is_relative_to(ROOT / ".audit/native-player-death-respawn") or output.exists():
        raise ValueError("Source must be private and output must be fresh below the death gate")
    fixture = ROOT / "tests/native/death-checkpoint.json"
    validate_profile(json.loads(fixture.read_text())["profile"])
    receipt = json.loads((source / "provenance.json").read_text())
    validate_provenance(receipt, EXTRA_PINS)
    presentation = json.loads((source / "presentation/provenance.json").read_text())
    validate_provenance(presentation, PRESENTATION_PINS)
    locations = [source, source / "presentation"]
    for name, expected in SOURCE_PINS.items():
        path = source / name if name in EXTRA_PINS else source / "presentation" / name
        source_block(path.read_bytes(), [], expected)
    output.mkdir(parents=True)
    before = source_state()
    manifest = {"extractions": [], "claim": "Dependency checkpoint, NOT coherent lifecycle closure", "full_load_level_probe": probe_load_level,
        "source_revision": before[0], "source_changes": before[1]}

    def extract(name, ranges):
        path = next((directory / name for directory in locations if (directory / name).is_file()), None)
        if path is None:
            raise ValueError("Missing pinned private source: " + name)
        blocks = source_block(path.read_bytes(), ranges, SOURCE_PINS[name])
        manifest["extractions"].append({"file": name, "source_path": str(path.relative_to(ROOT)), "source_sha256": SOURCE_PINS[name],
            "lines_inclusive": ranges, "blocks_sha256": [hashlib.sha256(block).hexdigest() for block in blocks]})
        return "\n".join(block.decode() for block in blocks)

    def whole(name, namespace):
        path = next(directory / name for directory in locations if (directory / name).is_file())
        lines = path.read_text().splitlines()
        start = next(index + 2 for index, line in enumerate(lines) if line == f"namespace {namespace};")
        return f"namespace {namespace} {{\n" + extract(name, [(start, len(lines))]) + "\n}\n"

    content = "using System; using System.Collections; using System.Collections.Generic; using System.Linq; using System.Reflection; using System.Globalization; using System.Text; using System.Xml; using Microsoft.Xna.Framework; using Microsoft.Xna.Framework.Graphics; using Monocle; using static Monocle.Engine;\n"
    content += "namespace PrivateRuntime {\n" + extract("System.Random.cs", [(7, 144)]) + "\n}\n"
    content += "namespace Microsoft.Xna.Framework { public struct Vector2 : IEquatable<Vector2> {\n" + extract("Microsoft.Xna.Framework.Vector2.cs", [(13, 90), (217, 220), (434, 503)]) + "\n} public struct Color : IEquatable<Color> {\n"
    content += extract("Microsoft.Xna.Framework.Color.cs", [(15, 505), (525, 569), (581, 585), (597, 648)]) + "\n} }\n"
    content += whole("Microsoft.Xna.Framework.MathHelper.cs", "Microsoft.Xna.Framework")
    content += "namespace Microsoft.Xna.Framework { public struct Rectangle {\n" + extract("Microsoft.Xna.Framework.Rectangle.cs", [(13, 29), (62, 68)]) + "\n} }\n"
    content += whole("Microsoft.Xna.Framework.Graphics.SpriteEffects.cs", "Microsoft.Xna.Framework.Graphics")
    for name in ("Sprite", "Image", "SpriteData", "SpriteBank", "Chooser_1", "GraphicsComponent", "SpriteDataSource", "Component", "ComponentList", "Coroutine", "StateMachine", "EntityList", "Tween", "Ease", "RendererList", "Renderer", "TagLists"):
        content += whole("Monocle." + name + ".cs", "Monocle")
    content += "namespace Monocle { public class Tracker {\n" + extract("Monocle.Tracker.cs", [(10, 143), (162, 165), (212, 215), (235, 285)]) + "\n} public partial class Entity {\n"
    content += extract("Monocle.Entity.cs", [(10, 482), (493, 519), (923, 946), (995, 998)]) + "\n} public partial class Scene {\n"
    content += extract("Monocle.Scene.cs", [(10, 28), (32, 43), (63, 91), (126, 129), (810, 830), (839, 847), (892, 913)]) + "\n} }\n"
    for name in ("PlayerSprite", "PlayerHair", "PlayerSpriteMode", "PlayerAnimMetadata", "Facings", "PlayerDeadBody", "DeathEffect", "ScreenWipe", "AngledWipe"):
        content += whole("Celeste." + name + ".cs", "Celeste")
    content += "namespace Monocle { using Random = PresentationOracle.TracedRandom; public static partial class Calc {\n"
    content += extract("Monocle.Calc.cs", [(19, 21), (405, 418), (542, 572), (641, 644), (776, 804), (854, 867), (874, 893), (1017, 1020), (1027, 1030), (1042, 1055), (1222, 1260), (1472, 1517), (1607, 1610), (1696, 1699), (1802, 1805)])
    content += "\n} public partial class Atlas {\n" + extract("Monocle.Atlas.cs", [(24, 40), (310, 313), (324, 376)]) + "\n} public class MTexture {\n"
    content += extract("Monocle.MTexture.cs", [(9, 98), (140, 154), (186, 199), (231, 234)]) + "\n} }\n"
    content += "namespace Celeste { public static class Celeste {\n" + extract("Celeste.Celeste.cs", [(152, 162)]) + "\n} public partial class Player : Entity {\n" + extract("Celeste.Player.cs", [(623, 623), (2855, 2908), (2997, 3005), (6121, 6154)]) + "\n} public partial class Level : Scene {\n"
    content += extract("Celeste.Level.cs", [(1389, 1435), (1642, 1648)]) + "\n} }\n"
    if probe_load_level:
        content += "namespace Celeste { public partial class Level {\n" + extract("Celeste.Level.cs", [(357, 1387)]) + "\n} }\n"
    content += "namespace PresentationOracle { public unsafe partial class OriginalSpriteBatch {\n" + extract("Microsoft.Xna.Framework.Graphics.SpriteBatch.cs", [(128, 130), (335, 361), (744, 784)]) + "\n} }\n"
    content += "namespace Monocle { public sealed class FrameDriver { public Scene scene; public bool DashAssistFreeze; public void Tick() {\n" + extract("Monocle.Engine.cs", [(264, 276)]) + "\n} } }\n"
    (output / "Extracted.cs").write_text(content)
    manifest["extracted_sha256"] = hashlib.sha256(content.encode()).hexdigest()
    support = {"Shared.cs": ROOT / "tests/native/oracle/presentation/Shims.cs", "Geometry.cs": ROOT / "tests/native/oracle/presentation/Geometry.cs",
               "Services.cs": ROOT / "tests/native/oracle/death/Services.cs", "Runner.cs": ROOT / "tests/native/oracle/death/Runner.cs"}
    manifest["support_sha256"] = {}
    for name, path in support.items():
        data = path.read_bytes()
        (output / name).write_bytes(data)
        manifest["support_sha256"][str(path.relative_to(ROOT))] = hashlib.sha256(data).hexdigest()
    manifest["recipe_sha256"] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in RECIPE_FILES}
    manifest["fixture_sha256"] = hashlib.sha256(fixture.read_bytes()).hexdigest()
    manifest["source_provenance_sha256"] = {str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (source / "provenance.json", source / "presentation/provenance.json")}
    (output / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    identity = verify_extraction(output)
    (output / "source-identity.json").write_text(json.dumps(identity, indent=2) + "\n")
    metadata = locations[1]
    for name, member in (("Gameplay.meta", "Content/Graphics/Atlases/Gameplay.meta"), ("Sprites.xml", "Content/Graphics/Sprites.xml")):
        if hashlib.sha256((metadata / name).read_bytes()).hexdigest() != MEMBERS[member]:
            raise ValueError("Pinned sprite metadata changed")
    (output / "atlas.json").write_text(json.dumps(atlas_metadata((metadata / "Gameplay.meta").read_bytes())))
    constants = "DEATH_SOURCE_GATE" + (";PROBE_LOAD_LEVEL" if probe_load_level else "")
    (output / "Oracle.csproj").write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework><UseAppHost>false</UseAppHost><AllowUnsafeBlocks>true</AllowUnsafeBlocks><DefineConstants>' + constants + '</DefineConstants><NuGetAudit>false</NuGetAudit></PropertyGroup></Project>')
    (output / "NuGet.Config").write_text('<configuration><packageSources><clear/></packageSources></configuration>')
    sdk = sdk_path(ROOT)
    commands = []
    for args, log in ((["--version"], "sdk.log"), (["--list-runtimes"], "runtime.log"),
                      (["restore", output / "Oracle.csproj", "--configfile", output / "NuGet.Config"], "restore.log"),
                      (["build", output / "Oracle.csproj", "--no-restore", "-c", "Release", "-p:UseSharedCompilation=false", "--disable-build-servers"], "build.log"),
                      ([output / "bin/Release/net8.0/Oracle.dll", output / "atlas.json", metadata / "Sprites.xml", output, fixture], "execution.log")):
        command = list(map(str, [sdk, *args]))
        with (output / log).open("x") as stream:
            result = subprocess.run(command, cwd=ROOT, env=oracle_environment(sdk), stdout=stream, stderr=subprocess.STDOUT)
        commands.append({"command": command, "exit_code": result.returncode, "log": log})
        (output / "commands-run.json").write_text(json.dumps(commands, indent=2) + "\n")
        if result.returncode:
            raise RuntimeError("Source checkpoint failed: " + str(output / log))
        if log == "sdk.log" and (output / log).read_text().strip() != "8.0.425":
            raise ValueError("Pinned SDK changed")
        if log == "runtime.log" and "Microsoft.NETCore.App 8.0.31 [" not in (output / log).read_text():
            raise ValueError("Pinned runtime changed")
    if source_state() != before:
        raise RuntimeError("Tracked source changed during the dependency checkpoint")
    return identity


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoint-only", action="store_true", help="Run dependency diagnostic only; never claims lifecycle closure")
    parser.add_argument("--probe-load-level", action="store_true", help="Compile the full unchanged LoadLevel body to expose the remaining dependency cut")
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.output, args.probe_load_level), indent=2))
    if not args.checkpoint_only:
        validate_coverage(json.loads((args.output / "checkpoint-result.json").read_text()))
