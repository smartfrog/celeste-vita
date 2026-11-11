"""Source and build-mode pins for the separate input-only automatic guest fixture."""

from native_room_revision import REPO_ROOT, file_identity

FIXTURE_ID = "first_room_auto_death_v2"
FIXTURE_SOURCE = "src/vita/guest_automatic_replay.hpp"


def automatic_intent(root=REPO_ROOT):
    return {"id": FIXTURE_ID, "samples": 365, "exit_frame": 364, "source": FIXTURE_SOURCE,
            "sha256": file_identity(root / FIXTURE_SOURCE)["sha256"]}


def verify_automatic_intent(provenance, enabled, root=REPO_ROOT):
    if provenance.get("guest_automatic") is not None and provenance["guest_automatic"] != FIXTURE_ID:
        raise ValueError("Guest automatic fixture ID must be the declared ID or null")
    if provenance.get("guest_automatic") and provenance.get("guest_replay"):
        raise ValueError("Automatic and legacy guest replay modes are exclusive")
    if bool(provenance.get("guest_automatic")) != enabled:
        raise ValueError("Guest automatic intent differs from requested build mode")
    if enabled:
        if provenance["guest_automatic"] != FIXTURE_ID or provenance.get("guest_automatic_fixture") != automatic_intent(root):
            raise ValueError("Guest automatic fixture identity differs from this source")
    elif provenance.get("guest_automatic_fixture") is not None:
        raise ValueError("Disabled guest automatic mode cannot carry an automatic fixture pin")
