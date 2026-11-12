"""Prepare a private persistent terrain catalog from the accepted, pinned original bake. No images or SOURCE execution."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from stage_native_room import checksum

AUDIT = Path("/home/fred/projects/celeste-vita/.audit/native-terrain-draw-projection-01")
PROFILE = "c6ee452419e5d276b38e2257a53a0f052a9a46f5eb0a63da7d2ff0761007a2b6"
PINS = {
    "commands": "a8e10f7dac194b746584168a9d28009f9b8e0a36bb8cccbdcb19c6d61c5f9fde",
    "atlas": "b75f913d315bd641c35a4990d9041b238c0d9ef3f8b1247ec557de8a9defc1cc",
    "result": "f90448644caace1727eb46a5fce912ff1290678bd73efe6e1435ffd87951f1e0",
    "rng": "b28916f1bf700eac6d2b1abc272eb4d68cc8e670438d8ad0a8deedb7cdef9348",
    "driver": "2f7555abf2d9dd6d4e56429009d674551b2857304fd794d00e18958eef2563c6",
    "sheets": "c8ccf3ecb4b7cbe32da5a18de46e7db08d0be90a0acb4c0db1f9e72246258f52",
}
COVERAGE = {
    "acceptance": "restricted: all 514 accepted route frames; whole catalog provenance-bound",
    "observed_unique_cells": 2980,
    "unobserved_cells": 45835,
    "off_route_condition": "Per-cell behavioral assurance off route requires a separately authorized frozen-profile-02 full-grid static bake comparison; not claimed here.",
    "not_claimed": "full Level rendergraph/hooks, global command interleaving, vertices, scissor, GPU, pixels, Vita or capacity",
}


def require(value, message):
    if not value:
        raise ValueError(message)


def integer(value, low, high):
    require(type(value) is int and low <= value <= high, "Invalid terrain integer/range")
    return value


def identity(value):
    require(isinstance(value, str) and len(value) <= 192 and re.fullmatch(r"[A-Za-z0-9_/-]+", value)
            and not value.startswith("/"), "Invalid terrain source/sheet identity")
    return value


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def verify_inputs(inputs):
    require(set(inputs) == set(PINS), "Missing terrain pin inputs")
    for name, expected in PINS.items():
        require(hashlib.sha256(inputs[name]).hexdigest() == expected, "Terrain input pin changed: " + name)
    decoded = {name: json.loads(data, object_pairs_hook=unique_object,
                               parse_constant=lambda value: require(False, "Nonfinite JSON number: " + value))
               for name, data in inputs.items()}
    result = decoded["result"]
    require(result["status"] == "source-closed-compile-and-bake" and result["bake"] == {
        "seed": 553, "bgCalls": 21901, "totalCalls": 48816, "bgCommands": 21900, "fgCommands": 26915},
        "Unaccepted terrain bake result")
    for name in ("commands", "atlas", "rng"):
        require(result["artifacts"][name + ".json"] == PINS[name], "Result artifact binding changed")
    require(len(decoded["commands"]) == 48815 and len(decoded["rng"]) == 48816,
            "Terrain bake counts changed")
    require(decoded["rng"][0]["arguments"] == [553], "Terrain seed binding changed")
    return decoded


def encode_catalog(cells, atlas, sheets, pins, *, origin=(-64, -3272), dimensions=(541, 440)):
    require(len(pins) == 4 and all(re.fullmatch("[a-f0-9]{64}", pin) for pin in pins), "Invalid terrain pins")
    x0, y0 = [integer(value, -1_000_000, 1_000_000) for value in origin]
    columns, rows = [integer(value, 1, 4096) for value in dimensions]
    require(columns * rows <= 4_000_000 and cells, "Invalid terrain dimensions/empty catalog")
    layers = {"BG": {}, "FG": {}}
    descriptors = set()
    for cell in cells:
        require(set(cell) == {"layer", "x", "y", "character", "rule", "rng", "variant", "source", "rectangle"},
                "Invalid terrain cell schema")
        layer = cell["layer"]
        require(layer in layers, "Invalid terrain layer")
        x, y = integer(cell["x"], 0, columns - 1), integer(cell["y"], 0, rows - 1)
        require((x, y) not in layers[layer], "Duplicate terrain layer cell")
        integer(cell["rng"], 0, 48816)
        integer(cell["variant"], 0, 65535)
        require(isinstance(cell["character"], str) and len(cell["character"]) == 1 and cell["character"] != "0"
                and isinstance(cell["rule"], str), "Invalid terrain non-null cell identity")
        source = identity(cell["source"])
        require(source in atlas, "Missing terrain atlas source")
        entry = atlas[source]
        require(isinstance(entry, list) and len(entry) == 9, "Invalid terrain atlas descriptor")
        sheet, u0, v0, width, height, dx, dy, fw, fh = entry
        identity(sheet)
        require(sheet in sheets, "Missing terrain sheet")
        sw, sh = [integer(value, 8, 16384) for value in sheets[sheet]]
        for value in (u0, v0, width, height, dx, dy, fw, fh):
            integer(value, 0, 16384)
        require(width > 0 and height > 0 and u0 + width <= sw and v0 + height <= sh
                and dx == dy == 0 and [fw, fh] == [width, height], "Unsupported terrain atlas geometry")
        rect = cell["rectangle"]
        require(isinstance(rect, list) and len(rect) == 4, "Invalid terrain clip rectangle")
        u, v, w, h = [integer(value, 0, 16384) for value in rect]
        require(w == h == 8 and u0 <= u <= u0 + width - 8 and v0 <= v <= v0 + height - 8
                and (u - u0) % 8 == (v - v0) % 8 == 0, "Invalid terrain source clip bounds/alignment")
        descriptor = (source, sheet, u, v)
        descriptors.add(descriptor)
        layers[layer][x, y] = descriptor
    materials = sorted(descriptors)
    require(len(materials) <= 65536, "Too many terrain materials")
    material_index = {value: index for index, value in enumerate(materials)}
    used_sheets = sorted({value[1] for value in materials})
    require(1 <= len(used_sheets) <= 16, "Invalid terrain sheet count")
    sheet_index = {name: index for index, name in enumerate(used_sheets)}
    lines = ["CSTV1", *pins, f"{x0} {y0} {columns} {rows} 8 1", str(len(used_sheets))]
    lines += [f"{name} {sheets[name][0]} {sheets[name][1]}" for name in used_sheets]
    lines.append(str(len(materials)))
    lines += [f"{source} {sheet_index[sheet]} {u} {v} 8 8 0 0 8 8 255 255 255 255 1"
              for source, sheet, u, v in materials]
    lines.append("2")
    for layer, tag, depth in (("BG", "B", 10000), ("FG", "F", -10000)):
        lines.append(f"{tag} {depth} {len(layers[layer])}")
        lines += [f"{x} {y} {material_index[descriptor]}" for (x, y), descriptor in sorted(layers[layer].items())]
    encoded = ("\n".join(lines) + "\n").encode("ascii")
    require(len(encoded) <= 32_000_000, "Terrain catalog exceeds byte bound")
    return encoded


def prepare(paths, output):
    require(output.resolve().is_relative_to(AUDIT) and not output.exists(),
            "Terrain output must be fresh in its canonical private namespace")
    decoded = verify_inputs({name: path.read_bytes() for name, path in paths.items()})
    require([sum(cell["layer"] == layer for cell in decoded["commands"]) for layer in ("BG", "FG")]
            == [21900, 26915], "Terrain layer counts changed")
    data = encode_catalog(decoded["commands"], decoded["atlas"], decoded["sheets"],
                          [PINS["commands"], PINS["atlas"], PINS["result"], PROFILE])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(data)
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "fnv1a": f"{checksum(data):08x}",
            "pins": PINS, "profile_binding": PROFILE, "cells": 48815, "coverage": COVERAGE}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (*PINS, "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare({name: getattr(args, name) for name in PINS}, args.output), sort_keys=True))
