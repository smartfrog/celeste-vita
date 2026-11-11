"""Source and build-mode pins for the separate input-only Dash GPU probe."""

from native_room_revision import REPO_ROOT, file_identity

FIXTURE_ID = "first_room_dash_trails_v1"
FIXTURE_SOURCE = "src/vita/guest_dash_probe.hpp"


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
