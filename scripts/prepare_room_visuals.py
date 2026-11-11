#!/usr/bin/env python3
"""Prepare six private bounded textures and select room commands AFTER the full source bake."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from check_native_oracle import ROOT, verify_extraction
from native_room_textures import atlas_metadata, decode_crops, extrude
from prepare_static_tilemap import INPUT_SHA, MAP_SHA
from stage_native_room import checksum, verified_bytes
from game_input import archive_identity, read_members


TEXTURES = ("tilesets/dirt", "tilesets/snow", "tilesets/girder", "tilesets/cement", "tilesets/bgDirt", "characters/player/idle00")
MEMBERS = {
    "Celeste.exe": INPUT_SHA,
    "FNA.dll": "00349b572636c0ed4c97d4e4f74344b3450160c42d4a6b52bcf5e0f2d5193a31",
    "mscorlib.dll": "1da089aee864876d1f7d303e91087a1e2f3c9f7b989514a780a5ba9188053341",
    "Content/Maps/1-ForsakenCity.bin": MAP_SHA,
    "Content/Graphics/Atlases/Gameplay.meta": "1f23b1f35544a3751ffec170b0230c7c9513000ab1549f78ebb9cb9f4203c8d9",
    "Content/Graphics/Atlases/Gameplay0.data": "687f3340c937e3baca71758bfb1e6b8e799ad896f2df19bef26ec64968b3490b",
    "Content/Graphics/ForegroundTiles.xml": "1d31280a6ef0a81909186954648aa3e47e30de036404e3117916dbcdd0dfee65",
    "Content/Graphics/BackgroundTiles.xml": "fa2c03e2b41f72778bacbe2498927a5bfce81112e9645748d371606bd4ed016b",
    "Content/Graphics/AnimatedTiles.xml": "eedb00fc3eb3186cf92b14bc6ac1f080fc0409fa00975d62e84bc400df29e189",
    "Content/Graphics/Sprites.xml": "baec20ec28911be5ef8acc6b181c6818095aa867c692c14d57d26e42c00fc04a",
}


def room_commands(commands, metadata):
    selected = []
    for command in commands:
        x, y = command["x"] - 8, command["y"] - 409
        if not 0 <= x < 40 or not 0 <= y < 23:
            continue
        source = command["source"]
        if source not in TEXTURES[:5]:
            raise ValueError("Room command references an unowned source texture")
        _, sx, sy, width, height, *_ = metadata[source]
        u, v, w, h = command["rectangle"]
        u, v = u - sx, v - sy
        if w != 8 or h != 8 or min(u, v) < 0 or u + w > width or v + h > height or u % 8 or v % 8:
            raise ValueError("Source command outside owned tileset crop")
        selected.append(("B" if command["layer"] == "BG" else "F", TEXTURES.index(source), x * 8, y * 8, u, v))
    return selected


def visual_text(specs, commands):
    if len(specs) != 6 or len(commands) > 1840:
        raise ValueError("Invalid bounded room asset count")
    text = f"CSRV1\n{INPUT_SHA}\n{MAP_SHA}\n6\n"
    for spec in specs:
        text += " ".join(map(str, spec["profile"])) + f" {spec['fnv1a32']:08x}\n"
    text += str(len(commands)) + "\n"
    return text + "".join(" ".join(map(str, command)) + "\n" for command in commands)


def blend_pixel(source, destination):
    return [min(255, round(source[i] + destination[i] * (255 - source[3]) / 255)) for i in range(3)]


def content_probes(crops, metadata, commands):
    probes = []
    foreground = {(x // 8, y // 8) for layer, _, x, y, _, _ in commands if layer == "F"}
    for texture in range(6):
        candidates = [command for command in commands if command[1] == texture]
        if texture == 5:
            candidates = [("P", 5, 11, 132, 0, 0)]
        found = None
        for layer, _, x, y, u, v in candidates:
            width, height = (metadata[TEXTURES[texture]][3:5] if layer == "P" else (8, 8))
            stride = metadata[TEXTURES[texture]][3]
            for dy in range(min(height, 180 - y)):
                for dx in range(width):
                    px, py = x + dx, y + dy
                    if layer != "F" and (px // 8, py // 8) in foreground:
                        continue
                    if layer == "B" and px < 32 and py >= 120:
                        continue
                    index = ((v + dy) * stride + u + dx) * 4
                    rgba = list(crops[TEXTURES[texture]][index:index + 4])
                    if rgba[3] == 255:
                        found = {"texture": texture, "room_pixel": [px, py], "screen_pixel": [px * 3 + 1, 2 + py * 3 + 1], "expected_rgb": rgba[:3]}
                        break
                if found:
                    break
            if found:
                break
        if found is None:
            raise ValueError("No visible opaque content proof for source texture " + TEXTURES[texture])
        probes.append(found)
    return probes


def alpha_probe(crops, metadata, commands):
    def pixel(texture, x, y):
        width = metadata[TEXTURES[texture]][3]
        offset = (y * width + x) * 4
        return list(crops[TEXTURES[texture]][offset:offset + 4])

    for layer, texture, x, y, u, v in commands:
        if layer != "F":
            continue
        for dy in range(min(8, 180 - y)):
            for dx in range(8):
                rgba = pixel(texture, u + dx, v + dy)
                if not 0 < rgba[3] < 255 or max(rgba[:3]) < 20:
                    continue
                px, py = x + dx, y + dy
                if px < 32 and py >= 120:
                    continue
                destination = [9, 11, 18]
                for bg_layer, bg_texture, bx, by, bu, bv in commands:
                    if bg_layer == "B" and bx <= px < bx + 8 and by <= py < by + 8:
                        destination = blend_pixel(pixel(bg_texture, bu + px - bx, bv + py - by), destination)
                expected = blend_pixel(rgba, destination)
                wrong = [round(rgba[i] * rgba[3] / 255 + destination[i] * (255 - rgba[3]) / 255) for i in range(3)]
                if max(abs(a - b) for a, b in zip(expected, wrong)) < 8:
                    continue
                return {"texture": texture, "crop_pixel": [u + dx, v + dy], "source_rgba_unchanged": rgba,
                        "room_pixel": [px, py], "screen_pixel": [px * 3 + 1, 2 + py * 3 + 1],
                        "destination_rgb": destination, "expected_rgb": expected, "wrong_SRC_ALPHA_rgb": wrong,
                        "tolerance": 2, "claim": "One scalar premultiplied blend probe, not a CPU-rendered reference canvas; GPU 8-bit rounding allowed"}
    return None


def prepare(archive_path, oracle, output):
    if not output.resolve().is_relative_to(ROOT / ".audit") or output.exists():
        raise ValueError("Visual assets require a fresh private output directory")
    result = json.loads((oracle / "result.json").read_text())
    if result["status"] != "source-closed-compile-and-bake" or result["identity"] != verify_extraction(oracle):
        raise ValueError("Full source bake is not closed/verified")
    for name, digest in result["artifacts"].items():
        verified_bytes(oracle / name, digest, 32 * 1024 * 1024)
    members, provenance = {}, {}
    for name, data in read_members(archive_path, MEMBERS, 16 * 1024 * 1024).items():
        provenance[name] = {"sha256": MEMBERS[name], "bytes": len(data), "member": name}
        if name.endswith((".data", ".meta")):
            members[name.rsplit("/", 1)[-1]] = data
    metadata = atlas_metadata(members["Gameplay.meta"])
    crops = {}
    for name in TEXTURES:
        sheet, x, y, width, height, *_ = metadata[name]
        if sheet != "Gameplay0":
            raise ValueError("Owned crop references an unexpected atlas sheet")
        crops[name] = (x, y, width, height)
    stream_audit = {}
    crops = decode_crops(members["Gameplay0.data"], crops, stream_audit)
    commands = room_commands(json.loads((oracle / "commands.json").read_text()), metadata)
    counts = Counter(command[0] for command in commands)
    if counts["F"] != 363:
        raise ValueError("Selected room foreground occupancy changed")
    output.mkdir(parents=True)
    specs, files = [], {}
    for i, name in enumerate(TEXTURES):
        _, x, y, width, height, frame_x, frame_y, frame_width, frame_height = metadata[name]
        tw, th = (64, 128) if i < 5 else (16, 16)
        data = extrude(crops[name], width, height, tw, th)
        filename = f"texture{i}.rgba"
        (output / filename).write_bytes(data)
        files[filename] = hashlib.sha256(data).hexdigest()
        specs.append({"source": name, "atlas_rectangle": [x, y, width, height], "frame_fields": [frame_x, frame_y, frame_width, frame_height],
                      "crop_sha256": hashlib.sha256(crops[name]).hexdigest(), "rgba_sha256": files[filename], "fnv1a32": checksum(data),
                      "profile": [tw, th, width, height, -frame_x, -frame_y, frame_width, frame_height]})
    text = visual_text(specs, commands).encode("ascii")
    (output / "visuals.txt").write_bytes(text)
    files["visuals.txt"] = hashlib.sha256(text).hexdigest()
    manifest = {"input_sha256": INPUT_SHA, "map_sha256": MAP_SHA, "selected_room": "1", "members": provenance,
                "archive": archive_identity(archive_path),
                "source_bake": {"path": str(oracle), "result_sha256": hashlib.sha256((oracle / "result.json").read_bytes()).hexdigest(),
                                "source_manifest_sha256": hashlib.sha256((oracle / "source-manifest.json").read_bytes()).hexdigest(), **result["bake"]},
                "textures": specs, "draw_counts": dict(counts), "submitted_rgba_bytes": sum((output / f"texture{i}.rgba").stat().st_size for i in range(6)),
                "camera": [0, 0], "alpha_probe": alpha_probe(crops, metadata, commands), "stream_audit": stream_audit, "files": files,
                "spawn_content_probes": content_probes(crops, metadata, commands),
                "crop_alpha_counts": {name: dict(Counter(crops[name][3::4])) for name in TEXTURES},
                "scope": "Partial static BG -> idle00 BODY -> diagnostic spike markers -> FG; no hair/decals/backdrops/animation/audio/menu/full-game fidelity",
                "memory_claim": "164864 submitted RGBA bytes, max 32768 temporary CPU upload bytes, not exact physical GPU allocation"}
    (output / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ROOT / "game/celeste-linux.zip")
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = prepare(args.archive, args.oracle, args.output)
    print(json.dumps(manifest, indent=2))
