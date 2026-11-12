"""Separate original GameplayRenderer command experiment, not Level/GPU closure."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
from xml.sax.saxutils import escape
import zipfile

from binary_map import Reader
from native_room_revision import canonical_digest, file_identity, verify_file_identities
from native_room_textures import atlas_metadata
from prepare_dash_trail_oracle import compile_recording, replace_once
from prepare_full_bake_transition_profile import DRIVER_ID, verify_pinned, verify_source
from prepare_player_presentation_oracle import source_block
from prepare_room_transition_oracle import promote, verify_inputs
from prepare_static_tilemap import MAP_SHA, MEMBER

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = Path("/home/fred/projects/celeste-vita")
AUDIT = ROOT / ".audit/native-room-transition-vita/gameplay-draw-profile-01"
KIND = "native-room-transition-gameplay-draw-v1"
DEFAULT_ARCHIVE = CANONICAL / "game/celeste-linux.zip"
ROOMS_ID = {"bytes": 15518, "sha256": "b5c5814db9cb0084099a552d38890887f9f9602a97d86d99f07969e79602809f"}
LAYER_PINS = [
    ("03c27b1db4fe92fd6abba3580c98b8af0275d8c053184f033339f292f5f548f4",
     "3c304b7899a03f801bad23c8d869327a46386f3f19085b510e748fa965e68839"),
    ("55512dbe35005ea53820b717b98e1e68adde2e70bd8436dd47423846fcd50a4c",
     "71684dd2136d13680c969e832cb5d3e7ccb942ebff412350c2189292c15bd12e"),
]
EMPTY_OBJECT_SHA = "6b45c5409127d1574cdfc08ad849f384dc2b62b432bc7b297f0b7f70ee33626f"
DECAL_ROOT = CANONICAL / ".audit/native-first-room-decals/source-discovery-f4/il"
DRAW_ROOT = CANONICAL / ".audit/native-room-transition-vita/draw-source-closure-01"
GAMEPLAY_SOURCE = CANONICAL / ".audit/native-room-visuals/source-closure-01/Celeste.GameplayRenderer.cs"
GRAPHICS_SOURCE = CANONICAL / ".audit/native-player-presentation/correction-preflight/source/Monocle.GraphicsComponent.cs"
LEGACY = Path("/tmp/opencode/celeste-vita-death-source-up/.audit/native-player-death-respawn")


def room_contract(rooms):
    encoded = (json.dumps(rooms, sort_keys=True) + "\n").encode()
    if {"bytes": len(encoded), "sha256": hashlib.sha256(encoded).hexdigest()} != ROOMS_ID:
        raise ValueError("Pinned authored room schema/content/order changed")
    result = []
    for room, pins, counts in zip(rooms, LAYER_PINS, [(4, 25, 22, 7), (5, 18, 19, 4)]):
        layers = {layer["name"]: layer for layer in room["children"]}
        for name, sha in zip(("fgdecals", "bgdecals", "objtiles"), (*pins, EMPTY_OBJECT_SHA)):
            if hashlib.sha256(json.dumps(layers[name], sort_keys=True).encode()).hexdigest() != sha:
                raise ValueError("Pinned authored room layer changed: " + name)
        result.append({"room": room["attributes"]["name"], "fg": counts[0], "bg": counts[1],
                       "static": counts[2], "banners": counts[3], "object_csv": "authored-empty-no-innerText",
                       "layers": dict(zip(("fgdecals", "bgdecals", "objtiles"), (*pins, EMPTY_OBJECT_SHA)))})
    return result


def authored_rooms(archive):
    with zipfile.ZipFile(archive) as package:
        data = package.read(MEMBER)
    if hashlib.sha256(data).hexdigest() != MAP_SHA:
        raise ValueError("Pinned original map member changed")
    _, raw = Reader(data).map()
    rooms = [room for room in next(child["children"] for child in raw["children"] if child["name"] == "levels")
             if room["attributes"]["name"] in ("lvl_1", "lvl_2")]
    return rooms, room_contract(rooms)


def validate_profile(record):
    if type(record.get("schema")) is not int or record.get("schema") != 1 or record.get("kind") != KIND:
        raise ValueError("Expected separate gameplay-DRAW profile kind/version")
    if record.get("binding") != canonical_digest({key: value for key, value in record.items() if key != "binding"}):
        raise ValueError("Gameplay-DRAW provenance binding changed")
    if record.get("rooms") != ROOMS_ID or record.get("terrain_driver") != DRIVER_ID:
        raise ValueError("Gameplay-DRAW authored rooms or terrain changed")
    if record.get("claim") != "Original GameplayRenderer commands only; not full Level rendergraph, GPU, pixels or Vita":
        raise ValueError("Gameplay-DRAW scope changed")


def verify_profile(profile):
    record = json.loads((profile / "transition-profile.json").read_text())
    validate_profile(record)
    if record["profile_directory"] != str(profile.resolve()) or not profile.resolve().is_relative_to(AUDIT):
        raise ValueError("Gameplay-DRAW profile path/content mismatch")
    verify_inputs(record["inputs"], record["compiled_sources"])
    for group in ("generated", "compiled_artifacts"):
        verify_file_identities({str(profile / name): value for name, value in record[group].items()})
    return record


def promote_sources(text, inputs):
    spans = []

    def blocks(path, sha, ranges):
        values = [block.decode() for block in source_block(path.read_bytes(), ranges, sha)]
        inputs[str(path)] = file_identity(path)
        spans.append({"path": str(path), "sha256": sha, "ranges": ranges,
                      "blocks_sha256": [hashlib.sha256(value.encode()).hexdigest() for value in values]})
        return values

    def members(path, sha, ranges, start=None, end=None):
        nonlocal text
        values = blocks(path, sha, ranges)
        begin = text.index(start) if start else 0
        stop = text.index(end, begin) if end else len(text)
        selected = text[begin:stop]
        for value in values:
            if selected.count(value) != 1:
                if "(" not in value.split("\n", 1)[0] and "\n\t\tget\n" in value:
                    signature = value.split("\n", 1)[0].strip()
                    guard = r'\{ throw new DeathOracle.UnsupportedClosure\("Excluded source member: [^"\n]+/' + re.escape(path.name) + r':[^"\n]+"\); \}'
                    pattern = re.escape(signature) + r'\s*\{\s*get\s*' + guard + r'\s*set\s*' + guard + r'\s*\}'
                    selected, count = re.subn(pattern, lambda _: value, selected)
                    if count != 1:
                        raise ValueError("Missing original guarded property: " + signature)
                elif re.search(r"\n\t{3}: ", value):
                    prefix = value.split("{", 1)[0].strip()
                    pattern = re.escape(prefix) + r'\s*\{ throw new DeathOracle.UnsupportedClosure\("Excluded source member: [^"\n]+/' + re.escape(path.name) + r':[^"\n]+"\); \}'
                    selected, count = re.subn(pattern, lambda _: value, selected)
                    if count != 1:
                        raise ValueError("Missing original guarded nested constructor: " + prefix)
                else:
                    selected = promote(selected, value, path.name)
        text = text[:begin] + selected + text[stop:]

    gameplay_sha = "294faa1e6e9b7bb5b83429b5da32d19b7ced485bf5354cf4a51b6c97c5aa4931"
    members(GAMEPLAY_SOURCE, gameplay_sha, [(12, 16), (18, 21), (23, 32), (34, 37)])
    members(GRAPHICS_SOURCE, "7aea400b2428df2708b31c844f0dd15b797c419a4a63f945a473127ab3c4c210", [(85, 88), (90, 108)])
    decal = DECAL_ROOT / "Celeste.Decal.cs"
    decal_sha = "81d04a56cb9b5cb981f3c7823388bed6082db2d5755d364c15c35bbcaf8b7746"
    members(decal, decal_sha, [(34, 34), (36, 39), (41, 55), (57, 67)], "private class Banner :", "private class DecalImage :")
    members(decal, decal_sha, [(72, 72), (74, 77), (79, 82)], "private class DecalImage :", "private class FinalFlagDecalImage :")
    members(decal, decal_sha, [(152, 161), (163, 370), (372, 395), (505, 529), (531, 546)], "public Decal(string texture", "public void FinalFlagTrigger")
    members(LEGACY / "room-core-probe-46/source/Celeste.Spring.cs", "36a931e162387df599b88df84d851541be25001d24a5114084c6d06c461939d7", [(190, 197)])
    members(CANONICAL / ".audit/private-push-20261111/committed-preparation/player-sources/Celeste.Spikes.cs",
            "fb485592822286d316d93fe029acf92b83e4a0b119492dd3d2fa77f6b5e11901", [(199, 205)])
    members(LEGACY / "source-synced-6b-01/Monocle.Engine.cs", "ee6c3a4d8f6ff9fb6fcf5e45cc9710b0f038023ee9484ec1837f619ffe385f45", [(56, 56)])
    members(LEGACY / "room-core-probe-75/source/Microsoft.Xna.Framework.Graphics.DepthStencilState.cs",
            "8b8cc9497f161e0105062d9119b9347d3ab9984fc117dc750f518d7e194f318f",
            [(start, start + 10) for start in range(13, 194, 12)] + [(205, 223), (225, 231)])
    members(LEGACY / "room-core-probe-59/source/Microsoft.Xna.Framework.Graphics.RasterizerState.cs",
            "2b911305fa86fb1b1d83e17b38f77b80a53a8869c289bab3c47e0dc20f5fe5ac",
            [(start, start + 10) for start in range(13, 74, 12)] + [(85, 93), (95, 100)])
    image = DRAW_ROOT / "Monocle.Image.cs"
    for value in blocks(image, "aa87a22589821fc3781672126e68f2195fb46348f261013d8a01c070b53821d3", [(27, 33)]):
        if text.count(value) != 1:
            raise ValueError("Existing original Image.Render span changed")
    return text, spans


def observe_dispatch(text):
    for start, end, call, before, after in [
        ("public void RenderExcept(int excludeTags)", "public void DebugRender(Camera camera)", "entity.Render();",
         "DeathOracle.GameplayDrawProfile.EnterEntity(entity);", "DeathOracle.GameplayDrawProfile.ExitEntity(entity);"),
        ("internal void Render()", "internal void DebugRender(Camera camera)", "component.Render();",
         "DeathOracle.GameplayDrawProfile.EnterComponent(component);", "DeathOracle.GameplayDrawProfile.ExitComponent(component);"),
    ]:
        begin = text.index(start)
        stop = text.index(end, begin)
        original = text[begin:stop]
        observed = replace_once(original, call, before + "\n\t\t\t\t" + call + "\n\t\t\t\t" + after)
        if observed.replace(before + "\n\t\t\t\t", "").replace("\n\t\t\t\t" + after, "") != original:
            raise ValueError("Read-only dispatch observation changed SOURCE statements")
        text = text[:begin] + observed + text[stop:]
    return text


def prepare(profile, source_recheck, driver, archive, sdk, output):
    if output.exists() or not output.resolve().is_relative_to(AUDIT):
        raise ValueError("Gameplay-DRAW output must be fresh beneath its separate private namespace")
    source, inputs = verify_source(profile, source_recheck)
    if str(sdk) not in source["inputs"]:
        raise ValueError("Only the existing pinned SOURCE SDK is authorized")
    verify_pinned(sdk, source["inputs"][str(sdk)], "SOURCE SDK")
    verify_pinned(driver, DRIVER_ID, "full-terrain driver")
    loader = CANONICAL / ".audit/private-push-20261111/committed-preparation/visual-sources/Celeste.LevelLoader.cs"
    loader_sha = "b35b6f5c0479b0eccaf5d5a1c6affaca388c6733a585248b910208a354c6af7f"
    loader_ranges = [(44, 56), (75, 77)]
    loader_blocks = source_block(loader.read_bytes(), loader_ranges, loader_sha)
    inputs[str(loader)] = file_identity(loader)
    rooms, layers = authored_rooms(archive)
    originals = {Path(path).name: Path(path) for path in source["compiled_sources"]}
    extracted, spans = promote_sources(originals["TransitionExtracted.cs"].read_text(), inputs)
    frozen_ranges = [(2445, 2456), (2835, 2835), (2912, 2916), (3104, 3113), (4097, 4147), (11572, 11621), (15344, 15398)]
    frozen_sha = inputs[str(originals["TransitionExtracted.cs"])]["sha256"]
    frozen_blocks = source_block(originals["TransitionExtracted.cs"].read_bytes(), frozen_ranges, frozen_sha)
    if any(extracted.count(block.decode()) != 1 for block in frozen_blocks):
        raise ValueError("Existing original renderer/entity/hair span changed")
    extracted = observe_dispatch(extracted)
    caller = replace_once(originals["TransitionCaller.cs"].read_text(), '"53ddd1071bac512856a436769f7c40b40084cc629887b9e01d07025422f397a8"', json.dumps(ROOMS_ID["sha256"]))
    caller = replace_once(caller, "level.Camera = new Camera(1920, 1080);", "level.GameplayRenderer = new GameplayRenderer();\n        level.Camera = level.GameplayRenderer.Camera;")
    caller = replace_once(caller, "1920x1080-declared-display-profile", "320x180-original-GameplayRenderer-camera-alias")
    execution = replace_once(originals["TransitionExecution.cs"].read_text(), 'Path.GetFullPath(".audit/native-room-transition/source-contract-01")', 'Path.GetFullPath(' + json.dumps(str(AUDIT)) + ')')
    observer = replace_once(originals["TransitionProfile.cs"].read_text(), "RoomCoreTileBake.Build(probe.Level, probe.Level.Session.MapData);", "probe.Write(FullBakeProfile.Build(probe.Level));")
    observer = replace_once(observer, "using var probe = new Probe(args, 0);", "GameplayDrawProfile.RegisterSheets();\n        using var probe = new Probe(args, 0);")
    observer = replace_once(observer, 'graphics = "not rendered"', 'graphics = "original GameplayRenderer command-only; not Level/GPU closure"')
    observer = replace_once(observer, 'phase = "after-frame";', 'phase = "before-draw";\n                    probe.Write(new { @event = "draw-state", tick, phase, state = State() });\n                    GameplayDrawProfile.Render(level, tick, probe.Write);\n                    phase = "after-draw";\n                    probe.Write(new { @event = "draw-state", tick, phase, state = State() });\n                    phase = "after-frame";')
    with zipfile.ZipFile(archive) as package:
        sheets = {}
        atlas_members = {}
        for label, filename in (("Gameplay", "atlas.json"), ("Gui", "gui-atlas.json")):
            member = "Content/Graphics/Atlases/" + label + ".meta"
            data = package.read(member)
            metadata = atlas_metadata(data)
            cached = json.loads((originals["Shared.cs"].parent / filename).read_text())
            if metadata != {key: tuple(value) for key, value in cached.items()}:
                raise ValueError("Loaded SOURCE atlas metadata differs from original archive: " + label)
            atlas_members[member] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name in sorted({entry[0] for entry in metadata.values()}):
                member = "Content/Graphics/Atlases/" + name + ".data"
                with package.open(member) as stream:
                    header = stream.read(9)
                width, height, alpha = struct.unpack("<iiB", header)
                if not 0 < width <= 4096 or not 0 < height <= 4096 or alpha not in (0, 1):
                    raise ValueError("Invalid real atlas sheet header: " + name)
                sheets[name] = [width, height]
                atlas_members[member] = {"bytes": package.getinfo(member).file_size, "header_hex": header.hex(),
                                         "dimensions": [width, height], "identity": "bound by original archive input SHA256"}
    generated = {"TransitionExtracted.cs": extracted, "TransitionCaller.cs": caller, "TransitionExecution.cs": execution,
                 "TransitionProfile.cs": observer, "two-rooms.json": json.dumps(rooms, sort_keys=True) + "\n",
                 "full-bake-input.json": json.dumps({"driver": str(driver), "rooms": str(output / "two-rooms.json")}) + "\n",
                 "sheets.json": json.dumps(sheets) + "\n"}
    files = [str(output / Path(path).name) if Path(path).name in generated else path
             for path in source["compiled_sources"] if Path(path).name != "Shared.cs"]
    files += [str(ROOT / "tests/native/oracle/transition" / name) for name in ("DrawRecording.cs", "FullBakeProfile.cs", "GameplayDrawProfile.cs")]
    output.mkdir(parents=True)
    for directory in ("home", "tmp"):
        (output.parent / directory).mkdir(exist_ok=True)
    for name, text in generated.items():
        (output / name).write_text(text)
    (output / "Oracle.csproj").write_text('<Project><ItemGroup>' + ''.join('<Compile Include="' + escape(path) + '"/>' for path in files) + '</ItemGroup></Project>')
    dependencies = ("run_room_transition_probe.py", "compare_gameplay_draw_contract.py", "prepare_full_bake_transition_profile.py",
                    "prepare_room_transition_oracle.py", "prepare_dash_trail_oracle.py", "prepare_player_presentation_oracle.py",
                    "prepare_static_tilemap.py", "native_room_revision.py", "native_room_textures.py", "binary_map.py")
    for path in (Path(__file__).resolve(), *[ROOT / "scripts" / name for name in dependencies], driver, archive, *map(Path, files)):
        if path.parent != output:
            inputs[str(path)] = file_identity(path)
    compile_recording(output, sdk)
    command = json.loads((output / "compiler-command.json").read_text())
    for path in [Path(command[0]), Path(command[1]), *[Path(value[3:]) for value in command if value.startswith("-r:")]]:
        inputs[str(path)] = file_identity(path)
    record = {"schema": 1, "kind": KIND, "profile_directory": str(output.resolve()), "rooms": ROOMS_ID,
              "terrain_driver": DRIVER_ID, "authored_layers": layers, "original_spans": spans,
              "atlas_members": atlas_members,
              "camera_alias": {"source": str(loader), "sha256": loader_sha, "ranges": loader_ranges,
                               "blocks_sha256": [hashlib.sha256(block).hexdigest() for block in loader_blocks],
                               "execution": "Owned isolated caller binds actual original GameplayRenderer.Camera; full LevelLoader is not executed"},
              "frozen_original_spans": {"path": str(originals["TransitionExtracted.cs"]), "sha256": frozen_sha,
                                        "ranges": frozen_ranges, "blocks_sha256": [hashlib.sha256(block).hexdigest() for block in frozen_blocks]},
              "inputs": inputs, "compiled_sources": files,
              "generated": {name: file_identity(output / name) for name in (*generated, "Oracle.csproj")},
              "compiled_artifacts": {name: file_identity(output / name) for name in ("Oracle.dll", "Oracle.runtimeconfig.json", "compiler-command.json")},
              "dispatch_observation": "Read-only before/after hooks around unchanged entity/component Render statements; original visibility/HUD/order untouched",
              "original_payload_copies": [], "claim": "Original GameplayRenderer commands only; not full Level rendergraph, GPU, pixels or Vita"}
    record["binding"] = canonical_digest(record)
    (output / "transition-profile.json").write_text(json.dumps(record, indent=2) + "\n")
    verify_profile(output)
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("profile", "source-recheck", "driver", "archive", "sdk", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    record = prepare(*(getattr(args, name).resolve() for name in ("profile", "source_recheck", "driver", "archive", "sdk", "output")))
    print(json.dumps({"kind": record["kind"], "binding": record["binding"]}))
