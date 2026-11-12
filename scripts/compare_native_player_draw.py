"""Read-only Player command comparison; physical cropped pages are not SOURCE sheets."""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from compare_room_transition_contract import require
from native_room_revision import file_identity
from native_room_textures import atlas_metadata
from prepare_room_visuals import MEMBERS
from prepare_static_tilemap import INPUT_SHA, MAP_SHA

SOURCE_IDENTITY = {"bytes": 575248334, "sha256": "8af9703eff54511307b57170bd7bbc98fb8efcd58eb5d7e9ef2e0972ab378073"}
METADATA_IDENTITY = {"bytes": 13992, "sha256": "157b8dd821a79ed59b49834ac068b5edff1ee27b4ea6a8ebc4a5fa09df1697d6"}
SHEETS_IDENTITY = {"bytes": 50, "sha256": "c8ccf3ecb4b7cbe32da5a18de46e7db08d0be90a0acb4c0db1f9e72246258f52"}
FIELDS = ("sheet", "dimensions", "sourceRectangle", "position", "origin", "scale", "rotation", "color")


def logical_frames(text, atlas, sheets):
    lines = iter(text.rstrip("\0").splitlines())
    require([next(lines) for _ in range(3)] == ["CSPP1", INPUT_SHA, MAP_SHA], "Player metadata header changed")
    pages = int(next(lines))
    for _ in range(pages):
        next(lines)
    frames = []
    for _ in range(int(next(lines))):
        name, *fields = next(lines).split()
        values = list(map(int, fields))
        require(len(values) == 13 and name in atlas, "Missing/invalid native frame alias")
        page, u, v, width, height, tx, ty, fw, fh, *_ = values
        sheet, x, y, aw, ah, ax, ay, afw, afh = atlas[name]
        require(0 <= page < pages and [width, height, tx, ty, fw, fh] == [aw, ah, -ax, -ay, afw, afh],
                "Native alias/trim differs from independent atlas metadata: " + name)
        require(sheet in sheets, "Missing logical sheet dimensions")
        frames.append({"name": name, "native": [page, u, v, width, height, tx, ty, fw, fh],
                       "sheet": sheet, "dimensions": sheets[sheet], "sourceRectangle": [x, y, aw, ah]})
    require(len({frame["name"] for frame in frames}) == len(frames), "Duplicate native frame alias")
    return frames


def verified_frames(metadata, atlas, sheets):
    require(file_identity(metadata) == METADATA_IDENTITY, "Frozen native player metadata changed")
    require(file_identity(atlas)["sha256"] == MEMBERS["Content/Graphics/Atlases/Gameplay.meta"], "Pinned atlas changed")
    require(file_identity(sheets) == SHEETS_IDENTITY, "Pinned sheet dimensions changed")
    return logical_frames(metadata.read_text(), atlas_metadata(atlas.read_bytes()), json.loads(sheets.read_text()))


def mapping_text(frames):
    rows = ["CPLAYERDRAW1", str(len(frames))]
    for frame in frames:
        rows.append(" ".join(map(str, [frame["name"], *frame["native"], frame["sheet"],
                                       *frame["dimensions"], *frame["sourceRectangle"]])))
    return "\n".join(rows) + "\n"


def player_blocks(path, native=False):
    blocks, players, dispatches, rosters = {}, {}, {}, {}
    with path.open() as stream:
        for line in stream:
            if native:
                if line.startswith('{"event":"phase"') and '"after-frame"' in line:
                    row = json.loads(line)
                    require(row["tick"] not in players, "Duplicate native after-frame")
                    players[row["tick"]] = row["state"]["player"]
                elif line.startswith('{"event":"player-draw"'):
                    row = json.loads(line)
                    require(row["tick"] not in blocks, "Duplicate native Player block")
                    blocks[row["tick"]] = row
                elif line.startswith('{"event":"draw-owner-roster"'):
                    row = json.loads(line)
                    owners = [owner["identity"] for owner in row["live"] if owner["kind"] == "Player"]
                    require(len(owners) == 1 and row["tick"] not in rosters, "Native roster must have exactly one Player")
                    rosters[row["tick"]] = owners[0]
                elif line.startswith('{"event":"draw-owner-dispatch"'):
                    row = json.loads(line)
                    require(row["tick"] not in dispatches, "Duplicate native dispatch")
                    dispatches[row["tick"]] = row["order"]
            elif line.startswith('{"event":"draw-command"') and '"type":"Player"' in line:
                row = json.loads(line)
                blocks.setdefault(row["tick"], {"commands": []})["commands"].append(row)
            elif not native and line.startswith('{"event":"draw-dispatch"'):
                row = json.loads(line)
                spans = [span for span in row["entities"] if span["type"] == "Player"]
                require(len(spans) == 1 and row["tick"] not in dispatches, "Missing/duplicate SOURCE Player dispatch")
                dispatches[row["tick"]] = spans[0]
    if native:
        require(blocks and set(blocks) == set(players) == set(rosters) == set(dispatches), "Missing native Player command blocks")
        require(len(set(players.values())) == 1, "Tracked native Player was recreated")
        for tick, block in blocks.items():
            require(block["player"] == players[tick] == rosters[tick] and dispatches[tick].count(players[tick]) == 1,
                    "Native commands do not belong to the single tracked/dispatched Player")
    else:
        require(set(blocks) == set(dispatches), "Missing SOURCE Player commands/dispatch")
        for tick, block in blocks.items():
            span = dispatches[tick]
            commands = block["commands"]
            require([command["index"] for command in commands] == list(range(span["drawStart"], span["drawEnd"])),
                    "SOURCE Player command range is incomplete")
            require(all(command["owner"]["entity"] == span["entity"] for command in commands), "SOURCE owner changed")
    return blocks


def float32(value):
    return struct.pack("<f", value)


def same_value(actual, expected):
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(same_value(a, b) for a, b in zip(actual, expected))
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return type(actual) in (int, float) and float32(actual) == float32(expected)
    return actual == expected


def block_differences(tick, source, native, frames):
    commands, expected = native["commands"], source["commands"]
    require(type(native["renderCalls"]) is int and native["renderCalls"] == 1, f"tick {tick}: exactly one real Player render required")
    require(len(commands) == len(expected), f"tick {tick}: Player command count differs")
    require([command["index"] for command in commands] == list(range(len(commands))), f"tick {tick}: command order/index differs")
    differences = []
    for index, (command, oracle) in enumerate(zip(commands, expected)):
        require(type(command["frame"]) is int and 0 <= command["frame"] < len(frames), "Invalid native frame index")
        frame = frames[command["frame"]]
        require(command["frameName"] == frame["name"] and command["nativeFrame"] == frame["native"],
                f"tick {tick}/{index}: frame alias/trim identity differs")
        for key in ("sheet", "dimensions", "sourceRectangle"):
            require(command[key] == frame[key], f"tick {tick}/{index}: logical atlas mapping differs")
        require(command["owner"] == native["player"], f"tick {tick}/{index}: wrong Player owner")
        require(command["componentType"] == oracle["owner"]["componentType"], f"tick {tick}/{index}: component attribution differs")
        for key in FIELDS:
            if not same_value(command[key], oracle[key]):
                differences.append({"index": index, "field": key, "actual": command[key], "expected": oracle[key]})
        require(oracle["effects"] == "None", "Unsupported SOURCE Player effects")
    return differences


def compare_block(tick, source, native, frames):
    differences = block_differences(tick, source, native, frames)
    require(not differences, f"tick {tick}: Player command fields differ: {differences}")
    return len(native["commands"])


def compare(source_path, native_path, frames):
    with source_path.open("rb") as stream:
        identity = {"bytes": source_path.stat().st_size, "sha256": hashlib.file_digest(stream, "sha256").hexdigest()}
    require(identity == SOURCE_IDENTITY, "Immutable SOURCE oracle changed")
    source, native = player_blocks(source_path), player_blocks(native_path, native=True)
    require(sorted(source) == sorted(native) == list(range(514)), "All 514 Player blocks must be present")
    counts = {tick: compare_block(tick, source[tick], native[tick], frames) for tick in (375, 513)}
    failures, passing, mismatched_commands = [], [], 0
    for tick in range(514):
        differences = block_differences(tick, source[tick], native[tick], frames)
        if differences:
            failures.append({"tick": tick, "differences": differences})
            mismatched_commands += len({difference["index"] for difference in differences})
        else:
            passing.append(tick)
    return {"focused_commands": counts, "emitted_blocks": len(native), "passing_ticks": passing, "failures": failures,
            "commands": sum(len(block["commands"]) for block in native.values()),
            "mismatched_commands": mismatched_commands,
            "source": identity, "native": file_identity(native_path),
            "scope": "Player logical command identity/order/float32 fields and component type only; no global spans, vertices, GPU, pixels or Vita"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("metadata", "atlas", "sheets"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--mapping-output", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--native", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    git_dir = subprocess.check_output(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                      cwd=Path(__file__).resolve().parents[1], text=True).strip()
    audit = Path(git_dir).parent / ".audit/native-player-draw-projection-01"
    destination = args.mapping_output or args.output
    require(destination is not None and destination.resolve().is_relative_to(audit) and not destination.exists(),
            "Player draw evidence must be fresh in its canonical private namespace")
    frames = verified_frames(args.metadata, args.atlas, args.sheets)
    if args.mapping_output:
        with args.mapping_output.open("x") as stream:
            stream.write(mapping_text(frames))
    else:
        if not all((args.source, args.native, args.output)):
            parser.error("Comparison requires --source, --native and --output")
        result = compare(args.source, args.native, frames)
        with args.output.open("x") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
        print(json.dumps({key: result[key] for key in ("focused_commands", "emitted_blocks", "commands")}, sort_keys=True))
        if result["failures"]:
            raise SystemExit("Player command mismatches: " + str(len(result["failures"])))


if __name__ == "__main__":
    main()
