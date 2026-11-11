"""Exact bounded native lifecycle comparison against the accepted immutable source captures."""

import argparse
from collections import Counter
import json
from pathlib import Path
import struct
import subprocess

from check_native_oracle import ROOT, verify_extraction
from native_room_revision import validate_source_state, file_identity as pin

SOURCE_TRACES = {
    "repeat": "b2123d17ef324e44535f20f75963ea9a177ea38217c8255162a2c97c45c04260",
    "checkpoint-repeat": "fd043cbe6b6ad3398d1494466e41f6a1396b14d2069594874a573a88bc3aeb47",
}


def equal(label, actual, expected):
    if isinstance(actual, dict) and isinstance(expected, dict):
        if actual.keys() != expected.keys():
            raise ValueError(label + ": object fields differ")
        for key in actual:
            equal(label + "." + key, actual[key], expected[key])
        return
    if isinstance(actual, bool) or isinstance(expected, bool):
        matched = type(actual) is type(expected) and actual == expected
    elif isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        matched = (struct.pack("<f", actual) == struct.pack("<f", expected)) if isinstance(actual, float) or isinstance(expected, float) else actual == expected
    elif isinstance(actual, list) and isinstance(expected, list):
        if len(actual) != len(expected):
            raise ValueError(f"{label}: length {len(actual)} != {len(expected)}")
        for index, (a, b) in enumerate(zip(actual, expected, strict=True)):
            equal(f"{label}[{index}]", a, b)
        return
    else:
        matched = actual == expected
    if not matched:
        raise ValueError(f"{label}: {actual!r} != {expected!r}")


def compare_render(source, native, frames, layout):
    label = f"tick {source['tick']}"
    for key in ("phase", "position", "animation", "spriteScale", "spriteRotation", "hairColor", "hairNodes", "introEase", "deadOffset", "effectPercent", "hasHair", "hairFacing"):
        equal(label + "." + key, native[key], source[key])
    entity = source["updateStateAfter"]["entities"][0]
    if entity["state"] is not None:
        equal(label + ".state", native["state"], entity["state"])
    for key in ("wave", "animationTimer", "tweenTime"):
        equal(label + "." + key, native[key], entity[key])
    equal(label + ".rngCalls", native["rngCalls"], source["rngAfter"])
    equal(label + ".frameCounter", native["frameCounter"], source["updateStateAfter"]["FrameCounter"])
    equal(label + ".timeActive", native["timeActive"], source["updateStateAfter"]["TimeActive"])
    equal(label + ".rawTimeActive", native["rawTimeActive"], source["updateStateAfter"]["RawTimeActive"])
    equal(label + ".freeze", native["freeze"], source["freezeAfterUpdate"])
    equal(label + ".drawCount", len(native["draws"]), len(source["draws"]))
    for index, (actual, expected) in enumerate(zip(native["draws"], source["draws"], strict=True)):
        draw_label = f"{label}.draws[{index}]"
        for key in ("texture", "position", "scale", "Rotation", "color"):
            equal(draw_label + "." + key, actual[key], expected[key])
        frame = frames[actual["texture"]]
        equal(draw_label + ".clip", expected["clip"], frame["rectangle"])
        equal(draw_label + ".textureSize", expected["textureSize"], [4096, 4096])
        equal(draw_label + ".effects", expected["effects"], 0)
        equal(draw_label + ".origin", [a-b for a,b in zip(actual["origin"], frame["trim"], strict=True)], expected["origin"])
        equal(draw_label + ".vertexCount", len(actual["vertices"]), 4)
        _, u, v = layout[actual["texture"]]
        x, y, width, height = frame["rectangle"]
        for vertex, (source_index, corner) in enumerate(zip((0,1,3,2), ((0,0),(1,0),(1,1),(0,1)), strict=True)):
            a, b = actual["vertices"][vertex], expected["vertices"][source_index]
            equal(draw_label + f".vertex[{vertex}].position", a["position"], b["position"])
            equal(draw_label + f".vertex[{vertex}].color", expected["color"], b["color"])
            equal(draw_label + f".vertex[{vertex}].sourceUV", b["uv"], [(x+corner[0]*width)/4096, (y+corner[1]*height)/4096])
            equal(draw_label + f".vertex[{vertex}].packedUV", a["uv"], [(u+corner[0]*width)/128, (v+corner[1]*height)/64])
    wipe = source["wipe"]
    if wipe is None:
        equal(label + ".wipe", native["wipe"], None)
        equal(label + ".wipeDraws", source["wipeDraws"], [])
    else:
        if native["wipe"] is None:
            raise ValueError(label + ": missing native wipe")
        for key in ("WipeIn", "Percent"):
            equal(label + ".wipe." + key, native["wipe"][key], wipe[key])
        equal(label + ".wipeDrawCount", len(source["wipeDraws"]), 1)
        equal(label + ".wipeVertexCount", source["wipeDraws"][0]["vertexCount"], 36)
        equal(label + ".wipeMatrix", source["wipeDraws"][0]["matrix"], [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1])
        equal(label + ".wipeVertices", native["wipe"]["vertices"], source["wipeVertices"][0])


def random_events(rows, rng):
    result = {}
    for row in rows:
        if row.get("event") != "contract-rng" or row["rng"] != rng:
            continue
        stack = row["stack"]
        if "Celeste.Player.Jump" in stack:
            phase = "jump-dust"
        elif "Celeste.Player.OnCollideV" in stack:
            phase = "landing-dust"
        elif stack[0] == "Celeste.Level.Update" and row["operation"] == "Next":
            phase = "level-shake-after-hair"
            equal("shake RNG after hair", row["hairHeadMatchesPostUpdate"], True)
        elif stack[:2] == ["Monocle.Calc.NextFloat", "Celeste.Level.Update"]:
            phase = "level-glitch"
        else:
            raise ValueError("Undeclared persistent RNG source: " + str(stack))
        equal("RNG during render", row["duringRender"], False)
        equal("RNG during freeze", row["freezeBeforeUpdate"], False)
        result.setdefault(row["tick"], []).append({"phase": phase, "operation": row["operation"], "calls": row["calls"]})
    return result


def compare(source, native, bank, layout):
    renders = [row for row in source if row.get("event") == "contract-render"]
    inputs = [row for row in source if row.get("event") == "natural-frame"]
    equal("source render ticks", [r["tick"] for r in renders], list(range(-1,364)))
    equal("source input ticks", [r["tick"] for r in inputs], list(range(364)))
    equal("native frame ticks", [r["tick"] for r in native], list(range(-1,364)))
    frames = {frame["name"]: frame for frame in bank["frames"]}
    rng = renders[0]["updateStateAfter"]["rng"]
    events = random_events(source, rng)
    scoped_calls = 0
    scoped_by_tick = Counter(row["tick"] for row in source if row.get("event") == "contract-rng" and row["rng"] != rng and "Celeste.Spikes.Added" in row["stack"])
    expected_counts = {"jumps": 0, "reloads": 0, "loads": 1, "respawnCallbacks": 0, "wipeCallbacks": 0,
                       "corpseAdds": 0, "corpseCommits": 0, "corpseRemoves": 0}
    source_events = {}
    for row in source:
        if "tick" in row:
            source_events.setdefault(row["tick"], []).append(row)
    for expected, actual in zip(renders, native, strict=True):
        compare_render(expected, actual, frames, layout)
        equal(f"tick {actual['tick']}.randomEvents", actual["randomEvents"], events.get(actual["tick"], []))
        scoped_calls += scoped_by_tick[actual["tick"]]
        equal(f"tick {actual['tick']}.scopedRoomRandomCalls", actual["scopedRoomRandomCalls"], scoped_calls)
        for row in source_events.get(actual["tick"], []):
            name = row.get("event")
            if name == "contract-callback":
                key = "respawnCallbacks" if row["callback"] == "respawn-tween" else "wipeCallbacks"
                expected_counts[key] += 1
            for event, key in (("natural-jump", "jumps"), ("natural-reload", "reloads"),
                               ("natural-reload", "loads"), ("contract-deferred-corpse", "corpseAdds"),
                               ("contract-corpse-commit", "corpseCommits"), ("natural-reload", "corpseRemoves")):
                if name == event:
                    expected_counts[key] += 1
        for key, count in expected_counts.items():
            equal(f"tick {actual['tick']}.{key}", actual[key], count)
        expected_callbacks = []
        for row in source_events.get(actual["tick"], []):
            if row.get("event") == "contract-callback":
                keys = ("callback", "invocations", "stateBefore", "stateAfter", "scaleAfter", "maxFall", "timeLeft", "percent") if row["callback"] == "respawn-tween" else ("callback", "invocations", "Completed", "ending")
                expected_callbacks.append({key: row[key] for key in keys})
        equal(f"tick {actual['tick']}.callback endpoints", actual["callbacks"], expected_callbacks)
    by_tick = {row["tick"]: row for row in native}
    for expected in inputs:
        actual = by_tick[expected["tick"]]
        for key in ("moveX", "jumpCheck", "jumpPressedBeforeScene", "jumpReleased", "bufferBeforeScene", "bufferAfterScene", "sceneRan", "pendingCorpses", "committedCorpses"):
            equal(f"tick {actual['tick']}.{key}", actual[key], expected[key])
        if expected["wipe"] is not None:
            equal("wipe completion flag", actual["wipe"]["Completed"], expected["wipe"]["Completed"])
    for event in source:
        name = event.get("event")
        if name not in ("natural-jump", "natural-death", "natural-reload", "contract-callback"):
            continue
        actual = by_tick[event["tick"]]
        if name == "natural-jump":
            for key in ("position", "speed"):
                equal(f"jump {event['tick']}.{key}", actual[key], event[key])
            equal("total jumps", actual["jumps"], event["totalJumps"])
        elif name in ("natural-death", "natural-reload"):
            for key in ("sessionDeaths", "roomDeaths", "saveDeaths"):
                equal(f"{name} {event['tick']}.{key}", actual[key], event[key])
            equal("corpse creates", actual["corpseAdds"], event["cycle"]+1)
            if name == "natural-reload":
                equal("reloads", actual["reloads"], event["cycle"]+1)
                equal("loads", actual["loads"], event["cycle"]+2)
                equal("session reload time", actual["sessionTime"], event["sessionTimeAfter"])
                equal("corpse removes", actual["corpseRemoves"], event["cycle"]+1)
                equal("reload state", actual["state"], 14)
                equal("reconstructed raw hazards", actual["rawHazards"], event["rawHazards"])
                death = next(row for row in source if row.get("event") == "natural-death" and row["cycle"] == event["cycle"])
                equal("session time at death", by_tick[death["tick"]]["sessionTime"], event["sessionTimeAtDeath"])
        else:
            equal("source callback invocation count", event["invocations"], 1)
            key = "respawnCallbacks" if event["callback"] == "respawn-tween" else "wipeCallbacks"
            equal("callback exactly once at tick", actual[key]-by_tick[event["tick"]-1][key], 1)
    return {"frames": len(native), "phases": dict(Counter(row["phase"] for row in native)),
            "sprite_draws": sum(len(row["draws"]) for row in native),
            "wipe_draws": sum(row["wipe"] is not None for row in native),
            "jumps": native[-1]["jumps"], "automatic_reloads": native[-1]["reloads"],
            "comparison": "float32 bit equality; source/packed UV checked independently against the pinned atlas and generated layout"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--mask", type=Path, required=True)
    parser.add_argument("--hazards", type=Path, required=True)
    parser.add_argument("--player-dir", type=Path, required=True)
    parser.add_argument("--expected-source-state", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    expected = json.loads(args.expected_source_state.read_text()) if args.expected_source_state else None
    before = validate_source_state(expected)
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / ".audit") or output.exists():
        parser.error("Output must be fresh and private beneath .audit")
    output.mkdir(parents=True)
    source_identity = verify_extraction(args.source)
    paths = [args.native, args.mask, args.hazards, args.player_dir / "provenance.json", args.player_dir / "bank.json",
             args.player_dir / "player.txt", args.source / "source-manifest.json", args.source / "Extracted.cs", args.source / "Frontier.cs"]
    provenance = json.loads((args.player_dir / "provenance.json").read_text())
    for name, digest in provenance["files"].items():
        path = args.player_dir / name
        if pin(path)["sha256"] != digest:
            raise ValueError("Prepared player artifact changed: " + name)
        paths.append(path)
    for scenario, digest in SOURCE_TRACES.items():
        path = args.source / f"source-contract-{scenario}.jsonl"
        if pin(path)["sha256"] != digest:
            raise ValueError("Accepted immutable source trace changed: " + scenario)
        paths.append(path)
    manifest = json.loads((args.source / "source-manifest.json").read_text())
    paths.extend(ROOT / entry["source_path"] for entry in manifest["extractions"])
    artifacts = {str(path.resolve()): pin(path) for path in paths}
    result = {"source_before": before, "immutable_source": source_identity, "artifacts": artifacts, "scenarios": {},
              "claim": "base plus exact native dirty source identity, immutable accepted source captures; no GPU, hardware, full Engine/MInput or startup RNG parity"}
    try:
        bank = json.loads((args.player_dir / "bank.json").read_text())
        for scenario in SOURCE_TRACES:
            rows = [json.loads(line) for line in (args.source / f"source-contract-{scenario}.jsonl").read_text().splitlines()]
            inputs = [r for r in rows if r.get("event") == "natural-frame"]
            fixture = output / f"{scenario}.inputs"
            fixture.write_text("".join(f"{r['tick']} {int('Right' in r['keys'])-int('Left' in r['keys'])} {int('C' in r['keys'])}\n" for r in inputs))
            native_path = output / f"{scenario}.native.jsonl"
            command = list(map(str, [args.native, args.mask, args.hazards, args.player_dir / "player.txt", fixture, int(scenario == "checkpoint-repeat")]))
            with native_path.open("x") as stream:
                subprocess.run(command, cwd=ROOT, stdout=stream, check=True)
            native = [json.loads(line) for line in native_path.read_text().splitlines()]
            result["scenarios"][scenario] = compare(rows, native, bank, provenance["layout"])
            result["scenarios"][scenario].update({"command": command, "input": pin(fixture), "native_output": pin(native_path)})
        result["status"] = "passed"
    except Exception as error:
        result["status"] = "failed"
        result["error"] = str(error)
        raise
    finally:
        result["source_after"] = validate_source_state(before)
        for path, identity in artifacts.items():
            if pin(Path(path)) != identity:
                raise ValueError("Input/source/native artifact drift: " + path)
        (output / "checks.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["scenarios"], indent=2))


if __name__ == "__main__":
    main()
