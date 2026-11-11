"""Source pins and bounded checks on the Dash producer's closed RGBA attachment."""

import math
import re

from native_room_revision import REPO_ROOT, file_identity

FIXTURE_ID = "first_room_dash_trails_v1"
FIXTURE_SOURCE = "src/vita/guest_dash_probe.hpp"


def attachment_pixel(raw, x, top):
    offset = ((511 - top) * 512 + x) * 4
    return raw[offset:offset + 4]


def validate_dash_probe(pixels, metadata, raw):
    if len(raw) != 512 * 512 * 4:
        raise ValueError("Dash probe requires the exact 512x512 raw RGBA attachment")
    expected = {"trail_probe":"diagnostic_rgba_fbo", "trail_depth":"1",
                "trail_target_logical_RGBA_bytes":"1048576", "other_captured_tiles_preserved":"1",
                "single_ghost_xy":"200,16", "between_ghost_xy":"240,16;248,16",
                "tint_rgba":"51,137,191,191", "FBO_RGBA":"512x512", "raw_rows":"GL_bottom_up",
                "probe_fixture":"first_room_dash_trails_v1", "native_probe_checks":"1"}
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise ValueError("Dash probe receipt lacks its exact FBO/orientation/preservation contract")
    if not re.fullmatch(r'[0-9a-f]{64}',metadata.get('probe_fixture_sha256','')):
        raise ValueError('Dash export lacks a pinned fixture hash')
    swatches = {"swatch_single":(454,454,128), "swatch_inner_union":(462,454,192),
                "swatch_opaque":(486,454,255), "swatch_orientation":(486,470,64)}
    for key, (x, top, value) in swatches.items():
        field = metadata.get(key, "")
        if not re.fullmatch(r"0|[1-9][0-9]{0,2}", field) or abs(int(field) - value) > 1:
            raise ValueError("Dash probe receipt has an invalid swatch: " + key)
        if int(field) != attachment_pixel(raw, x, top)[3]:
            raise ValueError("Dash probe receipt swatch differs from actual attachment: " + key)
    snapshots = metadata.get("trail_snapshots", "").split(";")
    if len(snapshots) != 4 or snapshots[-1]:
        raise ValueError("Dash capture requires three ordered committed trail snapshots")
    observed = []
    for index, row in enumerate(snapshots[:-1]):
        fields = row.split(",")
        if len(fields) != 8 or fields[0] != str(index):
            raise ValueError("Dash capture snapshot slots/order differ from the first three trails")
        percent, x, y = map(float, fields[1:4])
        if not all(math.isfinite(v) for v in (percent, x, y)) or not 0 <= percent < 1:
            raise ValueError("Dash capture snapshot has invalid position/fade")
        tint = fields[4:]
        amount = .75 * (1 - percent) ** 3
        if any(not re.fullmatch(r"0|[1-9][0-9]{0,2}", value) or
               abs(int(value) - int(source * amount)) > 1
               for value, source in zip(tint, (68, 183, 255, 255), strict=True)):
            raise ValueError("Dash capture snapshot tint is not the truncated original fade")
        if observed and percent > observed[-1]["percent"]:
            raise ValueError("Dash capture snapshots are not in creation order")
        count = 0
        for top in range(64):
            for column in range(index * 64, (index + 1) * 64):
                rgba = attachment_pixel(raw, column, top)
                if any(abs(channel - rgba[3]) > 1 for channel in rgba[:3]):
                    raise ValueError("Captured trail attachment is not the completed alpha mask")
                count += rgba[3] > 0
        if not count:
            raise ValueError("Dash probe attachment lacks a captured trail tile")
        observed.append({"slot":index, "percent":percent, "position":[x, y],
                         "tint_rgba":list(map(int, tint)), "nonzero_alpha_pixels":count})
    for top in range(448, 512):
        for x in range(448, 512):
            alpha = 0
            if 452 <= top < 468 and 452 <= x < 476:
                alpha = 192 if 460 <= x < 468 else 128
            elif 452 <= top < 460 and 484 <= x < 500:
                alpha = 255
            elif 468 <= top < 472 and 484 <= x < 488:
                alpha = 64
            if any(abs(channel - alpha) > 1 for channel in attachment_pixel(raw, x, top)):
                raise ValueError(f"Dash raw FBO swatch/channel/orientation failed at {x},{top}")
    if not any(pixels):
        raise ValueError("Dash probe frame lacks actual room RGB")
    return {"raw_swatch_pixels_checked":4096, "raw_rows":"GL_bottom_up", "snapshots":observed,
            "captured_tile_preservation":"native_before_after_assertion_only_not_independent_host_proof",
            "state_restoration":"native_fail_fatal_checks_only_not_independent_host_proof",
            "frame_compositing":"pending_parent_visual_review", "physical_proof":False,
            "freshness":"not_established_by_offline_collection", "runtime_completion":False}


def dash_probe_intent(root=REPO_ROOT):
    return {"id": FIXTURE_ID, "samples": 360, "exit_frame": 359, "source": FIXTURE_SOURCE,
            "sha256": file_identity(root / FIXTURE_SOURCE)["sha256"]}


def verify_dash_probe_intent(provenance, enabled, root=REPO_ROOT):
    if provenance.get("guest_dash_probe") is not None and provenance["guest_dash_probe"] != FIXTURE_ID:
        raise ValueError("Dash probe fixture ID must be the declared ID or null")
    if provenance.get("guest_dash_probe") and (provenance.get("guest_replay") or provenance.get("guest_automatic")):
        raise ValueError("Dash probe, automatic and legacy guest modes are exclusive")
    if bool(provenance.get("guest_dash_probe")) != enabled:
        raise ValueError("Dash probe intent differs from requested build mode")
    if enabled:
        if provenance.get("guest_dash_probe_fixture") != dash_probe_intent(root):
            raise ValueError("Dash probe fixture identity differs from this source")
        if provenance.get("render_style") != "animated_player_partial" or not provenance.get("player"):
            raise ValueError("Dash probe requires animated Player assets")
    elif provenance.get("guest_dash_probe_fixture") is not None:
        raise ValueError("Disabled Dash probe mode cannot carry a probe fixture pin")
