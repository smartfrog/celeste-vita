#!/usr/bin/env python3
"""Extend fresh six-texture room visuals with the two source spike images."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import zipfile

from check_native_oracle import ROOT, verify_extraction
from native_room_textures import atlas_metadata, decode_crops, extrude
from prepare_room_visuals import MEMBERS, TEXTURES, room_commands
from prepare_static_tilemap import INPUT_SHA, MAP_SHA
from stage_native_room import checksum, verified_bytes

UP_CROP_SHA256 = "8bc6e3fa5bb458c0a196b4792a5946b1034cf4dcc5defaa9b39dca845776b617"
LEFT_CROP_SHA256 = "900a3b0f9d6a0a028240b01a25e8b1fb0e3d0d6fe4134c91b9ba3d9eea9ad01f"
FAMILIES = {
    "up": {"key": "danger/spikes/default_up", "entry": "danger/spikes/default_up00",
           "rectangle": [30, 176, 7, 6], "trim": [0, -3], "frame": [8, 9], "draw_offset": [0, 3],
           "justify": [0.5, 1.0], "crop_sha256": UP_CROP_SHA256},
    "left": {"key": "danger/spikes/default_left", "entry": "danger/spikes/default_left00",
             "rectangle": [22, 193, 6, 7], "trim": [-3, -1], "frame": [9, 8], "draw_offset": [3, 1],
             "justify": [1.0, 0.5], "crop_sha256": LEFT_CROP_SHA256},
}


def profile_row(values, digest):
    return " ".join(map(str, values)) + f" {digest:08x}\n"


def parse_visual_text(text):
    lines = text.splitlines()
    if lines[:3] != ["CSRV1", INPUT_SHA, MAP_SHA] or lines[3] != "6":
        raise ValueError("Six-texture source visual identity changed")
    profiles = lines[4:10]
    if any(len(row.split()) != 9 for row in profiles):
        raise ValueError("Malformed source visual texture profile")
    count = int(lines[10])
    commands = lines[11:11 + count]
    if len(commands) != count or len(lines) != 11 + count:
        raise ValueError("Malformed source visual command block")
    return profiles, commands


def float32(bits):
    return struct.unpack(">f", bytes.fromhex(bits))[0]


def close(left, right):
    return abs(left - right) <= 0.00001


def verify_piece(piece, hazards, families):
    direction = piece["direction"]
    family = families[direction]
    hazard = hazards[piece["hazard"]]
    if hazard["direction"] != direction or piece["texture"] != family["entry"] or piece["clip"] != family["rectangle"]:
        raise ValueError("Spike piece references an unexpected hazard/family/clip")
    x, y = piece["x"], piece["y"]
    hazard_x, hazard_y = hazard["position"]
    if direction == "up":
        expected = (hazard_x + piece["index"] * 8, hazard_y - 5)
    else:
        expected = (hazard_x - 5, hazard_y + 1 + piece["index"] * 8)
    if (x, y) != expected or piece["width"] != family["rectangle"][2] or piece["height"] != family["rectangle"][3]:
        raise ValueError("Spike piece geometry differs from the source placement contract")
    position = (float32(piece["position_bits"][0]), float32(piece["position_bits"][1]))
    recorded_origin = (float32(piece["origin_bits"][0]), float32(piece["origin_bits"][1]))
    expected_origin = (family["frame"][0] * family["justify"][0] - family["draw_offset"][0],
                       family["frame"][1] * family["justify"][1] - family["draw_offset"][1])
    if not close(recorded_origin[0], expected_origin[0]) or not close(recorded_origin[1], expected_origin[1]):
        raise ValueError("Spike source justified origin/draw offset changed")
    top_left = (position[0] - recorded_origin[0], position[1] - recorded_origin[1])
    if not close(top_left[0], x) or not close(top_left[1], y):
        raise ValueError("Spike source draw geometry does not resolve to the recorded top-left")
    if any(not close(value, 1.0) for value in (float32(piece["scale_bits"][0]), float32(piece["scale_bits"][1]))):
        raise ValueError("Spike source scale changed")
    if not close(float32(piece["rotation_bits"]), 0.0):
        raise ValueError("Spike source rotation changed")
    vertices = [float32(value) for value in piece["vertices_bits"]]
    if (not close(vertices[0], x) or not close(vertices[1], y) or not close(vertices[2], x + piece["width"]) or
            not close(vertices[3], y) or not close(vertices[4], x) or not close(vertices[5], y + piece["height"]) or
            not close(vertices[6], x + piece["width"]) or not close(vertices[7], y + piece["height"])):
        raise ValueError("FNA vertex corners differ from the recorded spike quad")
    u0, v0 = family["rectangle"][0] / 4096.0, family["rectangle"][1] / 4096.0
    u1, v1 = (family["rectangle"][0] + family["rectangle"][2]) / 4096.0, (family["rectangle"][1] + family["rectangle"][3]) / 4096.0
    texcoords = [float32(value) for value in piece["texcoords_bits"]]
    expected_texcoords = [u0, v0, u1, v0, u0, v1, u1, v1]
    if any(not close(a, b) for a, b in zip(texcoords, expected_texcoords)):
        raise ValueError("Source atlas texcoords changed")
    return {"direction": direction, "hazard": piece["hazard"], "index": piece["index"], "x": x, "y": y,
            "width": piece["width"], "height": piece["height"], "texture": piece["texture"]}


def build_content_probes(pieces, crops, commands, atlas):
    def tile_pixel(texture, u, v):
        name = TEXTURES[texture]
        width = int(atlas[name][3])
        offset = (v * width + u) * 4
        return list(crops[name][offset:offset + 4])

    def foreground(px, py):
        for layer, texture, x, y, u, v in commands:
            if layer == "F" and x <= px < x + 8 and y <= py < y + 8:
                return texture, u + px - x, v + py - y, tile_pixel(texture, u + px - x, v + py - y)
        return None

    probes, coverage = [], []
    for piece in pieces:
        direction = piece["direction"]
        crop = crops["danger/spikes/default_" + direction + "00"]
        width, height = piece["width"], piece["height"]
        visible = hidden = 0
        visible_probe = hidden_probe = None
        for dy in range(height):
            for dx in range(width):
                offset = (dy * width + dx) * 4
                rgba = list(crop[offset:offset + 4])
                if rgba[3] != 255:
                    continue
                px, py = piece["x"] + dx, piece["y"] + dy
                occluder = foreground(px, py)
                if occluder is None:
                    visible += 1
                    if visible_probe is None:
                        visible_probe = {"kind": "visible_source_spike", "direction": direction,
                                         "piece": [piece["hazard"], piece["index"]], "room_pixel": [px, py],
                                         "screen_pixel": [px * 3 + 1, 2 + py * 3 + 1],
                                         "source_rgba": rgba, "expected_rgb": rgba[:3],
                                         "claim": "Opaque source spike texel outside the foreground tile overlay"}
                elif occluder[3][3] == 255:
                    hidden += 1
                    if hidden_probe is None:
                        hidden_probe = {"kind": "foreground_occludes_spike", "direction": direction,
                                        "piece": [piece["hazard"], piece["index"]], "room_pixel": [px, py],
                                        "screen_pixel": [px * 3 + 1, 2 + py * 3 + 1],
                                        "spike_rgba": rgba, "occluder_texture": occluder[0],
                                        "occluder_source_pixel": [occluder[1], occluder[2]],
                                        "expected_rgb": occluder[3][:3],
                                        "claim": "Opaque foreground texel must replace the spike image at this location"}
        if visible == 0 or hidden == 0:
            raise ValueError("Spike piece is not partly visible and partly foreground-occluded")
        coverage.append({"direction": direction, "piece": [piece["hazard"], piece["index"]],
                         "visible_opaque_texels": visible, "occluded_opaque_texels": hidden})
        probes.extend(probe for probe in (visible_probe, hidden_probe) if probe is not None)
    return probes, coverage


def prepare(visual_dir, oracle, archive_path, output):
    output = output.resolve()
    if not output.is_relative_to(ROOT / ".audit") or output.exists():
        raise ValueError("Spike art requires a fresh private output directory")
    visual = json.loads((visual_dir / "provenance.json").read_text())
    if (visual["input_sha256"], visual["map_sha256"], visual["selected_room"]) != (INPUT_SHA, MAP_SHA, "1"):
        raise ValueError("Wrong six-texture prepared visual provenance")
    if set(visual["files"]) != {"visuals.txt", *(f"texture{i}.rgba" for i in range(6))} or visual["submitted_rgba_bytes"] != 164864:
        raise ValueError("Unexpected six-texture visual asset set")
    for name, digest in visual["files"].items():
        verified_bytes(visual_dir / name, digest, 65_536)
    old_text = (visual_dir / "visuals.txt").read_text()
    profiles, commands_text = parse_visual_text(old_text)
    commands = []
    for row in commands_text:
        layer, texture, x, y, u, v = row.split()
        commands.append((layer, int(texture), int(x), int(y), int(u), int(v)))
    counts = Counter(command[0] for command in commands)
    if counts["F"] != 363 or counts["B"] != 620:
        raise ValueError("Source room layer draw counts changed")
    result = json.loads((oracle / "result.json").read_text())
    if result["status"] != "source-spike-art-closed" or result["identity"] != verify_extraction(oracle):
        raise ValueError("Spike source oracle is not closed/verified")
    for name, digest in result["artifacts"].items():
        verified_bytes(oracle / name, digest, 16 * 1024 * 1024)
    spike = result["oracle"]
    if spike["status"] != "source-spike-art-executed" or spike["draws"] != 19 or len(spike["pieces"]) != 19:
        raise ValueError("Spike oracle does not expose nineteen source pieces")
    for direction, family in FAMILIES.items():
        recorded = spike["families"][direction]
        if recorded["count"] != 1 or recorded["entry"] != family["entry"] or recorded["rectangle"] != family["rectangle"] or \
                recorded["trim"] != family["trim"] or recorded["frame"] != family["frame"] or recorded["draw_offset"] != family["draw_offset"]:
            raise ValueError("Spike family singleton/pinned metadata changed: " + direction)
    hazards = spike["hazards"]
    if [hazard["position"] for hazard in hazards] != [[40, 168], [104, 152], [176, 128], [208, 160], [272, 80]]:
        raise ValueError("Selected room spike set changed")
    if [hazard["size"] for hazard in hazards] != [40, 40, 32, 24, 16]:
        raise ValueError("Selected room spike sizes changed")
    if [hazard["pieces"] for hazard in hazards] != [5, 5, 4, 3, 2]:
        raise ValueError("Source spike piece counts changed")
    if [piece["direction"] for piece in spike["pieces"]].count("up") != 17 or [piece["direction"] for piece in spike["pieces"]].count("left") != 2:
        raise ValueError("Source spike orientation counts changed")
    for run_row in spike["runs"]:
        if run_row["draws"] != 19 or run_row["rng"]["next_calls"] != 19 or set(run_row["rng"]["next_maximums"]) != {1} or set(run_row["rng"]["results"]) != {0}:
            raise ValueError("Original source Choose RNG invariant failed")
    atlas = atlas_metadata_cache_init(archive_path)
    pieces = [verify_piece(piece, hazards, FAMILIES) for piece in spike["pieces"]]
    with zipfile.ZipFile(archive_path) as archive:
        sheet = archive.read("Content/Graphics/Atlases/Gameplay0.data")
    crops = {}
    for name in TEXTURES:
        _, x, y, width, height, *_ = atlas[name]
        crops[name] = decode_crops(sheet, {name: (x, y, width, height)})[name]
    spike_crops = {}
    for direction, family in FAMILIES.items():
        _, x, y, width, height, *_ = atlas[family["entry"]]
        crop = decode_crops(sheet, {family["entry"]: (x, y, width, height)})[family["entry"]]
        if hashlib.sha256(crop).hexdigest() != family["crop_sha256"] or set(crop[3::4]) != {0, 255}:
            raise ValueError("Pinned source spike crop identity/alpha bytes changed")
        spike_crops["danger/spikes/default_" + direction + "00"] = crop
    output.mkdir(parents=True)
    files, texture_specs = {}, []
    for index in range(6):
        name = f"texture{index}.rgba"
        data = (visual_dir / name).read_bytes()
        (output / name).write_bytes(data)
        files[name] = hashlib.sha256(data).hexdigest()
    for index, (direction, family) in enumerate(FAMILIES.items(), start=6):
        crop = spike_crops[family["entry"]]
        width, height = family["rectangle"][2], family["rectangle"][3]
        data = extrude(crop, width, height, 16, 16)
        name = f"texture{index}.rgba"
        (output / name).write_bytes(data)
        files[name] = hashlib.sha256(data).hexdigest()
        texture_specs.append({"source": family["entry"], "atlas_rectangle": family["rectangle"],
                              "crop_sha256": family["crop_sha256"], "rgba_sha256": files[name], "fnv1a32": checksum(data),
                              "profile": [16, 16, width, height, 1, 1, width, height],
                              "draw_offset": family["draw_offset"], "alpha_values": sorted(set(crop[3::4]))})
    text = f"CSRV2\n{INPUT_SHA}\n{MAP_SHA}\n8\n" + "".join(row + "\n" for row in profiles) + "".join(
        profile_row(spec["profile"], spec["fnv1a32"]) for spec in texture_specs)
    text += f"{len(commands)}\n" + "".join(row + "\n" for row in commands_text) + "2\n"
    text += "default_up 1\ndefault_left 1\n19\n"
    text += "".join(f"{piece['direction']} {piece['x']} {piece['y']} {piece['width']} {piece['height']} 1 1\n" for piece in pieces)
    data = text.encode("ascii")
    (output / "visuals.txt").write_bytes(data)
    files["visuals.txt"] = hashlib.sha256(data).hexdigest()
    probes, coverage = build_content_probes(pieces, {**crops, **spike_crops}, commands, atlas)
    manifest = {"input_sha256": INPUT_SHA, "map_sha256": MAP_SHA, "selected_room": "1",
                "visuals_source": {"path": str(visual_dir), "provenance_sha256": hashlib.sha256((visual_dir / "provenance.json").read_bytes()).hexdigest()},
                "spike_oracle": {"path": str(oracle), "result_sha256": hashlib.sha256((oracle / "result.json").read_bytes()).hexdigest(),
                                 "source_manifest_sha256": hashlib.sha256((oracle / "source-manifest.json").read_bytes()).hexdigest(),
                                 "families": FAMILIES, "hazards": hazards, "pieces": pieces, "runs": spike["runs"]},
                "spike_textures": texture_specs, "draw_counts": dict(counts), "render_order": "BG -> hair/body -> source static spikes -> FG",
                "submitted_rgba_bytes": 164864 + sum(len((output / f"texture{i}.rgba").read_bytes()) for i in range(6, 8)),
                "additional_spike_rgba_bytes": 2048, "max_temporary_cpu_upload_bytes": 32768,
                "spike_content_probes": probes, "piece_visibility": coverage,
                "spawn_content_probes": visual["spawn_content_probes"], "alpha_probe": visual["alpha_probe"],
                "camera": [0, 0], "files": files,
                "scope": "Partial static BG -> hair/body -> nineteen source spike images -> FG; old six-texture and debug modes remain available; no death/respawn/full-game fidelity",
                "memory_claim": "166912 submitted RGBA bytes, max 32768 temporary CPU upload bytes, not exact physical GPU allocation"}
    (output / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def atlas_metadata_cache_init(archive_path):
    with zipfile.ZipFile(archive_path) as archive:
        if archive.getinfo("Content/Graphics/Atlases/Gameplay.meta").file_size > 16 * 1024 * 1024:
            raise ValueError("Oversized atlas metadata")
        metadata = archive.read("Content/Graphics/Atlases/Gameplay.meta")
    if hashlib.sha256(metadata).hexdigest() != MEMBERS["Content/Graphics/Atlases/Gameplay.meta"]:
        raise ValueError("Atlas metadata identity changed")
    return atlas_metadata(metadata)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--visuals", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--archive", type=Path, default=ROOT / "game/celeste-linux.zip")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = prepare(args.visuals, args.oracle, args.archive, args.output)
    print(json.dumps(manifest, indent=2))
