#!/usr/bin/env python3
"""Prepare private ForsakenCity global static solids offline; never execute the game."""

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import zipfile

from binary_map import Reader

INPUT_SHA = "fd73f8a2311fa5737ded550cbad4b75c85b7686b36432f59185e940fcb65fcfe"
MAP_SHA = "ace1892261c03aa766f45aaa38cb2cd60a8823c34eda673f5b2ed8ab31c890ab"
MEMBER = "Content/Maps/1-ForsakenCity.bin"
MAX_CELLS = 4_000_000


def int32(value):
    if type(value) is not int or not -2147483648 <= value <= 2147483647:
        raise ValueError("Expected int32 map scalar")
    return value


def trunc8(value):
    return value // 8 if value >= 0 else -((-value) // 8)


def tile_bounds(room, normalize_height=True):
    x, y, width, height = (int32(room[key]) for key in ("x", "y", "width", "height"))
    if width <= 0 or height <= 0:
        raise ValueError("Room dimensions must be positive")
    if normalize_height and height == 184:
        height = 180
    ceil8 = lambda value: math.ceil(struct.unpack("<f", struct.pack("<f", value))[0] / 8)
    return trunc8(x), trunc8(y), ceil8(width), ceil8(height)


class Layer:
    def __init__(self, columns, rows, default):
        if columns <= 0 or rows <= 0 or columns * rows > MAX_CELLS:
            raise ValueError("Invalid or excessive global mask dimensions")
        self.columns, self.rows = columns, rows
        self.data = [default] * (columns * rows)

    def index(self, x, y):
        if not 0 <= x < self.columns or not 0 <= y < self.rows:
            raise ValueError(f"Raw VirtualMap access outside valid storage: {x},{y}")
        return y * self.columns + x

    def __getitem__(self, at):
        return self.data[self.index(*at)]

    def __setitem__(self, at, value):
        self.data[self.index(*at)] = value


def merge_text(layer, x, y, text):
    for dy, row in enumerate(re.split(r"\r\n|\n\r|\n|\r", text)):
        for dx, char in enumerate(row):
            layer[x + dx, y + dy] = char


def map_dimensions(driver):
    levels, filler = driver["levels"], driver["filler"]
    if not levels:
        raise ValueError("Global construction requires levels")
    rectangles = []
    for room in levels:
        tile_bounds(room)
        height = 180 if room["height"] == 184 else room["height"]
        rectangles.append((room["x"], room["y"], int32(room["x"] + room["width"]), int32(room["y"] + height)))
    for item in filler:
        x, y, w, h = (int32(item[key]) for key in ("x", "y", "w", "h"))
        if w < 0 or h < 0:
            raise ValueError("Negative filler dimensions")
        rectangles.append((x, y, int32(x + w), int32(y + h)))
    left = int32(min(r[0] for r in rectangles) - 64)
    top = int32(min(r[1] for r in rectangles) - 64)
    width = int32(max(r[2] for r in rectangles) - left + 64)
    height = int32(max(r[3] for r in rectangles) - top + 64)
    tx, ty, columns, rows = tile_bounds(dict(x=left, y=top, width=width, height=height), normalize_height=False)
    return tx * 8, ty * 8, columns, rows


def build_mask(driver):
    levels, filler = driver["levels"], driver["filler"]
    x, y, columns, rows = map_dimensions(driver)
    tx, ty = trunc8(x), trunc8(y)
    solids, reserved = Layer(columns, rows, "0"), Layer(columns, rows, False)
    bounds = [tile_bounds(room) for room in levels]
    for room, (x, y, w, h) in zip(levels, bounds):
        merge_text(solids, x - tx, y - ty, room["solids"])
        for m in range(w):
            for n in range(h):
                reserved[x + m - tx, y + n - ty] = True
    for item in filler:
        x, y, w, h = (item[key] for key in ("x", "y", "w", "h"))
        for m in range(x, x + w):
            for n in range(y, y + h):
                char = "0"
                for permitted, probe in ((y - ty > 0, (m - tx, y - ty - 1)),
                                         (x - tx > 0, (x - tx - 1, n - ty)),
                                         (x + w - tx < columns - 1, (x + w - tx, n - ty)),
                                         (y + h - ty < rows - 1, (m - tx, y + h - ty))):
                    if char == "0" and permitted:
                        char = solids[probe]
                solids[m - tx, n - ty] = char if char != "0" else "1"
                reserved[m - tx, n - ty] = True
    for x, y, w, h in bounds:
        for m in range(x, x + w):
            for edge, direction in ((y, -1), (y + h - 1, 1)):
                if solids[m - tx, edge - ty] == "0":
                    for distance in range(1, 8):
                        reserved[m - tx, edge - ty + direction * distance] = True
    for x, y, w, h in bounds:
        for m in range(x, x + w):
            for edge, direction in ((y, -1), (y + h - 1, 1)):
                char = solids[m - tx, edge - ty]
                for distance in range(1, 4):
                    at = (m - tx, edge - ty + direction * distance)
                    if reserved[at]:
                        break
                    solids[at] = char
        for n in range(y - 4, y + h + 4):
            for edge, direction in ((x, -1), (x + w - 1, 1)):
                char = solids[edge - tx, n - ty]
                for distance in range(1, 4):
                    at = (edge - tx + direction * distance, n - ty)
                    if reserved[at]:
                        break
                    solids[at] = char
    return tx * 8, ty * 8, columns, rows, "".join("1" if char != "0" else "0" for char in solids.data)


def mask_text(mask):
    x, y, columns, rows, cells = mask
    if any(type(v) is not int for v in (x, y, columns, rows)) or columns <= 0 or rows <= 0 or columns * rows > MAX_CELLS:
        raise ValueError("Invalid mask dimensions")
    for value in (x, y, columns * 8, rows * 8, x + columns * 8, y + rows * 8):
        int32(value)
    if len(cells) != columns * rows or set(cells) - {"0", "1"}:
        raise ValueError("Invalid mask cells")
    return f"CSTM1\n{INPUT_SHA}\n{MAP_SHA}\n{x} {y} {columns} {rows}\n{cells}\n"


def read_mask(text):
    lines = text.splitlines()
    if len(lines) != 5 or lines[:3] != ["CSTM1", INPUT_SHA, MAP_SHA]:
        raise ValueError("Invalid mask header or input hashes")
    try:
        dimensions = tuple(map(int, lines[3].split()))
    except ValueError as error:
        raise ValueError("Invalid mask dimensions") from error
    if len(dimensions) != 4:
        raise ValueError("Invalid mask dimension count")
    mask = (*dimensions, lines[4])
    if mask_text(mask) != text:
        raise ValueError("Noncanonical mask serialization")
    return mask


def map_driver(root):
    groups = {child["name"]: child["children"] for child in root["children"]}
    levels = []
    for room in groups["levels"]:
        a = room["attributes"]
        layers = {child["name"]: child for child in room["children"]}
        levels.append({**{key: a[key] for key in ("name", "x", "y", "width", "height")},
                       "solids": layers.get("solids", {}).get("attributes", {}).get("innerText", ""),
                       "bg": layers.get("bg", {}).get("attributes", {}).get("innerText", "")})
    return {"levels": levels, "filler": [child["attributes"] for child in groups.get("Filler", [])]}


def geometry_fixtures(mask):
    x, y, columns, rows, cells = mask
    grid = f"grid 1 {x} {y} 0 0 8 8 {columns} {rows} {cells} 1\n"
    actor = "actor 19 144 8 11 -4 -11 1 1 0\n"
    return ("case room1_spawn\n" + actor + grid + "Q 19 144\nQ 19 145\n"
            + "case room1_global_edges\nactor 0 0 1 1 0 0 1 1 0\n" + grid + "Q -1 144\nQ 16 -1\nQ 240 -1\n"
            + "case room1_actor_ground\n" + actor + grid + "V 0.25 record -1\nV 1 record 1\n")


def player_fixtures(mask):
    x, y, columns, rows, cells = mask
    return (f"case room1_walk_jump 19 144 0 0 0 320\ngrid 1 {x} {y} 0 0 8 8 {columns} {rows} {cells} 1\n"
            + "tick @3c888889 1 0 0 0 0 0 0 0\n" * 10
            + "tick @3c888889 1 0 1 1 0 0 0 0\n"
            + "tick @3c888889 1 0 1 0 0 0 0 0\n" * 9)


def selected_room_facts(root):
    levels = next(group["children"] for group in root["children"] if group["name"] == "levels")
    rooms = [room for room in levels if room["attributes"]["name"] == "lvl_1"]
    if len(rooms) != 1:
        raise ValueError("Expected explicit unique room 1")
    room = rooms[0]
    a = room["attributes"]
    layers = {layer["name"]: layer for layer in room["children"]}
    solids = layers["solids"]["attributes"]["innerText"]
    spawns = [[a["x"] + entity["attributes"]["x"], a["y"] + entity["attributes"]["y"]]
              for entity in layers["entities"]["children"] if entity["name"] == "player"]
    rows = re.split(r"\r\n|\n\r|\n|\r", solids)
    facts = {"origin": [a["x"], a["y"]], "stored_dimensions": [a["width"], a["height"]],
             "normalized_dimensions": [a["width"], 180 if a["height"] == 184 else a["height"]],
             "tile_dimensions": list(tile_bounds(a)[2:]), "occupied": sum(c not in "0\r\n" for c in solids),
             "occupied_characters": dict(Counter(c for c in solids if c not in "0\r\n")),
             "line_feeds": solids.count("\n"), "carriage_returns": solids.count("\r"), "spawns": spawns,
             "solids_text_sha256": hashlib.sha256(solids.encode()).hexdigest()}
    if (facts["origin"] != [0, 0] or facts["stored_dimensions"] != [320, 184] or spawns != [[19, 144]] or
            len(rows) != 23 or any(len(row) != 40 for row in rows) or facts["occupied"] != 363):
        raise ValueError("Room 1 geometry/spawn acceptance changed")
    return facts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=Path("game/celeste-linux.zip"))
    parser.add_argument("--output", type=Path, default=Path(".audit/native-static-tilemap/prepared"))
    args = parser.parse_args()
    output = args.output.resolve()
    private = Path(".audit").resolve()
    if not output.is_relative_to(private):
        parser.error("Private assets must remain under .audit")
    with zipfile.ZipFile(args.archive) as archive:
        if archive.getinfo(MEMBER).file_size > 16 * 1024 * 1024 or archive.getinfo("Celeste.exe").file_size > 32 * 1024 * 1024:
            raise ValueError("Private input exceeds preparation bound")
        data = archive.read(MEMBER)
        exe = archive.read("Celeste.exe")
    if hashlib.sha256(data).hexdigest() != MAP_SHA or hashlib.sha256(exe).hexdigest() != INPUT_SHA:
        raise ValueError("Unexpected private game/map input hash")
    package, root = Reader(data).map()
    if package != "1-ForsakenCity":
        raise ValueError("Unexpected map package")
    driver = map_driver(root)
    facts = selected_room_facts(root)
    mask = build_mask(driver)
    text = mask_text(mask)
    read_mask(text)
    output.mkdir(parents=True, exist_ok=True)
    (output / "driver.json").write_text(json.dumps(driver, ensure_ascii=True, separators=(",", ":")) + "\n")
    (output / "global.mask").write_text(text)
    (output / "geometry.fixtures").write_text(geometry_fixtures(mask))
    (output / "player.fixtures").write_text(player_fixtures(mask))
    manifest = {"input_sha256": INPUT_SHA, "map_sha256": MAP_SHA, "member": MEMBER, "selected_room": "1",
                "room_facts": facts,
                "claim": "Offline source-informed global construction; run the unchanged-block oracle for verification",
                "origin": mask[:2], "dimensions": mask[2:4], "occupied": mask[4].count("1"),
                "files": {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in ("driver.json", "global.mask", "geometry.fixtures", "player.fixtures")}}
    (output / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Prepared private global mask {mask[2]}x{mask[3]}; {manifest['occupied']} occupied cells; {output}")


if __name__ == "__main__":
    main()
