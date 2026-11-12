"""Generate the private bounded spike material catalog from pinned original inputs."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path("/home/fred/projects/celeste-vita")
AUDIT = ROOT / ".audit/native-spike-command-projection-01"
SPIKES_SOURCE_SHA = "fb485592822286d316d93fe029acf92b83e4a0b119492dd3d2fa77f6b5e11901"
ATLAS_SHA = "b75f913d315bd641c35a4990d9041b238c0d9ef3f8b1247ec557de8a9defc1cc"
ROOMS_SHA = "b5c5814db9cb0084099a552d38890887f9f9602a97d86d99f07969e79602809f"
SPIKE_TYPE = "default"
DIRECTIONS = ("up", "left")


def file_identity(path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def fnv1a(data):
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value


def require(condition, message):
    if not condition:
        raise ValueError(message)


def atlas_key(direction):
    return f"danger/spikes/{SPIKE_TYPE}_{direction}00"


def read_frame(atlas, direction):
    key = atlas_key(direction)
    require(key in atlas, "Pinned original atlas is missing the spike frame: " + key)
    value = atlas[key]
    require(isinstance(value, list) and len(value) == 9, "Invalid pinned spike atlas tuple: " + key)
    sheet, *numbers = value
    require(isinstance(sheet, str) and sheet, "Invalid pinned spike atlas sheet: " + key)
    require(all(type(number) is int for number in numbers), "Non-integer pinned spike atlas field: " + key)
    x, y, width, height, offset_x, offset_y, frame_width, frame_height = numbers
    require(0 <= x <= 4096 - width and 0 <= y <= 4096 - height and width > 0 and height > 0,
            "Pinned spike crop is outside its sheet: " + key)
    require(-4096 <= offset_x <= 4096 and -4096 <= offset_y <= 4096,
            "Pinned spike draw offset is out of bounds: " + key)
    require(0 < frame_width <= 4096 and 0 < frame_height <= 4096,
            "Pinned spike frame size is out of bounds: " + key)
    return {"key": key, "sheet": sheet, "x": x, "y": y, "width": width, "height": height,
            "offset_x": offset_x, "offset_y": offset_y,
            "frame_width": frame_width, "frame_height": frame_height}


def room_spike_summary(rooms_record):
    summary = []
    for room in rooms_record:
        spikes = [value for value in room["objects"] if value[0].startswith("spike_")]
        pieces = sum(value[4] // 8 for value in spikes)
        directions = [value[0][len("spike_"):] for value in spikes]
        for value in spikes:
            require(value[0] in ("spike_up", "spike_left") and 0 < value[4] <= 136 and value[4] % 8 == 0,
                    "Unsupported pinned room spike")
        summary.append({"room": room["name"], "owners": len(spikes), "pieces": pieces,
                        "objects": [{"kind": value[0], "id": value[1],
                                     "position": value[2:4], "size": value[4]} for value in spikes]})
        if room["name"] == "1":
            require(len(spikes) == 5 and pieces == 19 and
                    directions.count("up") == 4 and directions.count("left") == 1,
                    "Pinned room 1 spike owner/piece/direction facts changed")
        elif room["name"] == "2":
            require(len(spikes) == 3 and pieces == 9 and set(directions) == {"up"},
                    "Pinned room 2 spike owner/piece/direction facts changed")
        else:
            raise ValueError("Unexpected room in the bounded two-room profile")
    require([value["pieces"] for value in summary] == [19, 9], "Pinned room spike totals changed")
    return summary


def encode_catalog(frames):
    lines = ["CSPK1", SPIKES_SOURCE_SHA, ATLAS_SHA, ROOMS_SHA, str(len(DIRECTIONS))]
    for direction in DIRECTIONS:
        frame = frames[direction]
        lines.append(" ".join(map(str, [direction, frame["sheet"], frame["x"], frame["y"],
                                        frame["width"], frame["height"], frame["offset_x"],
                                        frame["offset_y"], frame["frame_width"],
                                        frame["frame_height"], frame["key"]])))
    return ("\n".join(lines) + "\n").encode()


def prepare(atlas_path, spikes_path, rooms_path, output):
    require(output.resolve().is_relative_to(AUDIT), "Spike catalog must live in its private audit namespace")
    require(not output.exists(), "Spike catalog output must be fresh")
    atlas_identity = file_identity(atlas_path)
    spikes_identity = file_identity(spikes_path)
    rooms_identity = file_identity(rooms_path)
    require(atlas_identity["sha256"] == ATLAS_SHA, "Pinned original atlas metadata changed")
    require(spikes_identity["sha256"] == SPIKES_SOURCE_SHA, "Pinned original Spikes source changed")
    require(rooms_identity["sha256"] == ROOMS_SHA, "Pinned room metadata changed")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from prepare_native_transition_fixture import room_records
    rooms = json.loads(rooms_path.read_text())
    require([room.get("attributes", {}).get("name") for room in rooms] == ["lvl_1", "lvl_2"],
            "Expected the pinned bounded lvl_1/lvl_2 profile")
    spike_summary = room_spike_summary(room_records(rooms))
    atlas = json.loads(atlas_path.read_text())
    require(isinstance(atlas, dict) and atlas, "Invalid pinned atlas metadata payload")
    frames = {direction: read_frame(atlas, direction) for direction in DIRECTIONS}
    data = encode_catalog(frames)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(data)
    receipt = {
        "schema": 1,
        "kind": "native-spike-material-catalog-01",
        "spikes_source": {"path": str(spikes_path), **spikes_identity},
        "atlas": {"path": str(atlas_path), **atlas_identity},
        "rooms": {"path": str(rooms_path), **rooms_identity},
        "spike_type": SPIKE_TYPE,
        "directions": list(DIRECTIONS),
        "room_spikes": spike_summary,
        "frames": frames,
        "output": {"path": str(output), "bytes": len(data),
                   "sha256": hashlib.sha256(data).hexdigest(),
                   "fnv1a": f"{fnv1a(data):08x}"},
        "integrity_note": "FNV-1a is build integrity; only the pinned SHA-256 values are provenance identities",
    }
    (output.parent / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--atlas", type=Path, required=True)
    parser.add_argument("--spikes-source", type=Path, required=True)
    parser.add_argument("--rooms", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.atlas, args.spikes_source, args.rooms, args.output), indent=2))
