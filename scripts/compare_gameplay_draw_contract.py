"""Validate two fresh original update+GameplayRenderer runs, never GPU/pixel parity."""

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import struct

from native_room_revision import file_identity, verify_file_identities
from prepare_gameplay_draw_profile import AUDIT, verify_profile

PROJECTION_EVENTS = {"input", "phase", "rng", "draw-state", "draw-roster", "draw-command", "draw-dispatch", "frame"}


def validate_frame(roster, dispatch, commands, sheets=None):
    if roster["cameraAlias"] is not True or roster["cameraViewport"] != [320, 180]:
        raise ValueError("Original GameplayRenderer camera alias/viewport changed")
    expected = [value for value in roster["live"] if value["Visible"] and not value["hudExcluded"]]
    if [value["entity"] for value in expected] != [value["entity"] for value in dispatch["entities"]]:
        raise ValueError("Render dispatch differs from the live SOURCE roster/filter/order")
    if dispatch["commands"] != len(commands) or [value["index"] for value in commands] != list(range(len(commands))):
        raise ValueError("Ordered original commands were omitted/reordered")
    cursor = 0
    for owner, span in zip(expected, dispatch["entities"]):
        if span["drawStart"] != cursor or not cursor <= span["drawEnd"] <= len(commands):
            raise ValueError("Invalid entity command range")
        for command in commands[cursor:span["drawEnd"]]:
            if any(command["owner"][key] != owner[key] for key in ("entity", "depth", "actualDepth")):
                raise ValueError("Draw owner/depth differs from original dispatch")
        cursor = span["drawEnd"]
    if cursor != len(commands):
        raise ValueError("Unattributed original commands")
    batches = dispatch["batches"]
    if (len(batches) != 1 or batches[0]["SortMode"] != "Deferred" or batches[0]["HasEffect"] is not False
            or (batches[0]["DrawStart"], batches[0]["DrawEnd"]) != (0, len(commands))
            or len(batches[0]["Matrix"]) != 16):
        raise ValueError("Unsupported/incomplete original GameplayRenderer batch")
    for command in commands:
        if (not command["sheet"] or len(command["dimensions"]) != 2 or min(command["dimensions"]) <= 0
                or len(command["sourceRectangle"]) != 4 or len(command["verticesFloat32Bits"]) != 4
                or any(len(vertex) != 5 or any(type(value) is not int or not -(2 ** 31) <= value < 2 ** 31 for value in vertex)
                       for vertex in command["verticesFloat32Bits"])
                or command["clipping"] != "atlas source rectangle; GPU scissor not observed"):
            raise ValueError("Incomplete texture/geometry/clipping evidence")
        finite = all(math.isfinite(struct.unpack("<f", struct.pack("<i", value))[0])
                     for vertex in command["verticesFloat32Bits"] for value in vertex)
        if type(command["finiteGeometry"]) is not bool or command["finiteGeometry"] != finite:
            raise ValueError("Original nonfinite geometry classification changed")
        if sheets is not None and sheets.get(command["sheet"]) != command["dimensions"]:
            raise ValueError("Draw texture identity/dimensions differ from original sheet headers")


def inspect_trace(path, sheets):
    digest = hashlib.sha256()
    ticks = []
    commands = []
    roster = before = after = None
    dispatch_seen = False
    previous_after = None
    owners = Counter()
    hair_changes = rng_changes = outgoing_frames = degenerate = outlines = 0
    transitions = []
    last_room = None
    ended = False
    for line in path.open():
        row = json.loads(line)
        event = row["event"]
        if event in PROJECTION_EVENTS:
            digest.update(json.dumps(row, sort_keys=True, separators=(",", ":")).encode() + b"\n")
        if event == "boundary":
            raise ValueError("SOURCE execution reached an unsupported boundary: " + row["error"])
        if event == "phase" and row["phase"] == "before-frame" and previous_after is not None:
            if row["state"]["hairNodes"] != previous_after["hairNodes"]:
                raise ValueError("DRAW hair mutation did not persist into the next original update")
        elif event == "draw-state":
            if row["phase"] == "before-draw":
                if before is not None or commands or roster is not None:
                    raise ValueError("Unfinished previous draw frame")
                before = row
            elif row["phase"] == "after-draw":
                if before is None or row["tick"] != before["tick"] or roster is None or not dispatch_seen:
                    raise ValueError("Missing before/after DRAW observation")
                after = row["state"]
                hair_changes += before["state"]["hairNodes"] != after["hairNodes"]
                rng_changes += before["state"]["rng"] != after["rng"]
                previous_after = after
                ticks.append(row["tick"])
                before = roster = None
                dispatch_seen = False
                commands = []
            else:
                raise ValueError("Unknown DRAW state phase")
        elif event == "draw-roster":
            if before is None or roster is not None or row["tick"] != before["tick"]:
                raise ValueError("Draw roster is not bound to original pre-DRAW state")
            roster = row
            if [value["entity"] for value in roster["live"]] != [value["id"] for value in before["state"]["entities"]]:
                raise ValueError("Draw roster was reconstructed rather than observed live")
            decals = [value for value in roster["live"] if value.get("decal") is not None]
            expected_decals = 29 if before["state"]["room"] == "1" else (52 if before["state"]["Transitioning"] else 23)
            expected_banners = {29: 7, 52: 11, 23: 4}[expected_decals]
            if len(decals) != expected_decals or sum(value["decal"]["image"] == "Banner" for value in decals) != expected_banners:
                raise ValueError("Original authored decal/Banner roster changed")
        elif event == "draw-command":
            if before is None or roster is None or row["tick"] != before["tick"] or dispatch_seen:
                raise ValueError("Unbound draw command")
            commands.append(row)
            owners[row["owner"]["type"]] += 1
            degenerate += not row["finiteGeometry"]
        elif event == "draw-dispatch":
            if before is None or roster is None or row["tick"] != before["tick"] or dispatch_seen:
                raise ValueError("Unbound draw dispatch")
            dispatch_seen = True
            validate_frame(roster, row, commands, sheets)
            if row["outlineBefore"] != row["outlineAfter"]:
                raise ValueError("Original Spring DrawOutline did not restore Position/Color")
            for span in row["entities"]:
                if span["type"] == "Spring":
                    submitted = commands[span["drawStart"]:span["drawEnd"]]
                    offsets = [(x, y) for x in (-1, 0, 1) for y in (-1, 0, 1) if x or y]
                    if (len(submitted) != 9 or any(value["color"] != [0, 0, 0, 255] for value in submitted[:8])
                            or any(value["position"] != [submitted[-1]["position"][0] + x, submitted[-1]["position"][1] + y]
                                   for value, (x, y) in zip(submitted[:8], offsets))):
                        raise ValueError("Original DrawOutline eight-neighbor Render calls missing")
                    outlines += 1
            transition = before["state"]["transition"]
            outgoing = transition["iterator"]["outgoing"] if transition and transition["iterator"] else []
            dispatched = {span["entity"] for span in row["entities"]}
            visible = {value["entity"] for value in roster["live"] if value["Visible"] and not value["hudExcluded"]}
            if outgoing:
                if not set(outgoing) & visible <= dispatched:
                    raise ValueError("Visible outgoing SOURCE entities were omitted")
                outgoing_frames += 1
        elif event == "frame":
            if after is None or row["tick"] != len(ticks) - 1 or row["nativeAttempts"] != 0:
                raise ValueError("Original update/DRAW frame continuity or native isolation changed")
            if row["room"] != last_room:
                transitions.append([row["tick"], row["room"]])
                last_room = row["room"]
        elif event == "experiment-ended":
            ended = row["ticks"] == len(ticks) and row["nativeAttempts"] == 0 and row["nativeMappings"] == []
    if not ended or before is not None or ticks != list(range(514)) or transitions != [[0, "1"], [374, "2"]]:
        raise ValueError("Not an uninterrupted 514-frame original two-room update+DRAW route")
    required = {"BackgroundTiles", "SolidTiles", "Decal", "Player", "Spikes", "Spring", "ParticleSystem", "JumpthruPlatform", "Strawberry"}
    if not required <= owners.keys() or not hair_changes or not outgoing_frames or not outlines:
        raise ValueError("Missing meaningful original renderer/entity/state coverage")
    return {"projection_sha256": digest.hexdigest(), "frames": len(ticks), "commands": sum(owners.values()),
            "commands_by_owner_type": dict(owners), "draw_hair_mutation_frames": hair_changes,
            "draw_rng_mutation_frames": rng_changes, "visible_outgoing_frames": outgoing_frames,
            "original_outline_checks": outlines, "nonfinite_geometry_commands_preserved": degenerate,
            "room_changes": transitions, "final_rng": after["rng"], "final_hair": after["hairNodes"],
            "final_position": after["position"], "final_camera": after["camera"]}


def compare(profile, first, second):
    record = verify_profile(profile)
    receipts = []
    for directory in (first, second):
        receipt = json.loads((directory / "execution.json").read_text())
        if (not directory.resolve().is_relative_to(AUDIT) or receipt["exit_code"] != 0
                or receipt.get("profile_binding") != record["binding"]
                or Path(receipt["command"][1]) != profile / "Oracle.dll"
                or Path(receipt["command"][2]) != directory / "trace.jsonl"
                or receipt.get("trace") != file_identity(directory / "trace.jsonl")):
            raise ValueError("A fresh successful bound SOURCE execution is required")
        verify_file_identities(receipt["inputs"])
        if receipt["inputs"][str(profile / "Oracle.dll")] != record["compiled_artifacts"]["Oracle.dll"]:
            raise ValueError("Execution/profile artifact binding changed")
        receipts.append(receipt)
    if first.resolve() == second.resolve() or receipts[0]["inputs"] != receipts[1]["inputs"]:
        raise ValueError("Two distinct fresh runs of the same SOURCE/controls are required")
    sheets = json.loads((profile / "sheets.json").read_text())
    results = [inspect_trace(directory / "trace.jsonl", sheets) for directory in (first, second)]
    if results[0] != results[1]:
        raise ValueError("Fresh SOURCE state/RNG/hair/order/command projections differ")
    return {"schema": 1, "kind": "original-gameplay-command-coverage-gate1", "profile_binding": record["binding"],
            "status": "two-fresh-source-runs-match", "observed": results[0],
            "traces": {str(directory / "trace.jsonl"): file_identity(directory / "trace.jsonl") for directory in (first, second)},
            "claim": "Original update→GameplayRenderer→live EntityList commands; not full Level/GPU/pixels/Vita or CPU-only equivalence",
            "clipping": "Original atlas source rectangles; zero-height/nonfinite original submissions preserved; no GPU scissor observation"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("profile", "first", "second", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or not args.output.resolve().is_relative_to(AUDIT):
        raise ValueError("Gameplay-DRAW evidence must be fresh inside its private namespace")
    result = compare(args.profile.resolve(), args.first.resolve(), args.second.resolve())
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(result["status"])
