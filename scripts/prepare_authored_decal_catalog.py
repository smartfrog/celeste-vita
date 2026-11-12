"""Generate private two-room owner metadata from the pinned original map, without images."""
import argparse
import hashlib
from pathlib import Path
import re

from prepare_gameplay_draw_profile import authored_rooms, room_contract
from prepare_native_transition_fixture import room_records
from prepare_static_tilemap import INPUT_SHA, MAP_SHA
from stage_native_room import checksum

AUDIT = Path("/home/fred/projects/celeste-vita/.audit/native-room2-decal-ownership-01")
DECAL_SOURCE_SHA = "81d04a56cb9b5cb981f3c7823388bed6082db2d5755d364c15c35bbcaf8b7746"
IDENTITY_NAMESPACE = "6000000000000000"


def banner_names(source):
    if hashlib.sha256(source).hexdigest() != DECAL_SOURCE_SHA:
        raise ValueError("Pinned original Decal source changed")
    added = source.decode().split("public override void Added(Scene scene)", 1)[1]
    added = added.split("private void MakeBanner(", 1)[0]
    groups = re.findall(r'((?:\s*case "[^"\n]+":)+)\s*MakeBanner\([^;]+;', added)
    if not groups:
        raise ValueError("Original Decal.Added banner classification unavailable")
    return {name for group in groups for name in re.findall(r'case "([^"\n]+)":', group)}


def banner_texture(texture, names):
    texture = texture.replace("\\", "/")
    extension = Path(texture).suffix
    normalized = texture.replace(extension, "") if extension else texture
    return re.sub(r"\d+$", "", normalized).lower() in names


def bounded_integer(value, low, high):
    if type(value) not in (int, float) or int(value) != value or not low <= value <= high:
        raise ValueError("Invalid authored decal transform/range")
    return int(value)


def encode_catalog(rooms, source):
    room_contract(rooms)
    names = banner_names(source)
    definitions = room_records(rooms)
    lines = ["CDO1", INPUT_SHA, MAP_SHA, DECAL_SOURCE_SHA, IDENTITY_NAMESPACE, str(len(rooms))]
    for room, definition in zip(rooms, definitions):
        layers = {layer["name"]: layer for layer in room["children"]}
        background, foreground = (layers[name]["children"] for name in ("bgdecals", "fgdecals"))
        x, y, width, height = definition["bounds"]
        lines.append(" ".join(map(str, ["R", definition["name"], x, y, width, height,
                                       room["attributes"]["height"], len(background), len(foreground)])))
        for layer, decals in (("B", background), ("F", foreground)):
            for ordinal, decal in enumerate(decals):
                if decal["name"] != "decal" or decal["children"]:
                    raise ValueError("Unexpected authored decal schema")
                attributes = decal["attributes"]
                if set(attributes) != {"texture", "x", "y", "scaleX", "scaleY"}:
                    raise ValueError("Unexpected authored decal attributes")
                texture = attributes["texture"]
                if not re.fullmatch(r"[A-Za-z0-9_/\\-]+(?:\.png)?", texture) or ".." in texture:
                    raise ValueError("Invalid original decal texture identity")
                px = bounded_integer(x + attributes["x"], -1_000_000, 1_000_000)
                py = bounded_integer(y + attributes["y"], -1_000_000, 1_000_000)
                sx = bounded_integer(attributes["scaleX"], -1, 1)
                sy = bounded_integer(attributes["scaleY"], -1, 1)
                if not sx or not sy:
                    raise ValueError("Zero authored decal scale")
                lines.append(" ".join(map(str, [layer, ordinal, texture, px, py, sx, sy,
                                               int(banner_texture(texture, names))])))
    return ("\n".join(lines) + "\n").encode()


def prepare(archive, source, output):
    if not output.resolve().is_relative_to(AUDIT) or output.exists():
        raise ValueError("Authored metadata output must be fresh in its private audit namespace")
    rooms, _ = authored_rooms(archive)
    data = encode_catalog(rooms, source.read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(data)
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "fnv1a": f"{checksum(data):08x}"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "decal-source", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(prepare(args.archive, args.decal_source, args.output))
