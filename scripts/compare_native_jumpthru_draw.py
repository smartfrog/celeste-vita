"""Read-only bounded JumpThru logical comparison. SOURCE trace never feeds production initialization."""
import argparse
import json
from pathlib import Path

from compare_native_player_draw import FIELDS, SOURCE_IDENTITY, same_value
from native_room_revision import file_identity
from prepare_static_decal_descriptors import require

SOURCE_ENTITY = "JumpthruPlatform#151"
SOURCE_COMPONENTS = tuple("Image#" + str(index) for index in range(195, 200))
SEMANTIC_OWNER = ("2", 7)
SOURCE_ROOMS = Path("/home/fred/projects/celeste-vita-worktrees/native-room-transition/.audit/native-room-transition"
                    "/source-contract-01/frozen-profile-02/two-rooms.json")
ROOMS_IDENTITY = {"bytes": 8415, "sha256": "53ddd1071bac512856a436769f7c40b40084cc629887b9e01d07025422f397a8"}


def verify_source_binding(path=SOURCE_ROOMS):
    require(file_identity(path) == ROOMS_IDENTITY, "Independent SOURCE authored rooms changed")
    rooms = json.loads(path.read_text())
    room = next(room for room in rooms if room["attributes"]["name"] == "lvl_2")
    entities = next(child["children"] for child in room["children"] if child["name"] == "entities")
    platforms = [entity["attributes"] for entity in entities if entity["name"] == "jumpThru"]
    require(len(platforms) == 1, "Independent SOURCE JumpThru authored count changed")
    platform, bounds = platforms[0], room["attributes"]
    require(("2", platform["id"]) == SEMANTIC_OWNER and platform["texture"] == "default" and platform["width"] == 40
            and [bounds["x"] + platform["x"], bounds["y"] + platform["y"]] == [248, -24],
            "Independent SOURCE authored JumpThru binding changed")


def read_source(path):
    require(file_identity(path) == SOURCE_IDENTITY, "Pinned SOURCE trace changed")
    verify_source_binding()
    frames = {}
    current = None
    with path.open() as stream:
        for line in stream:
            if not line.startswith('{"event":"draw-'):
                continue
            row = json.loads(line)
            tick, event = row["tick"], row["event"]
            if event == "draw-state" and row["phase"] == "before-draw":
                require(current is None and tick == len(frames), "SOURCE frame chronology changed")
                current = {"tick": tick, "commands": [], "owners": [], "spans": []}
            elif event == "draw-roster":
                require(current is not None and current["tick"] == tick, "Unbound SOURCE roster")
                current["owners"] = [owner for owner in row["live"] if owner["type"] == "JumpthruPlatform"]
            elif event == "draw-command" and row["owner"]["type"] == "JumpthruPlatform":
                require(current is not None and current["tick"] == tick, "Unbound SOURCE command")
                current["commands"].append(row)
            elif event == "draw-dispatch":
                require(current is not None and current["tick"] == tick, "Unbound SOURCE dispatch")
                current["spans"] = [span for span in row["entities"] if span["type"] == "JumpthruPlatform"]
            elif event == "draw-state" and row["phase"] == "after-draw":
                require(current is not None and current["tick"] == tick, "Unfinished SOURCE frame")
                frames[tick] = current
                current = None
    require(current is None and list(frames) == list(range(514)), "Incomplete SOURCE route")
    return frames


def read_native(path):
    frames = {}
    ended = False
    with path.open() as stream:
        for line in stream:
            if not line.startswith(('{"event":"draw-owner-', '{"event":"jumpthru-command"', '{"event":"native-ended"')):
                continue
            row = json.loads(line)
            event = row["event"]
            if event == "native-ended":
                require(not ended and row["frames"] == 514 and row["loads"] == 2 and row["reloads"] == 0, "Native route incomplete")
                ended = True
                continue
            require(not ended, "Native events after route end")
            tick = row["tick"]
            frame = frames.setdefault(tick, {"tick": tick, "commands": []})
            if event == "draw-owner-roster":
                require("owners" not in frame, "Duplicate native roster")
                frame["owners"] = row["live"]
            elif event == "draw-owner-dispatch":
                require("dispatch" not in frame, "Duplicate native dispatch")
                frame["dispatch"] = row["order"]
            else:
                frame["commands"].append(row)
    require(ended and list(frames) == list(range(514)), "Native route frames missing")
    return frames


def compare_frame(tick, source, native, stable_identity):
    expected_count = 0 if tick < 374 else 5
    actual = native["commands"]
    owners = [owner for owner in native["owners"] if owner["kind"] == "JumpthruPlatform"]
    require(len(actual) == len(source["commands"]) == expected_count, "Missing/reordered JumpThru commands")
    require(len(owners) == len(source["owners"]) == len(source["spans"]) == bool(expected_count), "JumpThru owner lifetime changed")
    if not expected_count:
        return stable_identity
    source_owner, span, owner = source["owners"][0], source["spans"][0], owners[0]
    require(source_owner["entity"] == span["entity"] == SOURCE_ENTITY and source_owner["position"] == [248, -24]
            and source_owner["Visible"] and not source_owner["hudExcluded"] and source_owner["depth"] == -60,
            "Independent SOURCE owner binding changed")
    require((owner["room"], owner["authoredId"]) == SEMANTIC_OWNER and owner["visible"] and not owner["hudExcluded"]
            and owner["sortDepthBand"] == -60, "Native semantic owner binding changed")
    identity = owner["identity"]
    require(identity and (stable_identity is None or identity == stable_identity), "Native lifetime identity changed")
    require(native["dispatch"].count(identity) == 1, "JumpThru owner missing/aliased in dispatch")
    dispatch_index = native["dispatch"].index(identity)
    require([row["index"] for row in source["commands"]] == list(range(span["drawStart"], span["drawEnd"])),
            "SOURCE dispatch span changed")
    for piece, (wanted, row) in enumerate(zip(source["commands"], actual)):
        require(wanted["owner"]["entity"] == SOURCE_ENTITY and wanted["owner"]["component"] == SOURCE_COMPONENTS[piece]
                and wanted["owner"]["componentType"] == "Image", "Independent SOURCE Image binding changed")
        require(row["ownerIdentity"] == identity and (row["room"], row["authoredId"]) == SEMANTIC_OWNER
                and row["piece"] == piece and row["dispatchIndex"] == dispatch_index
                and row["texture"] == "objects/jumpthru/wood", "Native command owner/piece/dispatch binding changed")
        for field in (*FIELDS, "effects"):
            require(same_value(row[field], wanted[field]), f"tick {tick} piece {piece}: logical {field} changed")
    return identity


def compare(source, native):
    require(list(source) == list(native) == list(range(514)), "Route coverage changed")
    identity = None
    for tick in range(514):
        identity = compare_frame(tick, source[tick], native[tick], identity)
    return {"frames": 514, "commands": 700, "logical_fields": list((*FIELDS, "effects")),
            "semantic_owner": SEMANTIC_OWNER, "native_identity": identity, "mismatches": 0,
            "scope": "Bounded logical commands only; detached visual initialization, not full unstripped SOURCE RNG equivalence or GPU/Vita"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--native", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compare(read_source(args.source), read_native(args.native)), indent=2))
