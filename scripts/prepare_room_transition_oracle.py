"""Build an isolated, fail-closed two-room original-source experiment offline."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import os
import subprocess
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
import zipfile

from binary_map import Reader
from native_room_revision import file_identity, verify_file_identities
from native_oracle_sdk import sdk_path
from prepare_dash_trail_oracle import compile_recording, replace_guard, replace_once
from prepare_player_presentation_oracle import source_block
from prepare_static_tilemap import MAP_SHA, MEMBER
from prepare_room_visuals import MEMBERS
from read_player_presentation_sources import ILSPY_SHA

ROOT = Path(__file__).resolve().parents[1]
ACCEPTED_SHA = "d13bc82b7b6d539ecc5453785cf5b5de5d2b72992b3b371647c0da429b9edb5c"
MANIFEST_SHA = "5838d2b32d8d99dac63e1dd5005c72a1af7f9e7b98288e51e7ae3686c83f3cb6"
GUARD_SHA = "7c21049f7d7994f146bd87f86b7887b4fc2afd636f3d9063ea4002efefc6e928"
RANGES = {
    "Celeste.Level.cs": [(1486, 1490), (1492, 1640), (2849, 2861), (2945, 2954)],
    "Celeste.Player.cs": [(2282, 2291), (2293, 2308), (2850, 2853), (3870, 3880), (3882, 3909), (3911, 3924),
                          (3926, 4104), (4106, 4120), (4122, 4144), (4146, 4154), (4156, 4177), (4179, 4189)],
    "Monocle.VirtualJoystick.cs": [(71, 233)],
    "Monocle.Calc.cs": [(895, 898)],
    "Celeste.LedgeBlocker.cs": [(20, 31), (33, 44)],
    "Monocle.Scene.cs": [(30, 30)],
    "Monocle.Tracker.cs": [(217, 220)],
    "Celeste.JumpthruPlatform.cs": [(14, 21), (23, 26), (28, 83)],
    "Celeste.Spring.cs": [(30, 95), (97, 100)],
    "Celeste.Strawberry.cs": [(57, 57), (59, 59), (61, 61), (80, 109), (111, 174), (176, 262), (274, 296)],
    "Celeste.SaveData.cs": [(346, 360), (404, 407), (409, 412)],
    "Celeste.HoldableCollider.cs": [(13, 18)],
    "Monocle.Entity.cs": [(583, 595), (597, 604)],
}


def mechanical_rooms(rooms):
    selected = [room for room in rooms if room["attributes"]["name"] in ("lvl_1", "lvl_2")]
    if [room["attributes"]["name"] for room in selected] != ["lvl_1", "lvl_2"]:
        raise ValueError("Expected exactly the authored first two rooms in source order")
    selected = copy.deepcopy(selected)
    exclusions = []
    for room in selected:
        for layer in room["children"]:
            if layer["name"] in ("fgdecals", "bgdecals", "objtiles"):
                exclusions.append({"room": room["attributes"]["name"], "layer": layer["name"],
                                   "sha256": hashlib.sha256(json.dumps(layer, sort_keys=True).encode()).hexdigest()})
                layer["children"] = []
                if "innerText" in layer["attributes"]:
                    layer["attributes"]["innerText"] = ""
    return selected, exclusions


def promote(text, original, name):
    if "{ get; private set; }" in original:
        signature = original.split("{", 1)[0].strip()
        prop = signature.rsplit(" ", 1)[1]
        guard = r'\{ throw new DeathOracle.UnsupportedClosure\("Excluded source member: [^"\n]+/' + re.escape(name) + ":" + re.escape(prop)
        pattern = re.escape(signature) + r' \{ get' + guard + r'\.get"\); \}private set' + guard + r'\.set"\); \}\}'
        text, count = re.subn(pattern, lambda _: original, text)
        if count != 1:
            raise ValueError("Missing original guarded auto property: " + signature)
        return text
    if "=>" in original.split("\n", 1)[0]:
        signature = original.split("=>", 1)[0].strip()
        pattern = re.escape(signature) + r'\s*=> throw new DeathOracle.UnsupportedClosure\("Excluded source accessor: [^"\n]+/' + re.escape(name) + r':[^"\n]+"\);'
        text, count = re.subn(pattern, lambda _: original, text)
        if count != 1:
            raise ValueError("Missing original guarded expression member: " + signature)
        return text
    if "\n\t\t: " in original:
        prefix = original.split("{", 1)[0].strip()
        pattern = re.escape(prefix) + r'\s*\{ throw new DeathOracle.UnsupportedClosure\("Excluded source member: [^"\n]+/' + re.escape(name) + r':[^"\n]+"\); \}'
        text, count = re.subn(pattern, lambda _: original, text)
        if count != 1:
            raise ValueError("Missing original guarded constructor: " + prefix)
        return text
    return replace_guard(text, original, name)


def verify_inputs(inputs, compiled_sources=()):
    guards = [path for path in compiled_sources if Path(path).name == "NativeImportGuard.cs"]
    if len(guards) != 1 or guards[0] not in inputs or inputs[guards[0]].get("sha256") != GUARD_SHA:
        raise ValueError("NativeImportGuard must be bound to the generated assembly")
    verify_file_identities(inputs)


def generate(accepted, manifest_path, legacy_root, archive, output, sdk):
    if output.exists() or not output.resolve().is_relative_to(ROOT / ".audit/native-room-transition/source-contract-01"):
        raise ValueError("Output must be fresh beneath the private transition experiment")
    if file_identity(manifest_path)["sha256"] != MANIFEST_SHA:
        raise ValueError("Accepted source8 manifest identity changed")
    canonical = archive.parent.parent
    if sdk != sdk_path(canonical):
        raise ValueError("Only the existing host-resolved canonical SDK is authorized")
    manifest = json.loads(manifest_path.read_text())
    extracted = (accepted / "Extracted.cs").read_text()
    if hashlib.sha256(extracted.encode()).hexdigest() != ACCEPTED_SHA or manifest["extracted_sha256"] != ACCEPTED_SHA:
        raise ValueError("Accepted source8 extraction identity changed")
    inputs = {str(manifest_path): file_identity(manifest_path)}
    spans = []

    def original(name, ranges):
        entry = next((entry for entry in manifest["extractions"] if entry["file"] == name), None)
        if entry:
            path = legacy_root / entry["source_path"]
            sha = entry["source_sha256"]
        else:
            entry = next(entry for group in ("executable_members", "declaration_contracts") for entry in manifest[group]
                         if Path(entry["File"]).name == name)
            path, sha = Path(entry["File"]), entry["SourceSha256"]
        blocks = source_block(path.read_bytes(), ranges, sha)
        inputs[str(path)] = file_identity(path)
        spans.append({"file": name, "source": str(path), "source_sha256": sha, "ranges": ranges,
                      "blocks_sha256": [hashlib.sha256(block).hexdigest() for block in blocks]})
        return [block.decode() for block in blocks]

    for name, ranges in RANGES.items():
        for member in original(name, ranges):
            extracted = promote(extracted, member, name)
    extracted = promote(extracted, original("Monocle.VirtualJoystick.cs", [(43, 43)])[0], "Monocle.VirtualJoystick.cs")
    with zipfile.ZipFile(archive) as source:
        data = source.read(MEMBER)
    if hashlib.sha256(data).hexdigest() != MAP_SHA:
        raise ValueError("Pinned original map member changed")
    _, raw = Reader(data).map()
    rooms, exclusions = mechanical_rooms(next(child["children"] for child in raw["children"] if child["name"] == "levels"))
    room_json = json.dumps(rooms, sort_keys=True) + "\n"
    room_sha = hashlib.sha256(room_json.encode()).hexdigest()
    caller = (accepted / "RoomCoreCaller.cs").read_text()
    caller = replace_once(caller, 'Path.Combine(directory, "presentation-stripped-room.json")',
                          'Path.Combine(TransitionProfile.DataRoot, "two-rooms.json")')
    caller = replace_once(caller, '"33cd5d93e1262aec2748cb02ffe1354b1bf46e992de2d49d6c60f4fb3b8fc076"', json.dumps(room_sha))
    caller = replace_once(caller, "var room = new LevelData(RoomCoreRoomInput.ReadElement(input.RootElement));",
                          "var rooms = input.RootElement.EnumerateArray().Select(element => new LevelData(RoomCoreRoomInput.ReadElement(element))).ToList();\n        var room = rooms[0];")
    caller = replace_once(caller, "map.Levels = new List<LevelData> { room };", "map.Levels = rooms;")
    caller = replace_once(caller, 'room.Entities.Where(entity => entity.Name == "strawberry")', 'rooms.SelectMany(value => value.Entities).Where(entity => entity.Name == "strawberry")')
    caller = replace_once(caller, 'room.Entities.Where(entity => entity.Name == "goldenBerry")', 'rooms.SelectMany(value => value.Entities).Where(entity => entity.Name == "goldenBerry")')
    caller = replace_once(caller, "map.DetectedStrawberries = room.Strawberries;", "map.DetectedStrawberries = rooms.Sum(value => value.Strawberries);")
    caller = replace_once(caller, "single-room-header-not-complete-world-caller", "two-room-header-not-complete-world-caller")
    caller = replace_once(caller, "map.Bounds = room.Bounds;", "map.Bounds = new Rectangle(-64, -248, 688, 492);")
    execution = (accepted / "RoomCoreExecution.cs").read_text()
    execution = replace_once(execution, 'string root = Path.GetFullPath(".audit/native-player-death-respawn") + Path.DirectorySeparatorChar;',
                             'string root = Path.GetFullPath(".audit/native-room-transition/source-contract-01") + Path.DirectorySeparatorChar;')
    execution = replace_once(execution, "Content = Path.GetDirectoryName(path);", "Content = " + json.dumps(str(accepted)) + ";")
    execution = replace_once(execution, 'static string Identity(object value) => value == null ? null : value.GetType().Name + "#" + RuntimeHelpers.GetHashCode(value);',
                             'static string Identity(object value) => TransitionObserver.Identity(value);')
    engine = original("Monocle.Engine.cs", [(264, 272), (273, 273), (274, 274), (275, 276)])
    observed_driver = ('using System; using static Monocle.Engine; namespace Monocle { public sealed class TransitionFrameDriver { public Scene scene; public bool DashAssistFreeze; '
                       'public Action<string> Observe; public void Tick() {\n' + engine[0] + '\nObserve("before-update");\n'
                       + engine[1] + '\nObserve("before-eof");\n' + engine[2] + '\nObserve("after-eof");\n' + engine[3] + '\n} } }\n')
    output.mkdir(parents=True)
    tool = canonical / ".audit/ilspy/tools/ilspycmd-9.1.0.7988/tools/net8.0/any/ilspycmd.dll"
    assembly = canonical / ".audit/ilspy/inputs/Celeste.exe"
    if file_identity(tool)["sha256"] != ILSPY_SHA or file_identity(assembly)["sha256"] != MEMBERS["Celeste.exe"]:
        raise ValueError("Pinned offline decompiler or source assembly changed")
    command = list(map(str, [sdk, tool, "--disable-updatecheck", "-r", assembly.parent, "-t", "Celeste.PufferCollider", assembly]))
    for directory in ("home", "tmp"):
        (output / directory).mkdir()
    result = subprocess.run(command, capture_output=True, check=True, timeout=120,
                            env=dict(os.environ, HOME=str(output / "home"), TMPDIR=str(output / "tmp"), DOTNET_EnableDiagnostics="0"))
    puffer_sha = "2b64110efb8286ccbf46bdf0f7116760d3744372079649f74bfe302556833412"
    puffer = source_block(result.stdout, [(6, 18), (20, 20)], puffer_sha)
    puffer_text = "namespace Celeste {\n" + puffer[0].decode() + "\n" + puffer[1].decode() + '\n{ throw new DeathOracle.UnsupportedClosure("Excluded source member: Celeste.PufferCollider.Check"); }\n}\n}\n'
    extracted += "\n" + puffer_text
    inputs[str(tool)] = file_identity(tool)
    inputs[str(assembly)] = file_identity(assembly)
    inputs[str(sdk)] = file_identity(sdk)
    generated = {"TransitionExtracted.cs": extracted, "TransitionExecution.cs": execution, "TransitionCaller.cs": caller,
                 "TransitionDriver.cs": observed_driver}
    combined = "\n".join(generated.values())
    for span in spans:
        blocks = source_block(Path(span["source"]).read_bytes(), span["ranges"], span["source_sha256"])
        if any(block.decode() not in combined for block in blocks):
            raise ValueError("Original promoted source span is not byte-identical: " + span["file"])
    if any(block.decode() not in combined for block in puffer):
        raise ValueError("Additional pinned constructor/declaration span changed")
    for name, text in generated.items():
        (output / name).write_text(text)
    (output / "two-rooms.json").write_text(room_json)
    omitted = {"Extracted.cs", "RoomCoreExecution.cs", "RoomCoreCaller.cs"}
    files = [output / name for name in generated]
    files += [accepted / item.attrib["Include"] for item in ET.parse(accepted / "Oracle.csproj").findall(".//Compile")
              if item.attrib["Include"] not in omitted]
    files.append(ROOT / "tests/native/oracle/transition/TransitionProfile.cs")
    files.append(ROOT / "tests/native/oracle/transition/TransitionObserver.cs")
    for path in (Path(__file__), ROOT / "scripts/run_room_transition_probe.py", ROOT / "scripts/compare_room_transition_contract.py",
                 ROOT / "scripts/prepare_dash_trail_oracle.py", ROOT / "scripts/prepare_player_presentation_oracle.py",
                 accepted / "Oracle.csproj", accepted / "Extracted.cs", accepted / "RoomCoreExecution.cs", accepted / "RoomCoreCaller.cs",
                 accepted / "atlas.json", accepted / "gui-atlas.json", accepted / "Sprites.xml", *files):
        if path.parent != output:
            inputs[str(path)] = file_identity(path)
    verify_inputs(inputs, list(map(str, files)))
    project = ('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework>'
               '<UseAppHost>false</UseAppHost><AllowUnsafeBlocks>true</AllowUnsafeBlocks><EnableDefaultCompileItems>false</EnableDefaultCompileItems>'
               '<StartupObject>DeathOracle.RoomCoreExecution</StartupObject><DefineConstants>DEATH_SOURCE_GATE;GRID_ORACLE</DefineConstants>'
               '</PropertyGroup><ItemGroup>' + ''.join('<Compile Include="' + escape(str(path)) + '"/>' for path in files) + '</ItemGroup></Project>')
    (output / "Oracle.csproj").write_text(project)
    record = {"schema": 1, "status": "experiment-not-transition-acceptance", "inputs": inputs, "original_spans": spans,
              "compiled_sources": list(map(str, files)),
              "additional_source": {"type": "Celeste.PufferCollider", "assembly": str(assembly), "source_sha256": puffer_sha,
                                    "command": command, "selected_ranges": [[6, 18], [20, 20]],
                                    "blocks_sha256": [hashlib.sha256(block).hexdigest() for block in puffer],
                                    "policy": "In-memory pinned decompilation; only transformed class/fields/constructor plus guarded Check emitted. No raw original source or DLL copy."},
              "generated": {name: file_identity(output / name) for name in (*generated, "two-rooms.json", "Oracle.csproj")},
              "map_member": MEMBER, "map_sha256": MAP_SHA, "presentation_exclusions": exclusions,
              "driver_observation": "Original Engine.cs264-276 freeze/Scene phase fragment, split only by read-only observations after each original phase. AfterUpdate invokes the unchanged deferred EOF delegate. No original gameplay method body changed.",
              "claim": "Original source8 plus isolated original transition roots. Unsupported dependencies still throw. No two-room closure, route, native product, GPU or physical claim."}
    (output / "transition-profile.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("accepted", "manifest", "legacy-root", "archive", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--sdk", type=Path, required=True)
    args = parser.parse_args()
    generate(*(getattr(args, name).resolve() for name in ("accepted", "manifest", "legacy_root", "archive", "output", "sdk")))
    compile_recording(args.output.resolve(), args.sdk.resolve())
    record_path = args.output / "transition-profile.json"
    record = json.loads(record_path.read_text())
    record["compiled_artifacts"] = {name: file_identity(args.output / name)
                                    for name in ("Oracle.dll", "Oracle.runtimeconfig.json", "compiler-command.json")}
    record_path.write_text(json.dumps(record, indent=2) + "\n")
    print("Generated private, fail-closed transition experiment:", args.output)
