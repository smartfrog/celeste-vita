#!/usr/bin/env python3
"""Decode only the selected room's static Up/Left spikes into private bounded fixtures."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import zipfile

from binary_map import Reader
from prepare_static_tilemap import INPUT_SHA, MAP_SHA, MEMBER, int32, selected_room_facts, map_driver, build_mask, read_mask


def room_hazards(root):
    facts = selected_room_facts(root)
    levels = next(group["children"] for group in root["children"] if group["name"] == "levels")
    room = next(room for room in levels if room["attributes"]["name"] == "lvl_1")
    entities = next(layer["children"] for layer in room["children"] if layer["name"] == "entities")
    origin = room["attributes"]
    hazards = []
    for order, entity in enumerate(entities):
        if not entity["name"].startswith("spikes"):
            continue
        if entity["name"] not in {"spikesUp", "spikesLeft"}:
            raise ValueError("Unsupported spike in explicitly selected room")
        a = entity["attributes"]
        direction = "up" if entity["name"] == "spikesUp" else "left"
        size = int32(a["width" if direction == "up" else "height"])
        if size <= 0:
            raise ValueError("Invalid static spike size")
        hazards.append({"map_order": order, "entity_id": int32(a["id"]), "direction": direction,
                        "x": int32(origin["x"] + int32(a["x"])), "y": int32(origin["y"] + int32(a["y"])), "size": size})
    if Counter(h["direction"] for h in hazards) != {"up": 4, "left": 1}:
        raise ValueError("Room 1 static hazard profile changed")
    if len({h["entity_id"] for h in hazards}) != len(hazards):
        raise ValueError("Duplicate static hazard identity")
    if sum(e["name"] == "goldenBerry" for e in entities) != 1:
        raise ValueError("Expected the ordinary-profile gated raw golden berry")
    return facts, hazards


def hazard_fixtures(mask, facts, hazards):
    x, y, columns, rows, cells = mask
    geometry = f"grid 1 {x} {y} 0 0 8 8 {columns} {rows} {cells} 1\n"
    for i, h in enumerate(hazards, 101):
        geometry += f"spike {i} {h['x']} {h['y']} {h['size']} {h['direction']} 1\n"
    spawn = facts["spawns"][0]
    output = f"case room1_spawn {spawn[0]} {spawn[1]} 0 0 0 320\n" + geometry
    output += "tick 0 0 0 0 0 0 0 0 0 => alive -\n"
    for i, h in enumerate(hazards, 101):
        px = h["x"] + min(4, h["size"] // 2) if h["direction"] == "up" else h["x"] - 2
        py = h["y"] + 2 if h["direction"] == "up" else h["y"] + min(4, h["size"] // 2)
        for lethal in (True, False):
            sx = -1 if not lethal and h["direction"] == "left" else 0
            sy = -1 if not lethal and h["direction"] == "up" else 0
            output += f"case room1_spike_{i}_{'lethal' if lethal else 'nonlethal'} {px} {py} {sx} {sy} 0 320\n" + geometry
            output += f"tick 0 0 0 0 0 0 0 0 0 => {'dead:' + str(i) if lethal else 'alive'} {i}\n"
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=Path("game/celeste-linux.zip"))
    parser.add_argument("--mask", type=Path, default=Path(".audit/native-static-tilemap/prepared/global.mask"))
    parser.add_argument("--output", type=Path, default=Path(".audit/native-room-hazards/prepared"))
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(Path(".audit").resolve()):
        parser.error("Private hazard data must remain under .audit")
    with zipfile.ZipFile(args.archive) as archive:
        if archive.getinfo(MEMBER).file_size > 16 * 1024 * 1024 or archive.getinfo("Celeste.exe").file_size > 32 * 1024 * 1024:
            raise ValueError("Private input exceeds preparation bound")
        data, exe = archive.read(MEMBER), archive.read("Celeste.exe")
    if hashlib.sha256(data).hexdigest() != MAP_SHA or hashlib.sha256(exe).hexdigest() != INPUT_SHA:
        raise ValueError("Unexpected private game/map hash")
    package, root = Reader(data).map()
    if package != "1-ForsakenCity":
        raise ValueError("Unexpected map package")
    facts, hazards = room_hazards(root)
    mask = read_mask(args.mask.read_text())
    if mask != build_mask(map_driver(root)):
        raise ValueError("Hazards must use the accepted merged global geometry, not an isolated room")
    output.mkdir(parents=True, exist_ok=True)
    (output / "hazards.json").write_text(json.dumps(hazards, indent=2) + "\n")
    (output / "hazards.fixtures").write_text(hazard_fixtures(mask, facts, hazards))
    provenance = {"input_sha256": INPUT_SHA, "map_sha256": MAP_SHA, "member": MEMBER, "selected_room": "1",
                  "room_facts": facts, "hazard_count": len(hazards), "map_order": [h["map_order"] for h in hazards],
                  "golden_gate": "closed: ordinary non-cheat/non-debug save, unlocked modes < 3; no raw berry spawn",
                  "global_mask_sha256": hashlib.sha256(args.mask.read_bytes()).hexdigest(),
                  "files": {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in ("hazards.json", "hazards.fixtures")},
                  "claim": "Offline selected static hazards and synthetic probes on merged geometry; no original game execution"}
    (output / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(f"Prepared five room-1 hazards in map order, 11 private probe cases; {output}")


if __name__ == "__main__":
    main()
