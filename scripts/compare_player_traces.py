#!/usr/bin/env python3
"""Check fixture-derived frame/phase/callback coverage before exact Player comparison."""

import argparse
from dataclasses import dataclass
from pathlib import Path
import struct

from compare_native_traces import compare_rows
from fixture_protocol import IDENTIFIER, integer, float_bits

FIELDS = ("case", "frame", "phase", "delta", "input_x", "input_y", "held", "raw_pressed", "released", "disabled", "grab", "dash",
          "x", "y", "remainder_x", "remainder_y", "previous_x", "previous_y", "speed_x", "speed_y", "facing", "move_x", "on_ground",
          "was_on_ground", "safe", "ducking", "hurtbox", "grace", "var_timer", "var_speed", "max_fall", "wall_timer", "wall_dir",
          "retention_timer", "retained_speed", "stamina", "dashes", "state", "previous_state", "changed", "buffer", "jump_pressed",
          "consumed", "launched", "hit", "direction_x", "direction_y", "moved_x", "moved_y", "target_x", "target_y")
DEFAULT_FIXTURES = Path(__file__).resolve().parents[1] / "tests/native/player.fixtures"
PHASES = ("input", "ground", "preamble", "normal", "boost", "unduck", "horizontal", "vertical", "hazards", "complete")
FLOAT_FIELDS = (3, *range(12, 20), *range(27, 32), 33, 34, 35, 40, *range(45, 51))
BOOL_FIELDS = (*range(6, 12), *range(22, 26), 39, 41, 42, 43)


@dataclass(frozen=True)
class Snapshot:
    case: str
    frame: int
    phase: str
    sample: tuple
    hit: str = "-1"


def fixture_operations(path):
    snapshots, cases = [], set()
    case, frame, bodies = None, 0, set()
    for line, text in enumerate(Path(path).read_text().splitlines(), 1):
        f = text.split()
        if not f or f[0].startswith("#"):
            continue
        try:
            op = f[0]
            if op == "case":
                if len(f) != 8 or not IDENTIFIER.fullmatch(f[1]) or f[1] in cases or (case is not None and frame == 0):
                    raise ValueError("Invalid/duplicate/empty case")
                for value in f[2:6]:
                    float_bits(value)
                left, right = (integer(v, -2147483648, 2147483647) for v in f[6:8])
                if left >= right:
                    raise ValueError("Invalid fixture bounds")
                case, frame, bodies = f[1], 0, set()
                cases.add(case)
            elif case is None:
                raise ValueError("Operation before case")
            elif op in {"solid", "jump"}:
                if len(f) != 7 or frame:
                    raise ValueError("Static platforms must precede frames")
                identity = f[1]
                integer(identity, 1, 2147483647)
                if identity in bodies:
                    raise ValueError("Duplicate platform identity")
                bodies.add(identity)
                for i, value in enumerate(f[2:6], 2):
                    bits = float_bits(value)
                    if i >= 4 and struct.unpack(">f", bytes.fromhex(bits))[0] < 0:
                        raise ValueError("Negative Hitbox dimension")
                integer(f[6], 0, 1)
            elif op == "tick":
                if len(f) < 10 or (len(f) > 10 and (f[10] != "=>" or len(f) == 11)):
                    raise ValueError("Invalid frame field count/annotation")
                delta = float_bits(f[1])
                if struct.unpack(">f", bytes.fromhex(delta))[0] < 0:
                    raise ValueError("Negative frame delta")
                for v in f[2:4]:
                    integer(v, -1, 1)
                for v in f[4:10]:
                    integer(v, 0, 1)
                frame += 1
                sample = (delta, *f[2:10])
                annotations = f[11:] if len(f) > 10 else []
                if annotations in (["!input"], ["!normal"]):
                    phases = [] if annotations == ["!input"] else list(PHASES[:3])
                    for phase in (*phases, "rejected"):
                        snapshots.append(Snapshot(case, frame, phase, sample))
                    continue
                if f[8:10] != ["0", "0"]:
                    raise ValueError("Grab/Dash must declare !input rejection")
                collisions = {"h": [], "v": []}
                last_axis = "h"
                for event in annotations:
                    parts = event.split(":")
                    if len(parts) != 2 or parts[0] not in collisions or parts[1] not in bodies:
                        raise ValueError("Invalid/foreign collision annotation")
                    axis, hit = parts
                    if axis == "h" and last_axis == "v":
                        raise ValueError("Horizontal callbacks must precede vertical callbacks")
                    last_axis = axis
                    collisions[axis].append(hit)
                for phase in PHASES:
                    axis = {"horizontal": "h", "vertical": "v"}.get(phase)
                    if axis:
                        for hit in collisions[axis]:
                            for prefix in ("collision_", "collided_"):
                                snapshots.append(Snapshot(case, frame, prefix + axis, sample, hit))
                    snapshots.append(Snapshot(case, frame, phase, sample))
            else:
                raise ValueError("Unknown Player command")
        except ValueError as error:
            raise ValueError(f"Fixture {path} line {line}: {error}") from error
    if not snapshots or frame == 0:
        raise ValueError("Fixture/case has no frames")
    return snapshots


def validate_trace(rows, snapshots, name):
    for row, text in enumerate(rows, 1):
        try:
            f = text.split("\t")
            if len(f) != len(FIELDS):
                raise ValueError(f"Expected {len(FIELDS)} TSV fields")
            if row > len(snapshots):
                raise ValueError("Unexpected row after final frame")
            expected = snapshots[row - 1]
            if f[:3] != [expected.case, str(expected.frame), expected.phase]:
                raise ValueError(f"Unexpected frame/phase {f[:3]}; expected {expected}")
            for index in FLOAT_FIELDS:
                float_bits("@" + f[index])
            for index in BOOL_FIELDS:
                integer(f[index], 0, 1)
            for index in (4, 5, 21, 32):
                integer(f[index], -1, 1)
            if f[20] not in {"-1", "1"} or f[26] != ("duck" if f[25] == "1" else "normal"):
                raise ValueError("Invalid facing/collider identity")
            if f[36:39] != ["1", "0", "-1"] or f[42:44] != ["0", "0"]:
                raise ValueError("Unsupported state/inventory/consumption/launched invariant")
            if tuple(f[3:12]) != expected.sample or f[44] != expected.hit:
                raise ValueError("Sample/delta/callback identity differs from fixture")
            if expected.hit == "-1" and f[45:] != ["00000000"] * 6:
                raise ValueError("Non-callback phase has a collision payload")
            if expected.hit != "-1":
                direction, perpendicular = (45, 46) if expected.phase.endswith("_h") else (46, 45)
                if f[direction] not in {"3f800000", "bf800000"} or f[perpendicular] not in {"00000000", "80000000"}:
                    raise ValueError("Invalid collision direction")
        except ValueError as error:
            raise ValueError(f"{name} Row {row}: {error}") from error
    if len(rows) != len(snapshots):
        raise ValueError(f"{name}: Missing frame/phase; expected {len(snapshots)} rows, got {len(rows)}")


def compare(reference, native, fixtures=DEFAULT_FIXTURES):
    expected = fixture_operations(fixtures)
    validate_trace(reference, expected, "reference")
    validate_trace(native, expected, "native")
    return compare_rows(reference, native, FIELDS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("native", type=Path)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    args = parser.parse_args()
    try:
        rows = compare(args.reference.read_text().splitlines(), args.native.read_text().splitlines(), args.fixtures)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")
    print(f"MATCH: {rows} rows, {len(FIELDS)} exact fields per row")


if __name__ == "__main__":
    main()
