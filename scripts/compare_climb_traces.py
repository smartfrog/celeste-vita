#!/usr/bin/env python3
"""Compare opt-in static Climb traces without changing the historical Dash schema."""

from pathlib import Path

from compare_dash_traces import FIELDS as DASH_FIELDS, FLOATS as DASH_FLOATS, BOOLS as DASH_BOOLS
from compare_dash_traces import fixture_operations, validate_trace
from compare_native_traces import compare_rows
from fixture_protocol import float_bits, integer

FIELDS = DASH_FIELDS + tuple("input_x input_y input_jump_held input_jump_pressed input_jump_released input_disabled input_grab input_legacy_dash input_aim_x input_aim_y input_dash_held input_dash_pressed input_dash_released grab_check climb_no_move last_climb_move wall_boost_timer wall_boost_dir hop_wait_x hop_wait_speed hop_solid hop_solid_x hop_solid_y tired wall_slide_timer wall_slide_dir".split())
FLOATS = DASH_FLOATS | set("climb_no_move wall_boost_timer hop_wait_speed hop_solid_x hop_solid_y wall_slide_timer".split())
BOOLS = DASH_BOOLS | set("input_jump_held input_jump_pressed input_jump_released input_disabled input_grab input_legacy_dash input_dash_held input_dash_pressed input_dash_released grab_check tired".split())
DEFAULT_FIXTURES = Path(__file__).resolve().parents[1] / "tests/native/climb.fixtures"


def validate_coverage(rows, name):
    snapshots = {tuple(f[:3]): dict(zip(FIELDS, f, strict=True)) for f in (text.split("\t") for text in rows)}

    def require(case, frame, phase="complete", **values):
        key = case, str(frame), phase
        if key not in snapshots:
            raise ValueError(f"{name}: Missing Climb checkpoint {key}")
        row = snapshots[key]
        for field, value in values.items():
            expected = float_bits(str(value)) if field in FLOATS else str(value)
            if row[field] != expected:
                raise ValueError(f"{name}: {key} {field}: expected {expected}, got {row[field]}")

    require("entry_right", 1, state=1, climb_no_move=.1, speed_y=10)
    require("entry_left", 1, state=1, facing=-1)
    require("entry_gap", 1, state=1, x=1)
    require("entry_corner", 1, state=1, y=-1)
    require("entry_bounds", 1, state=0)
    require("entry_rising", 1, state=0)
    require("timer_up", 2, state=1, stamina=110, last_climb_move=0)
    require("timer_up", 4, state=1, last_climb_move=-1)
    require("idle_down", 2, stamina=109, last_climb_move=0)
    require("idle_down", 3, stamina=109, last_climb_move=1, speed_y=80)
    require("ground_idle", 3, stamina=109, ground=1)
    require("release_land", 3, state=0)
    require("release_land", 5, ground=1, stamina=110)
    require("tired_boundary", 2, stamina=20, tired=0)
    require("tired_boundary", 3, stamina=19, tired=1)
    require("tired_boundary", 5, state=0)
    require("exhaustion", 2, state=0, stamina=0)
    require("exhaustion", 3, state=0)
    require("jump_dash_release", 2, state=0, stamina=82.5, dashes=1, wall_boost_timer=.2)
    require("dash_release", 2, state=2, dashes=0, freeze=.05)
    require("dash_release", 3, "freeze", state=2, freeze=0)
    require("grab_before_dash", 1, state=1, dashes=1)
    require("air_climb_jump_refund", 2, stamina=82.5, wall_boost_timer=.2)
    require("air_climb_jump_refund", 4, "preamble", stamina=110, speed_x=-130, wall_boost_timer=0)
    require("ground_climb_jump", 2, stamina=110, speed_y=-105)
    require("negative_climb_jump", 3, stamina=-8.5, tired=1)
    require("away_wall_jump", 2, speed_x=-130, stamina=110, force_x=-1, force_timer=.16)
    require("away_wall_jump", 3, "preamble", move_x=-1, facing=-1, force_timer=0)
    require("delayed_hop", 2, state=0, hop_solid=1, hop_wait_x=1, hop_wait_speed=100, speed_y=-120)
    require("delayed_hop", 3, "preamble", hop_wait_x=0, speed_x=100)
    require("immediate_hop", 3, state=0, hop_solid=-1, hop_wait_x=0, speed_x=100, speed_y=-120)
    require("blocked_hop", 2, state=1, last_climb_move=0, stamina=109)
    require("spike_hop_blocker", 2, state=1, last_climb_move=0, stamina=109)
    require("half_open_solid_top", 2, state=1, last_climb_move=-1)
    require("grid_ledge", 3, state=0, hop_solid=1)
    require("jump_thru_boost", 2, state=1)
    require("disabled_grab", 1, state=0, grab_check=0)
    require("hop_identity_order", 2, hop_solid=7, hop_solid_x=4, hop_solid_y=-5, hop_wait_x=1)
    require("hop_identity_collidable", 2, hop_solid=3, hop_wait_x=1)
    require("normal_selector_tired", 4, stamina=-8.5, speed_y=-105, wall_boost_timer=.2)
    require("pending_tired", 3, stamina=-6.5, tired=0, wall_boost_timer=.2)
    require("pending_tired", 4, tired=1, wall_boost_timer=0)
    require("slip_second_add_y", 2, state=0, hop_solid=1, hop_wait_x=1)


def compare(reference, native, fixtures=DEFAULT_FIXTURES):
    expected = fixture_operations(fixtures, point_queries=True)
    samples = {}
    case, frame = None, 0
    for text in Path(fixtures).read_text().splitlines():
        f = text.split()
        if not f or f[0].startswith("#"):
            continue
        if f[0] == "case":
            case, frame = f[1], 0
        elif f[0] in {"tick", "point"}:
            frame += 1
            samples[case, str(frame)] = f[2:15] if f[0] == "tick" else ["0"] * 13
    for rows, name in ((reference, "reference"), (native, "native")):
        validate_trace(rows, expected, name, fields=FIELDS, floats=FLOATS, bools=BOOLS, states=("0", "1", "2"))
        for text in rows:
            f = text.split("\t")
            row = dict(zip(FIELDS, f, strict=True))
            if f[len(DASH_FIELDS):len(DASH_FIELDS)+13] != samples[row["case"], row["frame"]]:
                raise ValueError(f"{name}: Input sample differs from fixture")
            for field in ("input_x", "input_y", "input_aim_x", "input_aim_y", "wall_boost_dir", "hop_wait_x", "last_climb_move", "wall_slide_dir"):
                integer(row[field], -1, 1)
            integer(row["hop_solid"], -1, 2147483647)
        validate_coverage(rows, name)
    return compare_rows(reference, native, FIELDS)
