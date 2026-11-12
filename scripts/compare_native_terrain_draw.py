"""Compare all accepted terrain logical commands against actual native session camera windows, read-only."""
import argparse
from collections import Counter
from itertools import zip_longest
import json
import math
from pathlib import Path
import struct

from compare_native_player_draw import FIELDS, SOURCE_IDENTITY, same_value
from native_room_revision import file_identity
from prepare_terrain_catalog import AUDIT, COVERAGE, require

LAYERS = {"BackgroundTiles": "B", "SolidTiles": "F"}
DEPTHS = {"B": 10000, "F": -10000}


def source_frames(path):
    frame = None
    for line in path.open():
        if not line.startswith('{"event":"draw-'):
            continue
        row = json.loads(line)
        event = row["event"]
        if event == "draw-state" and row["phase"] == "before-draw":
            require(frame is None, "Unfinished SOURCE terrain frame")
            frame = {"tick": row["tick"], "camera": row["state"]["camera"], "commands": {"B": [], "F": []}}
        elif event == "draw-roster":
            require(frame is not None and row["tick"] == frame["tick"] and row["cameraAlias"] is True
                    and row["cameraViewport"] == [320, 180], "SOURCE gameplay camera alias/viewport changed")
            frame["owners"] = {LAYERS[owner["type"]]: owner for owner in row["live"] if owner["type"] in LAYERS}
        elif event == "draw-command" and row["owner"]["type"] in LAYERS:
            require(frame is not None and row["tick"] == frame["tick"], "Unbound SOURCE terrain command")
            owner = row["owner"]
            layer = LAYERS[owner["type"]]
            require(owner["componentType"] == "TileGrid" and owner["depth"] == DEPTHS[layer]
                    and row["effects"] == "None" and row["finiteGeometry"] is True, "Unsupported SOURCE terrain fields")
            bits = row["verticesFloat32Bits"]
            require(len(bits) == 4 and all(len(vertex) == 5 and all(type(value) is int and -(2**31) <= value < 2**31
                    and math.isfinite(struct.unpack("<f", struct.pack("<i", value))[0]) for value in vertex) for vertex in bits),
                    "Nonfinite SOURCE terrain pre-batch vertex bits")
            frame["commands"][layer].append(row)
        elif event == "draw-dispatch":
            require(frame is not None and row["tick"] == frame["tick"], "Unbound SOURCE terrain dispatch")
            frame["spans"] = {LAYERS[span["type"]]: span for span in row["entities"] if span["type"] in LAYERS}
        elif event == "draw-state" and row["phase"] == "after-draw":
            require(frame is not None and row["tick"] == frame["tick"] and set(frame.get("owners", {})) == {"B", "F"}
                    and set(frame.get("spans", {})) == {"B", "F"}, "Incomplete SOURCE terrain frame")
            for layer in ("B", "F"):
                commands, owner, span = frame["commands"][layer], frame["owners"][layer], frame["spans"][layer]
                require(owner["position"] == [-64, -3272] and owner["depth"] == DEPTHS[layer]
                        and owner["Visible"] is True and owner["hudExcluded"] is False, "SOURCE global terrain owner changed")
                require([command["index"] for command in commands] == list(range(span["drawStart"], span["drawEnd"]))
                        and all(command["owner"]["entity"] == owner["entity"] == span["entity"] for command in commands),
                        "SOURCE terrain owner span incomplete")
            yield frame
            frame = None
    require(frame is None, "Truncated SOURCE terrain trace")


def native_frames(path):
    catalog = frame = None
    camera = roster = dispatch = None
    ended = False
    for line in path.open():
        if not line.startswith(('{"event":"terrain-', '{"event":"phase"', '{"event":"draw-owner-', '{"event":"native-ended"')):
            continue
        row = json.loads(line)
        event = row["event"]
        if event == "terrain-catalog":
            require(catalog is None, "Duplicate native terrain catalog")
            catalog = row
        elif event == "phase" and row["phase"] == "after-frame":
            camera = (row["tick"], row["state"]["camera"])
        elif event == "draw-owner-roster":
            roster = row
        elif event == "draw-owner-dispatch":
            dispatch = row
        elif event == "terrain-draw":
            require(catalog is not None and camera is not None and row["tick"] == camera[0], "Missing actual native camera/catalog")
            require(roster is not None and dispatch is not None and row["tick"] == roster["tick"] == dispatch["tick"],
                    "Missing native terrain owner roster/dispatch")
            layer = row["layer"]
            require(layer in DEPTHS and row["depth"] == DEPTHS[layer] and same_value(row["camera"], camera[1])
                    and row["viewport"] == [320, 180], "Native terrain camera/depth/viewport changed")
            owners = [owner for owner in roster["live"] if owner["kind"] == ("BackgroundTiles" if layer == "B" else "SolidTiles")]
            require(len(owners) == 1 and owners[0]["identity"] == row["owner"] and owners[0]["room"] == ""
                    and owners[0]["visible"] is True and owners[0]["hudExcluded"] is False
                    and dispatch["order"].count(row["owner"]) == 1, "Native terrain not bound to global dispatched owner")
            if layer == "B":
                require(frame is None, "Duplicate/incomplete native terrain frame")
                frame = {"tick": row["tick"], "catalog": catalog, "layers": {"B": row}}
            else:
                require(frame is not None and row["tick"] == frame["tick"] and "F" not in frame["layers"],
                        "Reordered/duplicate native terrain layer")
                frame["layers"]["F"] = row
                yield frame
                frame = None
        elif event == "native-ended":
            require(not ended and row["frames"] == 514 and row["reloads"] == 0 and row["loads"] == 2, "Native route incomplete")
            ended = True
    require(catalog is not None and frame is None and ended, "Missing native terrain evidence/end marker")


def compare_layer(source, native, materials, sheets):
    differences = []
    for index, (expected, command) in enumerate(zip_longest(source, native["commands"])):
        if expected is None or command is None:
            differences.append({"index": index, "field": "command-presence"})
            continue
        require(isinstance(command, list) and len(command) == 3 and type(command[0]) is int
                and 0 <= command[0] < len(materials), "Invalid native terrain material command")
        require(all(type(value) in (int, float) and math.isfinite(value) for value in command[1:]), "Nonfinite native terrain position")
        material = materials[command[0]]
        require(type(material["sheet"]) is int and 0 <= material["sheet"] < len(sheets), "Invalid native terrain sheet index")
        sheet = sheets[material["sheet"]]
        actual = {key: material[key] for key in ("sourceRectangle", "color", "origin", "scale", "rotation")}
        actual.update(sheet=sheet["name"], dimensions=sheet["dimensions"], position=command[1:])
        for key in FIELDS:
            if not same_value(actual[key], expected[key]):
                differences.append({"index": index, "field": key, "actual": actual[key], "expected": expected[key]})
    return differences


def compare(source_path, native_path):
    require(file_identity(source_path) == SOURCE_IDENTITY, "Immutable SOURCE terrain oracle changed")
    counts = Counter()
    failures, samples, source_owners, native_owners = [], {}, {}, {}
    observed_cells = set()
    for tick, (source, native) in enumerate(zip_longest(source_frames(source_path), native_frames(native_path))):
        require(source is not None and native is not None and source["tick"] == native["tick"] == tick,
                "Missing/reordered SOURCE/native terrain frame")
        for layer in ("B", "F"):
            actual = native["layers"][layer]
            expected_owner = source["owners"][layer]["entity"]
            require(source_owners.setdefault(layer, expected_owner) == expected_owner
                    and native_owners.setdefault(layer, actual["owner"]) == actual["owner"], "Persistent terrain owner recreated")
            require(source_owners["B"] != source_owners.get("F") and native_owners["B"] != native_owners.get("F"),
                    "Terrain owners aliased")
            commands = source["commands"][layer]
            positions = [tuple(command["position"]) for command in commands]
            require(all(positions[index - 1] < positions[index] for index in range(1, len(positions)))
                    and all(all(value % 8 == 0 for value in position) for position in positions),
                    "SOURCE terrain duplicate/non-grid/order changed")
            observed_cells.update((layer, *position) for position in positions)
            differences = compare_layer(commands, actual, native["catalog"]["materials"], native["catalog"]["sheets"])
            if not same_value(actual["camera"], source["camera"]):
                differences.append({"field": "actual-session-camera", "actual": actual["camera"], "expected": source["camera"]})
            if actual["renderCamera"] != [math.floor(value) for value in source["camera"]]:
                differences.append({"field": "renderer-camera-floor", "actual": actual["renderCamera"], "expected": source["camera"]})
            require(actual["outsideCatalog"] is False, "Accepted route unexpectedly leaves validated catalog bounds")
            counts[layer] += len(commands)
            counts["native_" + layer] += len(actual["commands"])
            if differences:
                failures.append({"tick": tick, "layer": layer, "mismatches": len(differences), "first": differences[:8]})
            if tick in (0, 375, 413, 513):
                samples.setdefault(tick, {})[layer] = {"source": len(commands), "native": len(actual["commands"])}
        counts["frames"] += 1
    require(counts["frames"] == 514 and counts["B"] == 358685 and counts["F"] == 247307
            and len(observed_cells) == 2980, "Accepted full-route terrain coverage changed")
    return {"frames": counts["frames"], "source_commands": counts["B"] + counts["F"],
            "native_commands": counts["native_B"] + counts["native_F"], "layers": dict(counts),
            "observed_unique_cells": len(observed_cells), "failures": failures, "samples": samples,
            "source": SOURCE_IDENTITY, "native": file_identity(native_path), "coverage": COVERAGE,
            "camera_semantics": "actual native session camera; gameplay renderer alias, 320x180, floor position before viewport edges; not Level.BeforeRender hooks",
            "float_bits_semantics": "SOURCE verticesFloat32Bits encode pre-batch XY/Z/UV as signed IEEE754 float32 words; checked finite, NOT compared as logical world-position bits or GPU output. Logical numeric fields compared at exact float32 precision.",
            "scope": "Ordered BG/FG logical commands, sheet/rect/position/color/origin/scale/rotation/dimensions and persistent owner binding; no full-owner interleaving equivalence"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "native", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    require(args.output.resolve().is_relative_to(AUDIT) and not args.output.exists(), "Terrain comparison output must be fresh/private")
    result = compare(args.source, args.native)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({key: result[key] for key in ("frames", "source_commands", "native_commands", "samples")}, sort_keys=True))
    if result["failures"]:
        raise SystemExit("Terrain comparison gaps: " + str(len(result["failures"])))


if __name__ == "__main__":
    main()
