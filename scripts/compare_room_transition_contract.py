"""Validate and exactly compare the bounded original-source transition recording."""

import argparse
import json
from pathlib import Path
import struct


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(rows):
    require(not any(row.get("event") == "boundary" for row in rows), "Unsupported boundary cannot establish closure")
    phases = {(row["tick"], row["phase"]): row["state"] for row in rows if row.get("event") == "phase"}
    frames = [row for row in rows if row.get("event") == "frame"]
    require(frames and [row["tick"] for row in frames] == list(range(len(frames))), "Missing or reordered frame stream")
    require(len(phases) == 5 * len(frames), "Each unfrozen fixture frame needs all five source phase observations")
    require(any(row.get("event") == "experiment-ended" and row.get("ticks") == len(frames)
                and row.get("nativeAttempts") == 0 and row.get("nativeMappings") == [] for row in rows), "Fresh source execution did not end cleanly")
    initial = phases[(0, "before-frame")]
    require(initial["room"] == "1" and initial["position"] == [19, 144] and initial["state"] == 14, "Missing actual first-room natural spawn")
    requests = [(tick, state) for (tick, phase), state in phases.items() if phase == "before-eof" and state["endOfFrame"]]
    require(len(requests) == 1, "Expected exactly one original deferred request")
    request_tick, request = requests[0]
    require(any("NextLevel" in method for method in request["endOfFrame"]), "Missing original NextLevel delegate")
    require(request["room"] == "1" and not request["Transitioning"], "Transition must not switch immediately")
    after_eof = phases[(request_tick, "after-eof")]
    require(after_eof["room"] == "1" and after_eof["Transitioning"] and not after_eof["endOfFrame"], "EOF must create coroutine before incoming LoadLevel")
    commits = [(tick, state) for (tick, phase), state in phases.items() if phase == "before-eof" and state["room"] == "2"]
    require(commits, "No incoming source room")
    commit_tick, incoming = commits[0]
    require(commit_tick == request_tick + 1 and incoming["Transitioning"], "Incoming load belongs to next coroutine update")
    require(incoming["bounds"] == [240, -184, 320, 180] and incoming["previousBounds"] == [0, 0, 320, 180], "Room world origins missing")
    completions = [(tick, state) for tick, state in commits if not state["Transitioning"]]
    require(completions, "Transition coroutine did not complete")
    completion_tick, complete = completions[0]
    require(complete["camera"] == [240, -184] and complete["respawn"] == [264, -24], "Original camera/respawn completion missing")
    require(complete["transition"] is None and complete["chaserCount"] == 0, "Original OnTransition/completion witness missing")
    require(incoming["chaserCount"] > 0, "Chaser reset witness requires prior source history")
    persistent = ("level", "player", "sprite", "hair")
    outgoing = set(incoming["transition"]["iterator"]["outgoing"])
    require(outgoing and not outgoing.intersection(entity["id"] for entity in complete["entities"]), "Outgoing entity leak")
    destination = {entity["type"] for entity in incoming["entities"]}
    require({"JumpthruPlatform", "Spring", "Strawberry"} <= destination, "Destination mechanics were dropped")
    require(sum(entity["type"] == "Spikes" for entity in complete["entities"]) == 3, "Wrong destination hazards")
    transition_rows = [phases[(tick, "after-frame")] for tick in range(commit_tick, completion_tick)]
    require(len(transition_rows) > 1 and len({tuple(state["camera"]) for state in transition_rows}) > 2, "Missing original camera easing")
    for state in transition_rows:
        require(next(entity for entity in state["entities"] if entity["type"] == "Strawberry")["strawberryWobble"] == 0,
                "Non-TransitionUpdate destination entity advanced during transition")
    for (tick, _), state in phases.items():
        require(all(state[key] == initial[key] for key in persistent), "Persistent reference identity changed")
        require(state["sameTrackedPlayer"] and state["sameSpriteOwner"] and state["sameHairOwner"], "Persistent ownership changed")
        require(not state["Dead"] and state["roomDeaths"] == state["sessionDeaths"] == state["saveDeaths"] == 0, "Death/reload is not this transition")
        require(state["nativeAttempts"] == 0, "Native import guard was reached")
        require(state["rng"]["identity"] == initial["rng"]["identity"], "Persistent RNG was not restored after legitimate source scopes")
        if tick > 35:
            require(state["state"] != 14, "Extra Respawn14 is not a transition")
    landed = [(tick, state) for tick, state in completions
              if state["groundQuery"] and state["position"][1] == -24 and state["speed"][1] == 0]
    require(landed, "No natural target JumpThru landing")
    landing_tick, landing = landed[0]
    controlled = [(tick, state) for tick, state in completions if tick > landing_tick
                  and state["saveJumps"] > landing["saveJumps"] and state["speed"][1] < 0]
    require(controlled, "No legal grounded Jump after landing")
    final = phases[(len(frames) - 1, "after-frame")]
    require(final["room"] == "2" and final["groundQuery"] and final["state"] == 0, "No final normal landing/control")
    return {"frames": len(frames), "request_tick": request_tick, "commit_tick": commit_tick,
            "completion_tick": completion_tick, "landing_tick": landing_tick, "control_tick": controlled[0][0],
            "final_position": final["position"], "final_camera": final["camera"],
            "persistent_ids": {key: initial[key] for key in persistent}, "outgoing_entities": len(outgoing),
            "source_only": True, "physical_or_native_proof": False}


def same(expected, actual, path):
    require(type(expected) is type(actual), "Type mismatch: " + path)
    if isinstance(expected, dict):
        require(expected.keys() == actual.keys(), "Field mismatch: " + path)
        for key in expected:
            same(expected[key], actual[key], path + "." + key)
    elif isinstance(expected, list):
        require(len(expected) == len(actual), "Length mismatch: " + path)
        for index, (left, right) in enumerate(zip(expected, actual, strict=True)):
            same(left, right, path + "[" + str(index) + "]")
    elif isinstance(expected, float):
        require(struct.pack("<f", expected) == struct.pack("<f", actual), "Float32 mismatch: " + path)
    else:
        require(expected == actual, "Value mismatch: " + path)


def compare(reference, candidate):
    summary = validate(reference)
    validate(candidate)
    events = {"phase", "input", "rng", "frame"}
    expected = [row for row in reference if row.get("event") in events]
    actual = [row for row in candidate if row.get("event") in events]
    same(expected, actual, "trace")
    return summary | {"compared_records": len(expected), "comparison": "exact scalar/integer and float32 bits; no epsilon"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    print(json.dumps(compare(*([json.loads(line) for line in path.read_text().splitlines()] for path in (args.reference, args.candidate))), indent=2))
