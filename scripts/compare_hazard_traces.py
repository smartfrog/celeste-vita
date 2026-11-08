#!/usr/bin/env python3
"""Validate the separate static-hazard grammar and fixture coverage before exact equality."""

from dataclasses import dataclass
from pathlib import Path
import struct

from compare_native_traces import compare_rows
from compare_player_traces import PHASES
from compare_grid_traces import grid_fields
from fixture_protocol import IDENTIFIER, integer, float_bits

FIELDS = ("case", "step", "operation", "result", "delta", "x", "y", "remainder_x", "remainder_y", "speed_x", "speed_y",
          "ducking", "collider", "on_ground", "was_on_ground", "dead", "depth", "locked", "collidable", "removed",
          "death_x", "death_y", "events", "refill_called", "checked", "overlaps", "phases", "dashes", "stamina", "state",
          "previous_state", "changed", "previous_x", "previous_y", "grace", "var_timer", "var_speed", "max_fall", "sample")
FLOATS = (4, *range(5, 11), 20, 21, 28, *range(32, 38))
BOOLS = (11, 13, 14, 15, 17, 18, 19, 23, 31)
DEFAULT_FIXTURES = Path(__file__).resolve().parents[1] / "tests/native/hazards.fixtures"


@dataclass(frozen=True)
class Snapshot:
    case: str
    step: int
    operation: str
    result: str
    delta: str
    dead: bool
    direction: tuple
    checked: str
    overlaps: str
    phases: str
    sample: str


def fixture_operations(path):
    snapshots, cases = [], set()
    case, step, dead = None, 0, False
    spikes, bodies = {}, set()
    checked = overlaps = "-"
    direction = ("00000000", "00000000")
    for number, text in enumerate(Path(path).read_text().splitlines(), 1):
        f = text.split()
        if not f or f[0].startswith("#"):
            continue
        try:
            op = f[0]
            if op == "case":
                if len(f) != 8 or not IDENTIFIER.fullmatch(f[1]) or f[1] in cases or (case and not step):
                    raise ValueError("Invalid/duplicate/empty case")
                for v in f[2:6]:
                    float_bits(v)
                if integer(f[6], -2147483648, 2147483647) >= integer(f[7], -2147483648, 2147483647):
                    raise ValueError("Invalid bounds")
                case, step, dead, spikes, bodies = f[1], 0, False, {}, set()
                checked = overlaps = "-"
                direction = ("00000000", "00000000")
                cases.add(case)
                continue
            if not case:
                raise ValueError("Operation before case")
            if op in {"solid", "jump", "grid", "spike"}:
                if step or len(f) != (12 if op == "grid" else 7):
                    raise ValueError("Static geometry must precede operations")
                integer(f[1], 1, 2147483647)
                if f[1] in bodies:
                    raise ValueError("Duplicate static identity")
                bodies.add(f[1])
                if op == "grid":
                    grid_fields(f)
                else:
                    for v in f[2:4]:
                        float_bits(v)
                    if op == "spike":
                        integer(f[4], 1, 2147483647)
                        if f[5] not in {"up", "left"}:
                            raise ValueError("Unsupported spike")
                        spikes[f[1]] = f[5]
                    else:
                        for v in f[4:6]:
                            if struct.unpack(">f", bytes.fromhex(float_bits(v)))[0] < 0:
                                raise ValueError("Negative dimension")
                    integer(f[6], 0, 1)
                continue
            step += 1
            phases = "-"
            delta = "00000000"
            if op == "die":
                if len(f) != 5 or f[3] != "=>" or f[4] != ("ignored" if dead else "accepted"):
                    raise ValueError("Invalid death operation/guard coverage")
                supplied = tuple(float_bits(v) for v in f[1:3])
                sample = ",".join(supplied)
                if not dead:
                    direction = supplied
                dead, result = True, f[4]
            elif op == "tick":
                if len(f) < 13 or f[10] != "=>":
                    raise ValueError("Missing frame coverage annotation")
                delta = float_bits(f[1])
                if struct.unpack(">f", bytes.fromhex(delta))[0] < 0:
                    raise ValueError("Negative delta")
                for v in f[2:4]:
                    integer(v, -1, 1)
                for v in f[4:10]:
                    integer(v, 0, 1)
                sample = ",".join(f[2:10])
                outcome = f[11]
                if outcome == "rejected":
                    if len(f) != 13 or f[12] != "-" or not (dead or f[8:10] != ["0", "0"]):
                        raise ValueError("Unjustified rejection")
                    result = "rejected"
                else:
                    if dead or f[8:10] != ["0", "0"]:
                        raise ValueError("Frame outside accepted lifetime/profile")
                    ids = list(spikes)
                    if outcome.startswith("dead:") and outcome[5:] in spikes:
                        killer = outcome[5:]
                        ids = ids[:ids.index(killer) + 1]
                        dead, result = True, "removed"
                        direction = ("00000000", "bf800000") if spikes[killer] == "up" else ("bf800000", "00000000")
                    elif outcome == "alive":
                        result = "frame"
                    else:
                        raise ValueError("Invalid terminal coverage")
                    covered = [] if f[12] == "-" else f[12].split(",")
                    if len(set(covered)) != len(covered) or covered != [i for i in ids if i in covered] or (dead and (not covered or covered[-1] != killer)):
                        raise ValueError("Invalid ordered overlap coverage")
                    checked, overlaps = ",".join(ids) or "-", ",".join(covered) or "-"
                    callbacks = {"h": [], "v": []}
                    previous = "h"
                    for value in f[13:]:
                        axis, identity = value.split(":")
                        if axis not in callbacks or identity not in bodies - spikes.keys() or (axis == "h" and previous == "v"):
                            raise ValueError("Invalid callback coverage")
                        callbacks[axis].append(identity)
                        previous = axis
                    ordered = []
                    for phase in (*PHASES[:8], "removed") if dead else PHASES:
                        axis = {"horizontal": "h", "vertical": "v"}.get(phase)
                        for identity in callbacks.get(axis, []):
                            ordered.extend((f"collision_{axis}:{identity}", f"collided_{axis}:{identity}"))
                        ordered.append(phase)
                    phases = ",".join(ordered)
            else:
                raise ValueError("Unknown hazard operation")
            snapshots.append(Snapshot(case, step, op, result, delta, dead, direction, checked, overlaps, phases, sample))
        except (ValueError, IndexError) as error:
            raise ValueError(f"Fixture {path} line {number}: {error}") from error
    if not snapshots or not step:
        raise ValueError("Empty hazard fixture/case")
    return snapshots


def validate_trace(rows, snapshots, name):
    if len(rows) != len(snapshots):
        raise ValueError(f"{name}: expected {len(snapshots)} rows, got {len(rows)}")
    for number, (text, expected) in enumerate(zip(rows, snapshots), 1):
        try:
            f = text.split("\t")
            if len(f) != len(FIELDS):
                raise ValueError("Invalid hazard TSV field count")
            if f[:5] != [expected.case, str(expected.step), expected.operation, expected.result, expected.delta]:
                raise ValueError("Unexpected case/step/operation/result/delta")
            for i in FLOATS:
                float_bits("@" + f[i])
            for i in BOOLS:
                integer(f[i], 0, 1)
            if f[12] != ("duck" if f[11] == "1" else "normal"):
                raise ValueError("Movement collider not restored")
            dead = str(int(expected.dead))
            if [f[15], f[17], f[19]] != [dead] * 3 or f[18] != str(1 - int(expected.dead)) or f[16] != ("-1000000" if expected.dead else "0"):
                raise ValueError("Invalid immediate death flags/depth/collision")
            if tuple(f[20:22]) != expected.direction or f[22] != ("corpse_created,corpse_added,player_removed" if expected.dead else "-"):
                raise ValueError("Invalid death direction/event order")
            if expected.dead and f[9:11] != ["00000000"] * 2:
                raise ValueError("Death must clear both speed components")
            if f[24:27] != [expected.checked, expected.overlaps, expected.phases]:
                raise ValueError("Missing/foreign/reordered hazard or frame phase coverage")
            if f[27:31] != ["1", "42dc0000", "0", "-1"]:
                raise ValueError("Unsupported inventory/state")
            if f[38] != expected.sample:
                raise ValueError("Input sample differs from fixture")
        except ValueError as error:
            raise ValueError(f"{name} row {number}: {error}") from error


def compare(reference, native, fixtures=DEFAULT_FIXTURES):
    expected = fixture_operations(fixtures)
    validate_trace(reference, expected, "reference")
    validate_trace(native, expected, "native")
    return compare_rows(reference, native, FIELDS)
