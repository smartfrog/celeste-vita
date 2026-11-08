#!/usr/bin/env python3
"""Pack the 15 source static decal crops and emit the bounded CSD1 draw protocol."""

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import zipfile

from check_native_oracle import ROOT, verify_extraction
from native_room_textures import atlas_metadata, decode_crops, extrude
from prepare_static_tilemap import INPUT_SHA, MAP_SHA
from stage_native_room import checksum, verified_bytes

GAMEPLAY_META_SHA = "1f23b1f35544a3751ffec170b0230c7c9513000ab1549f78ebb9cb9f4203c8d9"
GAMEPLAY_DATA_SHA = "687f3340c937e3baca71758bfb1e6b8e799ad896f2df19bef26ec64968b3490b"
RAW_ROOM_SHA = "3eefb6d3fae3cc0977583d8f53075da3db98da01795c0ce56f5b799e8bc65eb3"
PAGE_WIDTH, PAGE_HEIGHT = 64, 128
STATIC_CROP_SHA = {
    "decals/generic/hanginggrass_a": "94aaf0d99b846ab8e52b3d50adb6cc63600694525eb1173a743719bd16066743",
    "decals/generic/snow_b": "360e60094744e2520fc5e76ac276ebb3e02e8e93054c4ffca2e02e76fff83a49",
    "decals/1-forsakencity/collumn_small_broken": "d1415715ab8f2f4ee2c4ec014aa83d15d5afea7220cec17b34f218ec80fa8ebc",
    "decals/1-forsakencity/collumn_small_E": "8f5783e19bb6325a9c8656b8747f7ba1e97892d128b7b75f3550efe00ceaa03d",
    "decals/1-forsakencity/Collumn_concrete_E_broken": "8cd2b395e807d147b9731d4c6a534599cce380953fa3492bf8aa979e9bf8f43c",
    "decals/1-forsakencity/sign_under_construction": "f97a0a92655a5dda6d2809259ba30b7ca5d2dec025335dc4083b51cb932c7025",
    "decals/1-forsakencity/box": "f4e141dd159731b67dae2b95b166aa200d9661c0b0dea2d40e773eea2c4937d4",
    "decals/1-forsakencity/windowA": "338141780e3edcf3a6a5a2295fe3470367a06538f150a3c3de96c6c575df57f5",
    "decals/1-forsakencity/posterE": "e8ab559eb611799019c5a54f3d38b303a8fbe7c03655b52b03c7fdc13aa5f9a5",
    "decals/1-forsakencity/posterA": "8fa8a1acba4ab376ac5c4f33b69698f5e0fbc9f5fa91c039c841b85c547ee2c1",
    "decals/generic/snow_c": "4a7d9a90f45fe5ea53f74b48231bbbbb16f7ff48f8154f9f4e7abd57253cff08",
    "decals/generic/snow_d": "9ca9a048afad7cd43c600d9d11a11bba00a00e47122ede2fad481ea171b5bf1b",
    "decals/generic/snow_e": "a0165919c3edee067ad796f396305f0efcb80f8cafe9531ab9d319ac91ce5e84",
    "decals/generic/snow_g": "23dcfe49f8b49cd405945a879d5822d1b823b8abc7ca80a2ddebaeda4f023b94",
    "decals/generic/snow_h": "fcf1afdb5bd74c42fd957a1a685fd01756b1e58d018160cff92930a0d985a647",
}
EXPECTED_PIXELS, EXPECTED_RGBA, EXPECTED_ALPHA = 3378, 13512, 2367
EXPECTED_BANNERS = {( "F", 2, "generic/grass_a"), ("F", 3, "generic/grass_d"),
                    ("B", 20, "1-forsakencity/ragsB"), ("B", 21, "1-forsakencity/rags"),
                    ("B", 22, "1-forsakencity/ragsB"), ("B", 23, "1-forsakencity/rags"),
                    ("B", 24, "1-forsakencity/ragsB")}


def static_instances(oracle):
    draws = oracle["static_profile"]["draws"]
    if len(draws) != 22 or oracle["banner_exclusion"]["count"] != 7:
        raise ValueError("Decal oracle is not the closed 22/7 source profile")
    instances = []
    for draw in draws:
        texture = draw["name"]
        if texture not in STATIC_CROP_SHA:
            raise ValueError("Unexpected static decal texture: " + texture)
        instances.append({"group": draw["group"], "source_index": draw["source_index"], "name": texture,
                          "texture": draw["texture"], "position": draw["position"], "scale": draw["scale"],
                          "atlas_clip": draw["atlas_clip"], "frame": draw["frame"], "draw_offset": draw["draw_offset"],
                          "origin": draw["origin"], "depth": draw["depth"],
                          "position_bits": draw["position_bits"], "origin_bits": draw["origin_bits"],
                          "scale_bits": draw["scale_bits"], "vertices_bits": draw["vertices_bits"],
                          "texcoords_bits": draw["texcoords_bits"]})
    banners = []
    for attempt in oracle["banner_exclusion"]["attempts"]:
        layer = "B" if attempt["group"] == "bgdecals" else "F"
        banners.append((layer, attempt["source_index"], attempt["name"].removeprefix("decals/")))
    if set(banners) != EXPECTED_BANNERS:
        raise ValueError("Banner omission set differs from the source-proven seven")
    return instances, banners


def verify_atlas(instances, metadata):
    for instance in instances:
        record = metadata.get(instance["name"])
        if record is None:
            raise ValueError("Missing source atlas entry: " + instance["name"])
        _, x, y, width, height, offset_x, offset_y, frame_width, frame_height = record
        expected_clip = [x, y, width, height]
        expected_offset = [-offset_x, -offset_y]
        if (record[0] != "Gameplay0" or instance["atlas_clip"] != expected_clip or
                instance["frame"] != [frame_width, frame_height] or instance["draw_offset"] != expected_offset):
            raise ValueError("Source atlas metadata differs from executed Decal draw: " + instance["name"])
        expected_origin = [frame_width / 2 - expected_offset[0], frame_height / 2 - expected_offset[1]]
        if instance["origin"] != expected_origin:
            raise ValueError("Decal origin is not Center-DrawOffset: " + instance["name"])


def decode_static_crops(archive_path, names):
    with zipfile.ZipFile(archive_path) as archive:
        meta = archive.read("Content/Graphics/Atlases/Gameplay.meta")
        data = archive.read("Content/Graphics/Atlases/Gameplay0.data")
    if hashlib.sha256(meta).hexdigest() != GAMEPLAY_META_SHA or hashlib.sha256(data).hexdigest() != GAMEPLAY_DATA_SHA:
        raise ValueError("Pinned Gameplay atlas identity changed")
    metadata = atlas_metadata(meta)
    crops = {}
    for name in names:
        _, x, y, width, height, *_ = metadata[name]
        crops[name] = (x, y, width, height)
    decoded = decode_crops(data, crops)
    pixels = alpha = 0
    for name, buffer in decoded.items():
        if hashlib.sha256(buffer).hexdigest() != STATIC_CROP_SHA[name]:
            raise ValueError("Pinned static decal crop identity changed: " + name)
        values = buffer[3::4]
        if set(values) - {0, 255}:
            raise ValueError("Unexpected partial alpha in a static decal crop: " + name)
        pixels += len(values)
        alpha += sum(value != 0 for value in values)
    if (pixels, pixels * 4, alpha) != (EXPECTED_PIXELS, EXPECTED_RGBA, EXPECTED_ALPHA):
        raise ValueError("Static decal crop pixel/alpha totals changed")
    return metadata, decoded


def pack(crops, metadata):
    names = sorted(crops, key=lambda name: (-metadata[name][4], -metadata[name][3], name))
    page = bytearray(PAGE_WIDTH * PAGE_HEIGHT * 4)
    occupied = bytearray(PAGE_WIDTH * PAGE_HEIGHT)
    placed = {}
    x, y, shelf = 1, 1, 0
    for name in names:
        _, _, _, width, height, *_ = metadata[name]
        if x + width + 1 > PAGE_WIDTH:
            y += shelf + 2
            x, shelf = 1, 0
        if y + height + 1 > PAGE_HEIGHT:
            raise ValueError("Static decal atlas page cannot fit the 15 bounded crops")
        padded = extrude(crops[name], width, height, width + 2, height + 2)
        for py in range(height + 2):
            for px in range(width + 2):
                gx, gy = x - 1 + px, y - 1 + py
                cell = gy * PAGE_WIDTH + gx
                if occupied[cell]:
                    raise ValueError("Static decal atlas page overlap")
                occupied[cell] = 1
                source = (py * (width + 2) + px) * 4
                target = cell * 4
                page[target:target + 4] = padded[source:source + 4]
        placed[name] = (x, y, width, height)
        x += width + 2
        shelf = max(shelf, height)
    expected = sum((metadata[name][3] + 2) * (metadata[name][4] + 2) for name in names)
    if len(page) != 32768 or sum(occupied) != expected:
        raise ValueError("Static decal page byte/occupancy total changed")
    return bytes(page), placed


def render_order(instances):
    return sorted(instances, key=lambda instance: (-instance["depth"], 0 if instance["group"] == "bgdecals" else 1,
                                                   instance["source_index"]))


def parse_visual_commands(visuals):
    text = (Path(visuals) / "visuals.txt").read_text()
    lines = text.splitlines()
    if len(lines) < 5 or lines[0] not in {"CSRV1", "CSRV2"}:
        raise ValueError("Unexpected prepared visuals protocol for decal probes")
    textures = int(lines[3])
    count_at = 4 + textures
    if count_at >= len(lines):
        raise ValueError("Truncated prepared visual command headers")
    count = int(lines[count_at])
    if len(lines) < count_at + 1 + count:
        raise ValueError("Malformed prepared visual commands")
    foreground = []
    counts = Counter()
    for row in lines[count_at + 1:count_at + 1 + count]:
        layer, texture, x, y, u, v = row.split()
        counts[layer] += 1
        if layer == "F":
            foreground.append((int(x), int(y)))
    if counts["F"] != 363 or counts["B"] != 620:
        raise ValueError("Prepared source tile layer counts changed")
    return foreground


def hazard_rects(hazards):
    rows = json.loads(Path(hazards).read_text())
    rects = []
    for hazard in rows:
        x, y, size = hazard["x"], hazard["y"], hazard["size"]
        if hazard["direction"] == "up":
            rects.append((x, y - 8, x + size, y + 1))
        else:
            rects.append((x - 8, y, x + 1, y + size))
    return rects


def quad_rect(instance, placed):
    x, y, width, height = placed[instance["name"]]
    origin_x, origin_y = instance["origin"]
    sx, sy = instance["scale"]
    px, py = instance["position"]
    left = px - origin_x * sx
    top = py - origin_y * sy
    right = left + width * sx
    bottom = top + height * sy
    return min(left, right), min(top, bottom), max(left, right), max(top, bottom)


def mapped_pixel(instance, placed, dx, dy):
    x, y, width, height = placed[instance["name"]]
    origin_x, origin_y = instance["origin"]
    sx, sy = instance["scale"]
    px, py = instance["position"]
    left = px - origin_x * sx
    top = py - origin_y * sy
    if sx == 1:
        screen_x = left + dx
    else:
        screen_x = left - dx - 1
    if sy == 1:
        screen_y = top + dy
    else:
        screen_y = top - dy - 1
    return math.floor(screen_x), math.floor(screen_y)


def covered(pixel, later, foreground, hazards, player_zone):
    x, y = pixel
    if player_zone and 0 <= x < 48 and 108 <= y < 180:
        return True
    if any(left <= x <= right and top <= y <= bottom for left, top, right, bottom in hazards):
        return True
    if (x // 8 * 8, y // 8 * 8) in foreground:
        return True
    if any(left <= x <= right and top <= y <= bottom for left, top, right, bottom in later):
        return True
    return False


def content_probes(instances, placed, crops, metadata, foreground, hazards):
    ordered = render_order(instances)
    wanted = {
        "visible_static_bg_positive": lambda i: i["group"] == "bgdecals" and i["scale"] == [1, 1],
        "visible_static_bg_flip_horizontal": lambda i: i["group"] == "bgdecals" and i["scale"] == [-1, 1],
        "visible_static_bg_flip_vertical": lambda i: i["group"] == "bgdecals" and i["scale"] == [1, -1],
        "visible_static_fg": lambda i: i["group"] == "fgdecals",
    }
    probes = {}
    for kind, predicate in wanted.items():
        for index, instance in enumerate(ordered):
            if not predicate(instance):
                continue
            later = [quad_rect(other, placed) for other in ordered[index + 1:]
                     if other["group"] == instance["group"]]
            _, _, width, height = placed[instance["name"]]
            _, _, _, crop_width, crop_height, *_ = metadata[instance["name"]]
            if (width, height) != (crop_width, crop_height):
                raise ValueError("Placed crop dimensions changed")
            for dy in range(height):
                for dx in range(width):
                    offset = (dy * width + dx) * 4
                    rgba = list(crops[instance["name"]][offset:offset + 4])
                    if rgba[3] != 255:
                        continue
                    room = mapped_pixel(instance, placed, dx, dy)
                    if not (0 <= room[0] < 320 and 0 <= room[1] < 180):
                        continue
                    if covered(room, later, foreground if instance["group"] == "bgdecals" else set(),
                               hazards if instance["group"] == "bgdecals" else [], instance["group"] == "bgdecals"):
                        continue
                    probes[kind] = {"kind": kind, "group": instance["group"], "source_index": instance["source_index"],
                                    "name": instance["name"], "room_pixel": list(room),
                                    "screen_pixel": [room[0] * 3 + 1, 2 + room[1] * 3 + 1],
                                    "crop_pixel": [dx, dy], "scale": instance["scale"], "depth": instance["depth"],
                                    "source_rgba": rgba, "expected_rgb": rgba[:3],
                                    "claim": "Opaque source crop texel mapped through signed DecalImage transform and not covered by a later source layer"}
                    break
                if kind in probes:
                    break
            if kind in probes:
                break
        if kind not in probes:
            raise ValueError("No visible native probe for " + kind)
    return list(probes.values())


def protocol_text(textures, instances, banners, page):
    texture_index = {name: index for index, name in enumerate(textures)}
    text = f"CSD1\n{INPUT_SHA}\n{MAP_SHA}\n1\n{PAGE_WIDTH} {PAGE_HEIGHT} {checksum(page):08x}\n{len(textures)}\n"
    for name in textures:
        entry = textures[name]
        text += (f"{name} {entry['u']} {entry['v']} {entry['width']} {entry['height']} "
                 f"{entry['draw_offset'][0]} {entry['draw_offset'][1]} {entry['frame'][0]} {entry['frame'][1]}\n")
    text += f"{len(instances)}\n"
    for instance in instances:
        layer = "B" if instance["group"] == "bgdecals" else "F"
        text += (f"{layer} {instance['source_index']} {instance['position'][0]} {instance['position'][1]} "
                 f"{instance['scale'][0]} {instance['scale'][1]} {texture_index[instance['name']]}\n")
    text += f"{len(banners)}\n"
    text += "".join(f"{layer} {index} {name}\n" for layer, index, name in banners)
    return text.encode("ascii")


def prepare(oracle, raw_room, archive, visuals, hazards, output):
    output = output.resolve()
    if not output.is_relative_to(ROOT / ".audit") or output.exists():
        raise ValueError("Decal assets require a fresh private output directory")
    if hashlib.sha256(Path(raw_room).read_bytes()).hexdigest() != RAW_ROOM_SHA:
        raise ValueError("Raw room placement identity changed")
    result = json.loads((Path(oracle) / "result.json").read_text())
    if result["status"] != "source-static-decals-closed" or result["identity"] != verify_extraction(Path(oracle)):
        raise ValueError("Decal source oracle is not closed/verified")
    for name, digest in result["artifacts"].items():
        verified_bytes(Path(oracle) / name, digest, 32 * 1024 * 1024)
    source = result["oracle"]
    instances, banners = static_instances(source)
    names = sorted({instance["name"] for instance in instances})
    if len(names) != 15:
        raise ValueError("Static unique texture count changed")
    metadata, crops = decode_static_crops(archive, names)
    verify_atlas(instances, metadata)
    page, placed = pack(crops, metadata)
    foreground = parse_visual_commands(visuals)
    hazard_rows = hazard_rects(hazards)
    ordered = render_order(instances)
    probes = content_probes(ordered, placed, crops, metadata, set(foreground), hazard_rows)
    textures = {}
    for name in names:
        u, v, width, height = placed[name]
        _, _, _, _, _, offset_x, offset_y, frame_width, frame_height = metadata[name]
        textures[name] = {"name": name, "u": u, "v": v, "width": width, "height": height,
                          "atlas_clip": instance_clip(instances, name), "draw_offset": [-offset_x, -offset_y],
                          "frame": [frame_width, frame_height],
                          "crop_sha256": STATIC_CROP_SHA[name],
                          "alpha_values": sorted(set(crops[name][3::4]))}
    protocol = protocol_text(textures, ordered, sorted(banners), page)
    output.mkdir(parents=True)
    (output / "decal0.rgba").write_bytes(page)
    (output / "decals.txt").write_bytes(protocol)
    manifest = {"input_sha256": INPUT_SHA, "map_sha256": MAP_SHA, "selected_room": "1",
                "raw_room": {"path": str(Path(raw_room).resolve()), "sha256": RAW_ROOM_SHA},
                "placement_source": {"raw_room_fields": {"level_name": "lvl_1", "bounds": [0, 0, 320, 184]},
                                     "runtime_normalization": {"level_name": "1", "load_seed": 49, "logical_size": [320, 180]},
                                     "note": "raw map labels only; decal x/y are used through the unchanged Decal source path, not a runtime LevelData/seed-478 claim"},
                "oracle": {"path": str(Path(oracle).resolve()),
                           "result_sha256": hashlib.sha256((Path(oracle) / "result.json").read_bytes()).hexdigest(),
                           "source_manifest_sha256": hashlib.sha256((Path(oracle) / "source-manifest.json").read_bytes()).hexdigest()},
                "visuals": {"path": str(Path(visuals).resolve()),
                            "provenance_sha256": hashlib.sha256((Path(visuals) / "provenance.json").read_bytes()).hexdigest()},
                "hazards": {"path": str(Path(hazards).resolve()),
                            "sha256": hashlib.sha256(Path(hazards).read_bytes()).hexdigest()},
                "classification": {"static": 22, "bg": 20, "fg": 2, "banner_omitted": 7,
                                   "unique_static_textures": 15, "render_order": "BG tiles -> 20 static BG decals -> player -> 19 spikes -> FG tiles -> 2 static FG decals",
                                   "banner_ids": [list(row) for row in sorted(banners)]},
                "page": {"width": PAGE_WIDTH, "height": PAGE_HEIGHT, "bytes": len(page),
                         "sha256": hashlib.sha256(page).hexdigest(), "fnv1a32": checksum(page),
                         "padding": "one-pixel edge extrusion on all four sides of every crop",
                         "packing": "height-first shelf below one private 64x128 RGBA page; actual bounds/overlap/total verified"},
                "textures": textures, "crops": {"total_pixels": EXPECTED_PIXELS, "rgba_bytes": EXPECTED_RGBA,
                                                "alpha_nonzero": EXPECTED_ALPHA, "semi_alpha": 0,
                                                "decode_recipe": "A=0 two-byte [n,0] run; A>0 five-byte [n,A,B,G,R]; no unpremultiply"},
                "instances": ordered, "content_probes": probes,
                "submitted_decal_rgba_bytes": len(page), "max_temporary_cpu_upload_bytes": 32768,
                "files": {"decal0.rgba": hashlib.sha256(page).hexdigest(),
                          "decals.txt": hashlib.sha256(protocol).hexdigest()},
                "scope": "22 source-proven static DecalImage instances only; 7 animated Banner decals explicitly omitted; no parallax, scared animal, mirror, smoke or banner phase",
                "memory_claim": "32768 submitted decal RGBA bytes, max 32768 temporary CPU upload bytes, not exact physical GPU allocation"}
    (output / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def instance_clip(instances, name):
    clips = {tuple(instance["atlas_clip"]) for instance in instances if instance["name"] == name}
    if len(clips) != 1:
        raise ValueError("One texture name resolved to multiple source clips")
    return list(clips.pop())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--raw-room", type=Path, required=True)
    parser.add_argument("--archive", type=Path, default=ROOT / "game/celeste-linux.zip")
    parser.add_argument("--visuals", type=Path, required=True, help="Prepared six-texture visuals for tile occlusion probes")
    parser.add_argument("--hazards", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = prepare(args.oracle, args.raw_room, args.archive, args.visuals, args.hazards, args.output)
    print(json.dumps(manifest, indent=2))
