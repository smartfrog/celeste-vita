"""Generate a private static-decal descriptor catalog from pinned atlas and CDO1 metadata."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path("/home/fred/projects/celeste-vita")
AUDIT = ROOT / ".audit/native-static-decal-draw-projection-01"
INPUT_SHA = "fd73f8a2311fa5737ded550cbad4b75c85b7686b36432f59185e940fcb65fcfe"
MAP_SHA = "ace1892261c03aa766f45aaa38cb2cd60a8823c34eda673f5b2ed8ab31c890ab"
DECAL_SOURCE_SHA = "81d04a56cb9b5cb981f3c7823388bed6082db2d5755d364c15c35bbcaf8b7746"
ATLAS_SHA = "b75f913d315bd641c35a4990d9041b238c0d9ef3f8b1247ec557de8a9defc1cc"
AUTHORED_SHA = "1eb4bcb699363754df20ddf9b6f7b21738401cddf53e961755127f3ba5fda350"
IDENTITY_NAMESPACE = 0x6000000000000000
FAMILY_COUNT = 23
STATIC_COUNT = 41
DEFERRED_COUNT = 11


def fnv1a(data):
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value


def file_identity(path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def parse_authored_catalog(text):
    require(text.endswith("\n"), "CDO1 catalog must end with a newline")
    lines = text.splitlines()
    require(len(lines) >= 7 and lines[0] == "CDO1", "Unknown CDO1 catalog version")
    require(lines[1:6] == [INPUT_SHA, MAP_SHA, DECAL_SOURCE_SHA, "6000000000000000", "2"],
            "CDO1 provenance/namespace/room header changed")
    rooms, owners, index = [], [], 6
    for room_index in range(2):
        require(index < len(lines), "Truncated CDO1 room record")
        fields = lines[index].split()
        index += 1
        require(len(fields) == 9 and fields[0] == "R", "Invalid CDO1 room record")
        name, x, y, width, height, raw_height, background, foreground = (
            fields[1], *map(int, fields[2:]))
        require(name in ("1", "2") and (x, y, width, height, raw_height) ==
                ((0, 0, 320, 180, 184) if name == "1" else (240, -184, 320, 180, 184)),
                "CDO1 room bounds changed")
        require(0 <= background <= 64 and 0 <= foreground <= 64, "CDO1 room decal counts changed")
        room = {"name": name, "bounds": [x, y, width, height],
                "background": background, "foreground": foreground}
        rooms.append(room)
        for layer, count in (("B", background), ("F", foreground)):
            for ordinal in range(count):
                require(index < len(lines), "Truncated CDO1 decal owner record")
                fields = lines[index].split()
                index += 1
                require(len(fields) == 8 and fields[0] == layer and int(fields[1]) == ordinal,
                        "Invalid CDO1 decal owner layer/ordinal")
                texture = fields[2]
                px, py, sx, sy, banner = map(int, fields[3:])
                require(texture and ".." not in texture.replace("\\", "/"), "Invalid CDO1 decal key")
                require(-1_000_000 <= px <= 1_000_000 and -1_000_000 <= py <= 1_000_000,
                        "Invalid CDO1 decal position")
                require(sx in (-1, 1) and sy in (-1, 1), "Invalid CDO1 decal signed scale")
                require(banner in (0, 1), "Invalid CDO1 Banner classification")
                identity = (IDENTITY_NAMESPACE | (room_index + 1) << 32 |
                            (1 if layer == "B" else 2) << 24 | ordinal + 1)
                owners.append({"room": name, "background": layer == "B", "ordinal": ordinal,
                               "texture": texture, "position": [px, py], "scale": [sx, sy],
                               "banner": bool(banner), "identity": identity})
    require(index == len(lines), "Trailing CDO1 catalog data")
    require(sum(not owner["banner"] for owner in owners) == STATIC_COUNT,
            "Expected 41 static authored decal owners")
    require(sum(owner["banner"] for owner in owners) == DEFERRED_COUNT,
            "Expected 11 authored Banner decal owners")
    require([(room["background"], room["foreground"]) for room in rooms] == [(25, 4), (18, 5)],
            "Authored room decal layer counts changed")
    require((sum(owner["background"] and not owner["banner"] for owner in owners
                 if owner["room"] == "1"),
             sum(not owner["background"] and not owner["banner"] for owner in owners
                 if owner["room"] == "1")) == (20, 2), "Room 1 static split changed")
    require((sum(owner["background"] and not owner["banner"] for owner in owners
                 if owner["room"] == "2"),
             sum(not owner["background"] and not owner["banner"] for owner in owners
                 if owner["room"] == "2")) == (14, 5), "Room 2 static split changed")
    return rooms, owners


def atlas_key(texture):
    path = texture.replace("\\", "/")
    if path.lower().endswith(".png"):
        path = path[:-4]
    return "decals/" + path


def frame_tuple(atlas, texture):
    key = atlas_key(texture)
    require(key in atlas, "Static decal atlas key is missing: " + key)
    value = atlas[key]
    require(isinstance(value, list) and len(value) == 9, "Invalid atlas tuple: " + key)
    sheet, x, y, width, height, offset_x, offset_y, frame_width, frame_height = value
    require(isinstance(sheet, str) and sheet, "Invalid atlas sheet: " + key)
    require(all(type(number) is int for number in value[1:]), "Non-integer atlas tuple: " + key)
    require(0 <= x <= 4096 - width and 0 <= y <= 4096 - height and width > 0 and height > 0,
            "Atlas crop is outside the sheet: " + key)
    require(-4096 <= offset_x <= 4096 and -4096 <= offset_y <= 4096,
            "Atlas draw offset is out of bounds: " + key)
    require(0 < frame_width <= 4096 and 0 < frame_height <= 4096,
            "Atlas frame size is out of bounds: " + key)
    return value


def encode_catalog(authored_text, atlas):
    rooms, owners = parse_authored_catalog(authored_text)
    families, static_keys = [], []
    for owner in owners:
        if owner["banner"]:
            continue
        key = atlas_key(owner["texture"])
        if key not in static_keys:
            static_keys.append(key)
            families.append((key, owner["texture"], frame_tuple(atlas, owner["texture"])))
    require(len(families) == FAMILY_COUNT, "Expected 23 static decal atlas families")
    require(len(static_keys) == len(set(static_keys)), "Duplicate static decal atlas family")
    for owner in owners:
        frame_tuple(atlas, owner["texture"])
    family_index = {key: index for index, (key, _, _) in enumerate(families)}
    lines = ["CDSC1", INPUT_SHA, MAP_SHA, DECAL_SOURCE_SHA, ATLAS_SHA, AUTHORED_SHA,
             str(FAMILY_COUNT)]
    for _, texture, frame in families:
        lines.append(" ".join(map(str, frame)) + " " + texture)
    used = set()
    owners_out = []
    for owner in owners:
        if owner["banner"]:
            continue
        key = atlas_key(owner["texture"])
        index = family_index[key]
        used.add(index)
        owners_out.append((owner["room"], "B" if owner["background"] else "F",
                           owner["ordinal"], index))
    require(len(owners_out) == STATIC_COUNT and len(used) == FAMILY_COUNT,
            "Incomplete static descriptor family/owner coverage")
    lines.append(str(len(owners_out)))
    lines.extend("O " + " ".join(map(str, row)) for row in owners_out)
    deferred = [(owner["room"], "B" if owner["background"] else "F",
                 owner["ordinal"], owner["texture"]) for owner in owners if owner["banner"]]
    require(len(deferred) == DEFERRED_COUNT, "Incomplete deferred Banner coverage")
    lines.append(str(len(deferred)))
    lines.extend("D " + " ".join(map(str, row)) for row in deferred)
    return ("\n".join(lines) + "\n").encode()


def prepare(atlas_path, authored_path, output):
    require(output.resolve().is_relative_to(AUDIT), "Descriptor catalog must live in its private audit namespace")
    require(not output.exists(), "Descriptor catalog output must be fresh")
    atlas_identity = file_identity(atlas_path)
    authored_identity = file_identity(authored_path)
    require(atlas_identity["sha256"] == ATLAS_SHA, "Pinned private atlas metadata changed")
    require(authored_identity["sha256"] == AUTHORED_SHA, "Pinned authored decal catalog changed")
    atlas = json.loads(atlas_path.read_text())
    require(isinstance(atlas, dict) and atlas, "Invalid atlas metadata payload")
    authored_text = authored_path.read_text()
    rooms, owners = parse_authored_catalog(authored_text)
    data = encode_catalog(authored_text, atlas)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(data)
    receipt = {
        "schema": 1,
        "kind": "native-static-decal-descriptor-catalog-01",
        "atlas": {"path": str(atlas_path), **atlas_identity},
        "authored_catalog": {"path": str(authored_path), **authored_identity},
        "rooms": rooms,
        "atlas_owner_keys": len(owners),
        "atlas_missing_keys": 0,
        "static_owners": STATIC_COUNT,
        "deferred_banners": DEFERRED_COUNT,
        "families": FAMILY_COUNT,
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
    parser.add_argument("--authored-catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(prepare(arguments.atlas, arguments.authored_catalog,
                             arguments.output), indent=2))
