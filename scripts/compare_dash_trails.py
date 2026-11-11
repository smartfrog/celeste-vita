"""Compare the bounded native trail contract with the isolated original-source recording profile."""

import argparse
import copy
import json
import os
from pathlib import Path
import subprocess

from compare_lifecycle_traces import equal
from native_room_revision import canonical_digest, file_identity, validate_source_state, verify_file_identities

SCENARIOS = ("first", "repeat", "cancel", "reload", "capacity", "fractional")
REPEAT_HAIR_GEOMETRY_SLOTS = {134: 0, 139: 1, 145: 2}
REPEAT_HAIR_GEOMETRY_SHA256 = "9a5173ced88ab08fef14749402539f75f97281c7df3c46a2ab72349324f68ffc"


def compare(source, native, bank, scenario=None):
    if scenario is not None and scenario not in SCENARIOS:
        raise ValueError("Unknown trail comparison scenario")
    frames = {frame["name"]: frame for frame in bank["frames"]}
    states = {row["tick"]: row for row in source if row.get("event") == "trails"}
    equal("ticks", list(states), list(range(360)))
    equal("native ticks", [row["tick"] for row in native], list(states))
    captures = ghosts = 0
    geometry_differences = []
    inherited_hair_geometry = []
    for row in native:
        tick = row["tick"]
        state = states[tick]
        label = f"tick {tick}"
        slots = sorted([{**slot, "committed": True} for slot in state["committed"]] +
                       [{**slot, "committed": False} for slot in state["pending"]], key=lambda s: s["Index"])
        for slot in slots:
            slot.pop("Depth", None)
        equal(label + ".slots", row["slots"], slots)
        equal(label + ".SceneSkip", row["sceneRan"], not state["frozen"])
        events = [entry["row"] for entry in source if entry.get("event") == "recording" and entry["tick"] == tick]
        clearing, capturing = False, False
        cleared, draws, targets, masks = [], [], [], []
        for event in events:
            if event["operation"] == "begin":
                clearing = event["function"] == "Min"
                capturing = event["source"] == "One" and event["destination"] == "InverseSourceAlpha"
            elif event["operation"] == "rect":
                if clearing:
                    equal(label + ".tile size", [event["width"], event["height"]], [64, 64])
                    cleared.append(int(event["x"] / 64 + event["y"] / 64 * 8))
                else:
                    masks.append(event)
            elif event["operation"] == "draw":
                if event["target"]:
                    targets.append({"slot": event["clip"][0] // 64 + event["clip"][1] // 64 * 8, "color": event["color"]})
                elif capturing:
                    draws.append(event)
        equal(label + ".captured slots", [capture["slot"] for capture in row["captures"]], cleared)
        if cleared:
            equal(label + ".mask count", len(masks), 1)
            equal(label + ".whole-target alpha mask", [masks[0][key] for key in ("x", "y", "width", "height", "color")],
                  [0, 0, 512, 512, [255, 255, 255, 255]])
        offset = 0
        for capture in row["captures"]:
            captures += 1
            commands = draws[offset:offset + len(capture["draws"])]
            equal(label + ".capture draw count", len(commands), len(capture["draws"]))
            for index, (actual, expected) in enumerate(zip(capture["draws"], commands, strict=True)):
                for key in ("texture", "scale", "rotation", "color"):
                    equal(label + ".capture." + key, actual[key], expected[key])
                for key in ("position", "vertices"):
                    try:
                        equal(label + ".capture." + key, actual[key], expected[key])
                    except ValueError as error:
                        if (scenario != "repeat" or REPEAT_HAIR_GEOMETRY_SLOTS.get(tick) != capture["slot"]
                                or not 4 <= index <= 18 or actual["texture"] != "characters/player/hair00"):
                            raise
                        geometry_differences.append(str(error))
                        inherited_hair_geometry.append({"tick": tick, "slot": capture["slot"], "draw": index,
                            "texture": actual["texture"], "field": key, "native": actual[key], "source": expected[key]})
                trim = frames[actual["texture"]]["trim"]
                equal(label + ".capture.origin", [v-t for v, t in zip(actual["origin"], trim, strict=True)], expected["origin"])
            offset += len(commands)
        equal(label + ".capture total", offset, len(draws))
        equal(label + ".ghosts", row["ghosts"], targets)
        ghosts += len(targets)
    completed = [row for row in source if row.get("event") == "completed"]
    equal("source completion", len(completed), 1)
    equal("source native imports", completed[0]["nativeAttempts"], 0)
    if scenario == "repeat":
        equal("inherited repeat hair difference count", len(inherited_hair_geometry), 90)
        equal("inherited repeat hair raw value pairs", canonical_digest(inherited_hair_geometry), REPEAT_HAIR_GEOMETRY_SHA256)
    return {"frames": len(native), "captures": captures, "ghost_draws": ghosts, "GPU_pixel_parity": False,
            "capture_geometry_differences": geometry_differences,
            "inherited_hair_geometry": inherited_hair_geometry,
            "scope": "Exact trail/capture fields except the 90 immutable pre-correction hair position/vertex value pairs at repeat ticks 134/139/145. Body and all nongeometry fields always match; original source numerical outputs are unchanged."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("native", "oracle", "sdk", "mask", "hazards", "player-dir", "tile-content", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--expected-source-state", type=Path)
    args = parser.parse_args()
    before = validate_source_state(json.loads(args.expected_source_state.read_text()) if args.expected_source_state else None)
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(Path(__file__).resolve().parents[1] / ".audit"):
        parser.error("Comparison output must be fresh and private")
    output.mkdir(parents=True)
    profile = json.loads((args.oracle / "dash-profile.json").read_text())
    inputs = dict(profile["inputs"])
    for path in (args.native, args.oracle / "Oracle.dll", args.oracle / "Oracle.runtimeconfig.json", args.oracle / "dash-profile.json",
                 args.sdk, args.mask, args.hazards, args.player_dir / "player.txt", args.player_dir / "bank.json"):
        inputs[str(path.resolve())] = file_identity(path)
    verify_file_identities(inputs)
    results = {"source_before": before, "inputs": inputs, "scenarios": {}}
    try:
        bank = json.loads((args.player_dir / "bank.json").read_text())
        for scenario in SCENARIOS:
            source_path = output / (scenario + ".source.jsonl")
            environment = dict(os.environ, HOME=str(output.parent / "home"), TMPDIR=str(output.parent / "tmp"), DOTNET_EnableDiagnostics="0")
            with (output / (scenario + ".log")).open("x") as log:
                subprocess.run(list(map(str, [args.sdk, args.oracle / "Oracle.dll", source_path, args.tile_content, scenario])),
                               env=environment, stdout=log, stderr=subprocess.STDOUT, check=True)
            native_path = output / (scenario + ".native.jsonl")
            with native_path.open("x") as stream:
                subprocess.run(list(map(str, [args.native, args.mask, args.hazards, args.player_dir / "player.txt", scenario])), stdout=stream, check=True)
            source = [json.loads(line) for line in source_path.read_text().splitlines()]
            native = [json.loads(line) for line in native_path.read_text().splitlines()]
            results["scenarios"][scenario] = compare(source, native, bank, scenario)
            mutants = 0

            def reject_mutation(changed, field):
                try:
                    compare(source, changed, bank, scenario)
                except ValueError:
                    return 1
                raise ValueError("Native mutation passed: " + field)

            for field, value in (("slots", []), ("captures", []), ("ghosts", []), ("sceneRan", False)):
                changed = copy.deepcopy(native)
                index = next(i for i, row in enumerate(changed) if row[field] != value)
                changed[index][field] = value
                mutants += reject_mutation(changed, field)
            for field in ("percent", "fade-byte", "creation-order", "capture-vertex"):
                changed = copy.deepcopy(native)
                row = next(row for row in changed if row["captures"] and row["slots"] and row["ghosts"])
                if field == "percent":
                    row["slots"][0]["Percent"] += 0.001
                elif field == "fade-byte":
                    row["ghosts"][0]["color"][0] ^= 1
                elif field == "creation-order":
                    row["ghosts"][0]["slot"] = 63
                else:
                    row["captures"][0]["draws"][0]["vertices"][0][0] += 1
                mutants += reject_mutation(changed, field)
            if scenario == "repeat":
                for tick in (45, 134):
                    for field in ("body-alpha", "body-vertex"):
                        changed = copy.deepcopy(native)
                        body = changed[tick]["captures"][0]["draws"][-1]
                        if field == "body-alpha":
                            body["color"][3] = 0
                        else:
                            body["vertices"][0][0] += 16
                        mutants += reject_mutation(changed, f"{field} at {tick}")
                for tick in REPEAT_HAIR_GEOMETRY_SLOTS:
                    for field in ("position", "vertices"):
                        changed = copy.deepcopy(native)
                        hair = changed[tick]["captures"][0]["draws"][4]
                        if field == "position":
                            hair[field][0] += 1
                        else:
                            hair[field][0][0] += 16
                        mutants += reject_mutation(changed, f"inherited hair {field} at {tick}")
            results["scenarios"][scenario]["rejected_mutations"] = mutants
        results["status"] = "passed"
    except Exception as error:
        results.update(status="failed", error=str(error))
        raise
    finally:
        verify_file_identities(inputs)
        results["source_after"] = validate_source_state(before)
        (output / "checks.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results["scenarios"], indent=2))


if __name__ == "__main__":
    main()
