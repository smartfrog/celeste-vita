#!/usr/bin/env python3
"""Compare packed static decal draws against the executed original Decal source records."""

import argparse
import hashlib
import json
import struct
from pathlib import Path

from check_native_oracle import ROOT, verify_extraction
from stage_native_room import verified_bytes


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


def compare(oracle, prepared_dir):
    prepared_dir = Path(prepared_dir).resolve()
    provenance = json.loads((prepared_dir / "provenance.json").read_text())
    if provenance["files"]["decal0.rgba"] != hashlib.sha256((prepared_dir / "decal0.rgba").read_bytes()).hexdigest() or \
            provenance["files"]["decals.txt"] != hashlib.sha256((prepared_dir / "decals.txt").read_bytes()).hexdigest():
        raise ValueError("Prepared decal file identity changed")
    page = (prepared_dir / "decal0.rgba").read_bytes()
    if len(page) != provenance["page"]["bytes"] or hashlib.sha256(page).hexdigest() != provenance["page"]["sha256"]:
        raise ValueError("Prepared decal page identity changed")
    source = oracle["oracle"]
    draws = source["static_profile"]["draws"]
    if len(draws) != 22 or provenance["classification"]["static"] != 22 or provenance["classification"]["bg"] != 20 or \
            provenance["classification"]["fg"] != 2 or provenance["classification"]["banner_omitted"] != 7:
        raise ValueError("Static/banner classification or counts changed")
    instances = {(instance["group"], instance["source_index"]): instance for instance in provenance["instances"]}
    if len(instances) != 22:
        raise ValueError("Packed decal instances are not a 22-row source set")
    if any(key[0] == "bgdecals" and key[1] >= 20 or key[0] == "fgdecals" and key[1] >= 2 for key in instances):
        raise ValueError("Packed instance escaped the static index ranges")
    expected_omitted = {(row[0], row[1], row[2]) for row in provenance["classification"]["banner_ids"]}
    oracle_omitted = {("B" if row["group"] == "bgdecals" else "F", row["source_index"], row["name"].removeprefix("decals/"))
                      for row in source["banner_exclusion"]["attempts"]}
    if expected_omitted != oracle_omitted or len(expected_omitted) != 7:
        raise ValueError("Explicit Banner omission set changed")
    textures = provenance["textures"]
    rows = []
    for draw in draws:
        key = (draw["group"], draw["source_index"])
        if key not in instances:
            raise ValueError("Source draw is missing from the packed static profile")
        instance = instances[key]
        texture = textures.get(instance["name"])
        if texture is None:
            raise ValueError("Packed draw references an unowned static texture")
        texture = {**texture, "page": [provenance["page"]["width"], provenance["page"]["height"]]}
        rows.append(verify_instance(draw, instance, texture, page, provenance["page"]["width"]))
    return {"status": "static-decal-draws-compared", "rows": rows, "static": len(rows),
            "unique_textures": len({row["name"] for row in rows}), "banner_omitted": len(expected_omitted),
            "page_sha256": provenance["page"]["sha256"],
            "claim": "Packed native draw inputs preserve executed original DecalImage position/scale/depth/frame/origin and exact source crop bytes; Banner sin slices are explicit omissions"}


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
