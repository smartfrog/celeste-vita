#!/usr/bin/env python3
"""Compare packed static decal draws against the executed original Decal source records."""

import argparse
import hashlib
import json
import struct
from pathlib import Path

from check_native_oracle import ROOT, verify_extraction
from prepare_static_tilemap import INPUT_SHA, MAP_SHA
from prepare_decals import EXPECTED_BANNERS
from stage_native_room import checksum, verified_bytes


def f32(value):
    return struct.unpack(">f", struct.pack(">f", value))[0]


def bits(value):
    return struct.unpack(">I", struct.pack(">f", f32(value)))[0]


def recompute_quad(instance, texture):
    origin_x = f32(f32(texture["frame"][0]) * f32(0.5) - texture["draw_offset"][0])
    origin_y = f32(f32(texture["frame"][1]) * f32(0.5) - texture["draw_offset"][1])
    left = f32(instance["position"][0] - f32(origin_x * instance["scale"][0]))
    top = f32(instance["position"][1] - f32(origin_y * instance["scale"][1]))
    right = f32(left + f32(texture["width"] * instance["scale"][0]))
    bottom = f32(top + f32(texture["height"] * instance["scale"][1]))
    u0 = f32(texture["u"] / texture["page"][0])
    v0 = f32(texture["v"] / texture["page"][1])
    u1 = f32((texture["u"] + texture["width"]) / texture["page"][0])
    v1 = f32((texture["v"] + texture["height"]) / texture["page"][1])
    return {"left": left, "top": top, "right": right, "bottom": bottom, "u0": u0, "v0": v0, "u1": u1, "v1": v1}


def packed_crop(page, texture, page_width):
    rows = []
    for dy in range(texture["height"]):
        start = ((texture["v"] + dy) * page_width + texture["u"]) * 4
        rows.append(page[start:start + texture["width"] * 4])
    return b"".join(rows)


def verify_instance(draw, instance, texture, page, page_width):
    for key in ("group", "source_index", "name", "position", "scale", "depth", "frame", "draw_offset", "origin"):
        if draw[key] != instance[key]:
            raise ValueError(f"Packed decal source identity changed: {instance['group']} {instance['source_index']} {key}")
    if draw["behavior"] != "DecalImage":
        raise ValueError("Animated Banner draw leaked into the static profile")
    if hashlib.sha256(packed_crop(page, texture, page_width)).hexdigest() != texture["crop_sha256"]:
        raise ValueError("Packed decal crop bytes differ from the pinned source crop")
    quad = recompute_quad(instance, texture)
    corners = [(quad["left"], quad["top"]), (quad["right"], quad["top"]),
               (quad["right"], quad["bottom"]), (quad["left"], quad["bottom"])]
    recorded = [(struct.unpack(">f", bytes.fromhex(draw["vertices_bits"][index * 2]))[0],
                 struct.unpack(">f", bytes.fromhex(draw["vertices_bits"][index * 2 + 1]))[0]) for index in (0, 1, 3, 2)]
    for actual, expected in zip(recorded, corners):
        if abs(actual[0] - expected[0]) > 0.0001 or abs(actual[1] - expected[1]) > 0.0001:
            raise ValueError("Native decal quad differs from executed original Decal geometry")
    return {"group": instance["group"], "source_index": instance["source_index"], "name": instance["name"],
            "position": instance["position"], "scale": instance["scale"], "depth": instance["depth"],
            "quad": quad, "crop_sha256": texture["crop_sha256"]}


PINNED_OMISSIONS = sorted(EXPECTED_BANNERS, key=lambda row: (0 if row[0] == "B" else 1, row[1]))


def canonical_int(token):
    try:
        value = int(token)
    except ValueError as error:
        raise ValueError("Noncanonical decal integer") from error
    if str(value) != token:
        raise ValueError("Noncanonical decal integer")
    return value


def parse_csd1(text):
    if not text.endswith("\n"):
        raise ValueError("Decal protocol is not newline terminated")
    lines = text.splitlines()
    if len(lines) < 7 or lines[0] != "CSD1" or lines[1] != INPUT_SHA or lines[2] != MAP_SHA:
        raise ValueError("Decal protocol header changed")
    if canonical_int(lines[3]) != 1:
        raise ValueError("Expected one decal page")
    dimensions = lines[4].split()
    if len(dimensions) != 3:
        raise ValueError("Malformed decal page dimensions")
    page_width, page_height = canonical_int(dimensions[0]), canonical_int(dimensions[1])
    if ((page_width, page_height) != (64, 128) or len(dimensions[2]) != 8 or
            any(character not in "0123456789abcdef" for character in dimensions[2])):
        raise ValueError("Unexpected decal page")
    page_checksum = int(dimensions[2], 16)
    if page_checksum == 0 or canonical_int(lines[5]) != 15:
        raise ValueError("Unexpected decal page/texture count")
    cursor = 6
    textures = {}
    for _ in range(15):
        if cursor >= len(lines):
            raise ValueError("Truncated decal texture table")
        fields = lines[cursor].split()
        if len(fields) != 9:
            raise ValueError("Malformed decal texture row")
        name = fields[0]
        if (not name or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_/-"
                            for character in name) or name in textures):
            raise ValueError("Invalid or duplicate decal texture identity")
        values = [canonical_int(field) for field in fields[1:]]
        u, v, width, height, offset_x, offset_y, frame_width, frame_height = values
        if (u < 1 or v < 1 or width <= 0 or height <= 0 or u + width >= page_width or v + height >= page_height or
                frame_width <= 0 or frame_height <= 0 or offset_x < -4096 or offset_x > 4096 or
                offset_y < -4096 or offset_y > 4096):
            raise ValueError("Invalid decal crop/page/frame geometry")
        textures[name] = {"name": name, "u": u, "v": v, "width": width, "height": height,
                          "draw_offset": [offset_x, offset_y], "frame": [frame_width, frame_height]}
        cursor += 1
    if cursor >= len(lines) or canonical_int(lines[cursor]) != 22:
        raise ValueError("Expected twenty-two decal instances")
    cursor += 1
    instances = []
    expected_instances = [("B", index) for index in range(20)] + [("F", index) for index in range(2)]
    for layer, source_index in expected_instances:
        if cursor >= len(lines):
            raise ValueError("Truncated decal instances")
        fields = lines[cursor].split()
        if len(fields) != 7 or fields[0] != layer or canonical_int(fields[1]) != source_index:
            raise ValueError("Decal instance order/layer changed")
        x, y, scale_x, scale_y, texture_index = [canonical_int(field) for field in fields[2:]]
        if (scale_x not in (1, -1) or scale_y not in (1, -1) or not -1_000_000 <= x <= 1_000_000 or
                not -1_000_000 <= y <= 1_000_000 or not 0 <= texture_index < 15):
            raise ValueError("Invalid decal instance transform/index")
        texture = list(textures.values())[texture_index]
        instances.append({"group": "bgdecals" if layer == "B" else "fgdecals", "source_index": source_index,
                          "position": [x, y], "scale": [scale_x, scale_y], "name": texture["name"],
                          "depth": 9000 if layer == "B" else -10500, "frame": texture["frame"],
                          "draw_offset": texture["draw_offset"],
                          "origin": [texture["frame"][0] / 2 - texture["draw_offset"][0],
                                     texture["frame"][1] / 2 - texture["draw_offset"][1]]})
        cursor += 1
    if cursor >= len(lines) or canonical_int(lines[cursor]) != 7:
        raise ValueError("Expected seven explicit Banner omissions")
    cursor += 1
    omitted = []
    for _ in range(7):
        if cursor >= len(lines):
            raise ValueError("Truncated Banner omissions")
        fields = lines[cursor].split()
        if len(fields) != 3 or fields[0] not in ("B", "F"):
            raise ValueError("Malformed Banner omission")
        omitted.append((fields[0], canonical_int(fields[1]), fields[2]))
        cursor += 1
    if tuple(omitted) != tuple(PINNED_OMISSIONS):
        raise ValueError("Banner omission set changed")
    if cursor != len(lines):
        raise ValueError("Trailing decal protocol data")
    return {"page": [page_width, page_height], "page_checksum": page_checksum,
            "textures": textures, "instances": instances, "omitted": omitted}


def compare(oracle, prepared_dir):
    prepared_dir = Path(prepared_dir).resolve()
    provenance = json.loads((prepared_dir / "provenance.json").read_text())
    if provenance["files"]["decal0.rgba"] != hashlib.sha256((prepared_dir / "decal0.rgba").read_bytes()).hexdigest() or \
            provenance["files"]["decals.txt"] != hashlib.sha256((prepared_dir / "decals.txt").read_bytes()).hexdigest():
        raise ValueError("Prepared decal file identity changed")
    page = (prepared_dir / "decal0.rgba").read_bytes()
    if len(page) != provenance["page"]["bytes"] or hashlib.sha256(page).hexdigest() != provenance["page"]["sha256"]:
        raise ValueError("Prepared decal page identity changed")
    protocol_text = (prepared_dir / "decals.txt").read_text()
    parsed = parse_csd1(protocol_text)
    if checksum(page) != parsed["page_checksum"]:
        raise ValueError("Serialized decal page checksum differs from its RGBA bytes")
    source = oracle["oracle"]
    draws = source["static_profile"]["draws"]
    if len(draws) != 22 or len(parsed["instances"]) != 22 or len(parsed["textures"]) != 15 or len(parsed["omitted"]) != 7:
        raise ValueError("Serialized static/banner classification or counts changed")
    instances = {(instance["group"], instance["source_index"]): instance for instance in parsed["instances"]}
    if len(instances) != 22:
        raise ValueError("Serialized decal instances are not a 22-row source set")
    if any(key[0] == "bgdecals" and key[1] >= 20 or key[0] == "fgdecals" and key[1] >= 2 for key in instances):
        raise ValueError("Serialized instance escaped the static index ranges")
    expected_omitted = {tuple(row) for row in parsed["omitted"]}
    oracle_omitted = {("B" if row["group"] == "bgdecals" else "F", row["source_index"], row["name"].removeprefix("decals/"))
                      for row in source["banner_exclusion"]["attempts"]}
    if expected_omitted != oracle_omitted or len(expected_omitted) != 7:
        raise ValueError("Explicit Banner omission set changed")
    expected_crop = provenance["textures"]
    textures = {}
    for name, texture in parsed["textures"].items():
        if name not in expected_crop:
            raise ValueError("Serialized draw references an unowned static texture")
        texture = {**texture, "page": parsed["page"]}
        crop_sha256 = hashlib.sha256(packed_crop(page, texture, parsed["page"][0])).hexdigest()
        if crop_sha256 != expected_crop[name]["crop_sha256"]:
            raise ValueError("Serialized crop bytes differ from the pinned source crop")
        textures[name] = {**texture, "crop_sha256": crop_sha256}
    rows = []
    for draw in draws:
        key = (draw["group"], draw["source_index"])
        if key not in instances:
            raise ValueError("Source draw is missing from the serialized static profile")
        instance = instances[key]
        texture = textures.get(instance["name"])
        if texture is None:
            raise ValueError("Serialized draw references an unowned static texture")
        rows.append(verify_instance(draw, instance, texture, page, parsed["page"][0]))
    return {"status": "static-decal-draws-compared", "rows": rows, "static": len(rows),
            "unique_textures": len({row["name"] for row in rows}), "banner_omitted": len(expected_omitted),
            "page_sha256": provenance["page"]["sha256"],
            "protocol_sha256": hashlib.sha256(protocol_text.encode()).hexdigest(),
            "claim": "Actual serialized CSD1 records preserve executed original DecalImage position/scale/depth/frame/origin, exact source crop bytes, render order and explicit Banner omissions; hashes alone are not semantic proof"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = json.loads((args.oracle / "result.json").read_text())
    if result["status"] != "source-static-decals-closed" or result["identity"] != verify_extraction(args.oracle):
        raise ValueError("Decal source oracle is not closed/verified")
    comparison = compare(result, args.prepared)
    args.output.write_text(json.dumps(comparison, indent=2) + "\n")
    print(f"STATIC DECAL DRAWS COMPARED: {comparison['static']} rows, {comparison['unique_textures']} unique, "
          f"{comparison['banner_omitted']} explicit Banner omissions")


if __name__ == "__main__":
    main()
