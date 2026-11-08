#!/usr/bin/env python3
"""Validate explicit bounded Dash phase coverage, then compare exact float32 traces."""

from pathlib import Path
import struct

from compare_native_traces import compare_rows
from fixture_protocol import float_bits, integer, IDENTIFIER
from compare_grid_traces import grid_fields


FIELDS = tuple("case frame phase raw delta freeze clock_frame x y remainder_x remainder_y previous_x previous_y speed_x speed_y facing move_x ground was_ground safe duck dashes state previous_state changed jump_buffer jump_pressed jump_held dash_buffer dash_pressed dash_held started dash_ground called events before_x before_y dir_x dir_y aim_x aim_y attack cooldown refill glider trail trail_count auto auto_timer grace var_timer var_speed max_fall retention retained dead hit direction_x direction_y moved_x moved_y target_x target_y coroutine_active wait ended stack refill_called checked overlaps force_x force_timer low_friction launched glider_x glider_y stamina".split())
FLOATS = set("raw delta freeze x y remainder_x remainder_y previous_x previous_y speed_x speed_y jump_buffer dash_buffer before_x before_y dir_x dir_y aim_x aim_y attack cooldown refill glider trail auto_timer grace var_timer var_speed max_fall retention retained direction_x direction_y moved_x moved_y target_x target_y wait".split())
FLOATS.update(("force_timer", "low_friction", "glider_x", "glider_y", "stamina"))
BOOLS = set("ground was_ground safe duck changed jump_pressed jump_held dash_pressed dash_held started dash_ground called auto dead coroutine_active ended refill_called".split())
BOOLS.add("launched")
DEFAULT_FIXTURES = Path(__file__).resolve().parents[1] / "tests/native/dash.fixtures"


def fixture_operations(path, *, point_queries=False):
    expected, cases, bodies, spikes = [], set(), set(), set()
    case, frame = None, 0
    for number, text in enumerate(Path(path).read_text().splitlines(), 1):
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
                if integer(f[6], -2147483648, 2147483647) >= integer(f[7], -2147483648, 2147483647):
                    raise ValueError("Invalid bounds")
                case, frame, bodies, spikes = f[1], 0, set(), set()
                cases.add(case)
            elif case is None:
                raise ValueError("Operation before case")
            elif op in {"solid", "jump", "grid", "spike"}:
                size = 12 if op == "grid" else 7
                if frame or (len(f) != size and not (point_queries and op != "spike" and len(f) == size + 1)):
                    raise ValueError("Static world must precede frames")
                identity = integer(f[1], 1, 2147483647)
                if identity in bodies or identity in spikes:
                    raise ValueError("Duplicate world identity")
                (spikes if op == "spike" else bodies).add(identity)
                if op == "grid":
                    grid_fields(f[:12])
                elif op == "spike":
                    float_bits(f[2]); float_bits(f[3]); integer(f[4], 1, 1000000); integer(f[6], 0, 1)
                    if f[5] not in {"up", "left"}:
                        raise ValueError("Unsupported spikes")
                else:
                    for index, value in enumerate(f[2:6], 2):
                        bits = float_bits(value)
                        if index >= 4 and struct.unpack(">f", bytes.fromhex(bits))[0] < 0:
                            raise ValueError("Negative Hitbox dimension")
                    integer(f[6], 0, 1)
                if len(f) == size + 1:
                    integer(f[-1], 0, 1)
            elif op == "point" and point_queries:
                if len(f) != 4:
                    raise ValueError("Invalid point probe")
                float_bits(f[1]); float_bits(f[2]); integer(f[3], 0, 1)
                frame += 1
                expected.append((case, str(frame), "point_hit" if f[3] == "1" else "point_miss", "-1", float_bits("0")))
            elif op == "tick":
                if len(f) < 15 or (len(f) > 15 and (f[15] != "=>" or len(f) == 16)):
                    raise ValueError("Invalid Dash tick")
                raw = float_bits(f[1])
                if struct.unpack(">f", bytes.fromhex(raw))[0] < 0:
                    raise ValueError("Negative frame delta")
                for index in (2, 3, 10, 11):
                    integer(f[index], -1, 1)
                for index in (*range(4, 10), 12, 13, 14):
                    integer(f[index], 0, 1)
                frame += 1
                annotations = f[16:]
                special = set(annotations) & {"freeze", "!input", "!dash"}
                if special and (len(special) != 1 or len(annotations) != 1):
                    raise ValueError("Frozen/rejected ticks cannot declare other phases")
                phases = ["input", "ground", "preamble"]
                if "freeze" in annotations:
                    phases = ["input", "freeze"]
                elif "!input" in annotations:
                    phases = ["rejected"]
                elif "!dash" in annotations:
                    phases += ["rejected"]
                else:
                    if "dash" in annotations:
                        phases += ["dash_update"]
                    phases += ["normal", "boost", "unduck", "horizontal", "vertical"]
                    phases += ["removed"] if "dead" in annotations else ["hazards", "complete"]
                hits = {}
                for annotation in annotations:
                    if annotation in {"freeze", "dash", "!dash", "!input", "dead"}:
                        continue
                    axis, identity = annotation.split(":")
                    if axis not in {"h", "v"} or int(identity) not in bodies:
                        raise ValueError("Invalid collision annotation")
                    hits.setdefault(axis, []).append(identity)
                for phase in phases:
                    axis = {"horizontal": "h", "vertical": "v"}.get(phase)
                    for hit in hits.get(axis, []):
                        for prefix in ("collision_", "collided_"):
                            expected.append((case, str(frame), prefix + axis, hit, raw))
                    expected.append((case, str(frame), phase, "-1", raw))
            else:
                raise ValueError("Unsupported operation")
        except (ValueError, IndexError) as error:
            raise ValueError(f"Fixture {path} line {number}: {error}") from error
    if not expected or not frame:
        raise ValueError("Empty Dash fixture/case")
    return expected


def validate_trace(rows, expected, name, *, fields=FIELDS, floats=FLOATS, bools=BOOLS, states=("0", "2")):
    if len(rows) != len(expected):
        raise ValueError(f"{name}: Expected {len(expected)} phase rows, got {len(rows)}")
    for number, (text, snapshot) in enumerate(zip(rows, expected), 1):
        f = text.split("\t")
        if len(f) != len(fields) or (*f[:3], f[fields.index("hit")], f[3]) != snapshot:
            raise ValueError(f"{name} Row {number}: Unexpected schema/phase/callback; expected {snapshot}")
        for field, value in zip(fields[3:], f[3:]):
            if field in floats:
                float_bits("@" + value)
            elif field in bools:
                integer(value, 0, 1)
        if f[fields.index("state")] not in states or f[fields.index("dashes")] not in {"0", "1"}:
            raise ValueError(f"{name} Row {number}: Unsupported state/inventory")
        integer(f[fields.index("force_x")], -1, 1)


def compare(reference, native, fixtures=DEFAULT_FIXTURES, coverage=None):
    expected = fixture_operations(fixtures)
    validate_trace(reference, expected, "reference")
    validate_trace(native, expected, "native")
    if coverage is not None:
        coverage(reference, "reference")
        coverage(native, "native")
    return compare_rows(reference, native, FIELDS)
