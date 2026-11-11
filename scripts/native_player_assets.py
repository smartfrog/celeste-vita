"""Fixed 128x64 private player pages; deduplicate exact crops, never omit frames."""

from native_room_textures import extrude
import struct
import xml.etree.ElementTree as ET
from prepare_static_tilemap import INPUT_SHA, MAP_SHA


def player_metadata(bank, layout, page_checksums):
    frames = {frame["name"]: frame for frame in bank["frames"]}
    names = sorted(frames)
    indices = {name: index for index, name in enumerate(names)}
    text = f"CSPP1\n{INPUT_SHA}\n{MAP_SHA}\n{len(page_checksums)}\n"
    text += "".join(f"{value:08x}\n" for value in page_checksums)
    text += f"{len(names)}\n"
    for name in names:
        frame = frames[name]
        fields = [name, *layout[name], *frame["rectangle"][2:], *map(int, frame["trim"]), *frame["size"],
                  *map(int, frame["hairOffset"]), frame["hairFrame"], int(frame["hasHair"])]
        text += " ".join(map(str, fields)) + "\n"
    text += f"{len(bank['animations'])}\n"
    for animation in bank["animations"]:
        delay = struct.unpack("<I", struct.pack("<f", animation["delay"]))[0]
        text += f"{animation['id']} {delay:08x} {animation['next'] or '-'} {len(animation['frames'])} "
        text += " ".join(str(indices[name]) for name in animation["frames"]) + "\n"
    text += " ".join(str(indices[name]) for name in [*bank["bangs"], bank["hair"]]) + "\n"
    return text


def extend_death_bank(bank, sprites, atlas):
    if len(bank["animations"]) != 24:
        raise ValueError("Death extension requires the preserved legacy bank")
    player = ET.fromstring(sprites).find("player")
    if player is None or player.get("copy"):
        raise ValueError("Unsupported original player bank")
    result = {**bank, "animations": list(bank["animations"]), "frames": list(bank["frames"])}
    names = {frame["name"] for frame in result["frames"]}
    for identity in ("deadup", "deaddown", "deadside"):
        animations = [child for child in player if child.get("id") == identity]
        if len(animations) != 1 or animations[0].tag != "Anim" or animations[0].get("goto"):
            raise ValueError("Unsupported original death animation: " + identity)
        animation = animations[0]
        path = player.attrib["path"] + animation.attrib["path"]
        frames = []
        for item in animation.attrib["frames"].split(","):
            limits = [int(value) for value in item.split("-")]
            if len(limits) not in (1, 2) or min(limits) < 0 or max(limits) > 99:
                raise ValueError("Unsupported original death animation frames")
            frames.extend(range(limits[0], limits[-1] + 1))
        if not frames or len(frames) > 32:
            raise ValueError("Unsupported original death animation length")
        textures = [path + f"{index:02d}" for index in frames]
        metadata = player.find("Metadata")
        if metadata is not None and any(path.startswith(player.attrib["path"] + child.get("path", "")) for child in metadata):
            raise ValueError("Death metadata now requires original hair export")
        for name in textures:
            sheet, x, y, width, height, trim_x, trim_y, frame_width, frame_height = atlas[name]
            if sheet != "Gameplay0":
                raise ValueError("Death frame left the pinned atlas page")
            if name not in names:
                result["frames"].append({"name": name, "rectangle": [x,y,width,height], "trim": [-trim_x,-trim_y],
                                         "size": [frame_width,frame_height], "hairOffset": [0,0], "hairFrame": 0, "hasHair": False})
                names.add(name)
        delay = struct.unpack("<f", struct.pack("<f", float(animation.attrib["delay"])))[0]
        result["animations"].append({"id": identity, "delay": delay, "next": "", "frames": textures})
    sweat = ET.fromstring(sprites).find("player_sweat")
    if sweat is None:
        raise ValueError("Missing original player sweat bank")
    idle = [child for child in sweat if child.get("id") == "idle"]
    if len(idle) != 1 or idle[0].tag != "Loop" or idle[0].get("frames") not in (None, "0"):
        raise ValueError("Unsupported bounded sweat idle")
    name = sweat.attrib["path"] + idle[0].attrib["path"] + "00"
    if idle[0].get("frames") is None and {key for key in atlas if key.startswith(sweat.attrib["path"] + idle[0].attrib["path"])} != {name}:
        raise ValueError("Sweat idle no longer has exactly one frame")
    sheet, x, y, width, height, trim_x, trim_y, frame_width, frame_height = atlas[name]
    if sheet != "Gameplay0":
        raise ValueError("Sweat idle left the pinned atlas page")
    result["frames"].append({"name": name, "rectangle": [x,y,width,height], "trim": [-trim_x,-trim_y],
                             "size": [frame_width,frame_height], "hairOffset": [0,0], "hairFrame": 0, "hasHair": False})
    return result


def pack_player_crops(crops):
    if not crops or len(crops) > 256:
        raise ValueError("Invalid bounded player crop count")
    unique, aliases = {}, {}
    for name, (width, height, rgba) in crops.items():
        if not 1 <= width <= 126 or not 1 <= height <= 62 or len(rgba) != width * height * 4:
            raise ValueError("Invalid player crop dimensions or bytes")
        key = width, height, rgba
        aliases[name] = unique.setdefault(key, name)
    pages, layout = [bytearray(128 * 64 * 4)], {}
    x = y = row_height = 0
    for (width, height, rgba), name in sorted(unique.items(), key=lambda entry: (-entry[0][1], -entry[0][0], entry[1])):
        if x + width + 2 > 128:
            x, y, row_height = 0, y + row_height, 0
        if y + height + 2 > 64:
            if len(pages) == 10:
                raise ValueError("Required player closure exceeds fixed page upload budget")
            pages.append(bytearray(128 * 64 * 4))
            x = y = row_height = 0
        padded = extrude(rgba, width, height, width + 2, height + 2)
        for dy in range(height + 2):
            target = ((y + dy) * 128 + x) * 4
            start = dy * (width + 2) * 4
            pages[-1][target:target + (width + 2) * 4] = padded[start:start + (width + 2) * 4]
        layout[name] = len(pages) - 1, x + 1, y + 1
        x, row_height = x + width + 2, max(row_height, height + 2)
    return [bytes(page) for page in pages], {name: layout[target] for name, target in aliases.items()}
