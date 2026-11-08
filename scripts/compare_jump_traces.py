#!/usr/bin/env python3
"""Require jump-family behavior coverage in addition to exact Dash phase traces."""

from pathlib import Path
import math
import struct
from compare_dash_traces import FIELDS, FLOATS, compare as compare_dash
from fixture_protocol import float_bits

DEFAULT_FIXTURES = Path(__file__).resolve().parents[1] / "tests/native/jumps.fixtures"


def f32(value):
    return struct.unpack("f", struct.pack("f", value))[0]


def validate_coverage(rows, name):
    snapshots = {}
    for text in rows:
        row = dict(zip(FIELDS, text.split("\t"), strict=True))
        key = (row["case"], int(row["frame"]), row["phase"])
        snapshots[key] = row
        if row["stamina"] != float_bits("110"):
            raise ValueError(f"{name}: Unsupported stamina/profile")

    def require(case, frame, phase="complete", **values):
        key = (case, frame, phase)
        if key not in snapshots:
            raise ValueError(f"{name}: Missing jump-family checkpoint {key}")
        row = snapshots[key]
        for field, value in values.items():
            expected = float_bits(str(value)) if field in FLOATS else str(value)
            if row[field] != expected:
                raise ValueError(f"{name}: {key} {field}: expected {expected}, got {row[field]}")

    for case, facing, duck in (("super_right", 1, False), ("super_left", -1, False),
                               ("hyper_right", 1, True), ("hyper_left", -1, True)):
        angle = f32(f32(f32(math.pi) * -3.0) / 16.0) if duck else f32(-f32(math.pi) / 4.0)
        require(case, 2, "freeze", jump_buffer=.08, state=2, dir_x=0, dir_y=0)
        require(case, 3, state=0, coroutine_active=0, events=1, speed_x=facing * (325 if duck else 260),
                speed_y=-52.5 if duck else -105, jump_buffer=0, var_timer=.2, attack=0, duck=0, launched=1,
                glider=.55, glider_x=f32(math.cos(angle)), glider_y=f32(math.sin(angle)), dir_x=0, dir_y=0)
    for case, speed in (("wall_right_neutral", -130), ("wall_left_neutral", 130), ("wall_right_priority", -130)):
        require(case, 1, speed_x=speed, speed_y=-105, force_x=0, force_timer=0, low_friction=.15,
                jump_buffer=0, var_timer=.2, launched=0)
    require("wall_right_neutral", 2, move_x=1, force_timer=0)
    require("wall_forced_crossing", 1, force_x=1, force_timer=.16, move_x=-1)
    require("wall_forced_crossing", 2, "ground", low_friction=f32(f32(.15) - f32(.16)))
    require("wall_forced_crossing", 2, "preamble", force_timer=0, move_x=1, facing=1, aim_x=1)
    require("wall_forced_crossing", 3, "preamble", force_timer=0, move_x=-1, facing=-1, aim_x=-1)
    require("dash_horizontal_wall", 4, state=0, speed_x=-130, speed_y=-105, force_x=-1, force_timer=.16, coroutine_active=0)
    require("dash_diagonal_wall", 4, state=0, speed_x=130, speed_y=-105, force_timer=0, coroutine_active=0)
    for case, speed in (("bounce_five", -170), ("bounce_left_five", 170), ("spike_allows_three", -170)):
        require(case, 4, state=0, speed_x=speed, speed_y=-160, var_timer=.25, force_timer=0,
                low_friction=0, launched=1, glider_x=-0.0, glider_y=-1, jump_buffer=0)
    require("spike_shortens_five", 4, state=2, speed_y=-240, jump_buffer=.08, var_timer=0)
    require("postdash_attack", 6, state=0, speed_x=-170, speed_y=-160, launched=1, var_timer=.25)
    require("postdash_expired", 6, state=0, speed_x=-130, speed_y=-105, launched=0, var_timer=.2)
    require("inherited_force", 5, state=0, force_x=-1, force_timer=.16, low_friction=.15, speed_x=-170, var_timer=.25)
    require("wall_hold", 2, speed_y=-105, var_timer=.1)
    require("wall_release", 2, speed_y=-15, var_timer=0)
    require("ceiling_early", 2, speed_y=0, var_timer=.16)
    require("ceiling_late", 2, speed_y=0, var_timer=0)
    require("bounds_guard", 1, jump_buffer=.08, var_timer=0, speed_x=0)
    require("blocked_unduck", 3, state=2, duck=1, jump_buffer=.08, var_timer=0)
    require("retention_then_jump", 2, retention=.06, speed_x=-130)
    require("retention_then_jump", 3, retention=0)
    require("horizontal_vertical_hazard", 1, "removed", dead=1, speed_x=0, speed_y=0, checked="4", overlaps="4")


def compare(reference, native, fixtures=DEFAULT_FIXTURES):
    return compare_dash(reference, native, fixtures, coverage=validate_coverage)
