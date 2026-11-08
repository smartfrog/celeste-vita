"""Identity and observed completion contract for one explicit guest-only diagnostic."""

import hashlib
import re
from native_room_revision import REPO_ROOT

FIXTURE_ID = "first_room_climb_dash_v1"
FIXTURE_FRAMES = 250
FIXTURE_SOURCE = "src/vita/guest_replay.hpp"


def replay_intent(root=REPO_ROOT):
    return {"id":FIXTURE_ID,"frames":FIXTURE_FRAMES,"source":FIXTURE_SOURCE,
            "sha256":hashlib.sha256((root / FIXTURE_SOURCE).read_bytes()).hexdigest()}


def verify_replay_intent(provenance, enabled, root=REPO_ROOT):
    intent = provenance.get("guest_replay")
    if bool(intent) != enabled:
        raise ValueError("Guest replay intent differs from requested execution mode")
    if enabled and intent != replay_intent(root):
        raise ValueError("Guest replay fixture identity differs from this source")


def completion_receipt(revision):
    return f"complete revision={revision} input_source=scripted_guest_controls fixture={FIXTURE_ID} status=0\n"


def verify_replay_guest(text, revision, intent):
    from smoke_native_room import verify_guest, verify_climb_guest
    verify_replay_intent({"guest_replay":intent},True)
    marker = f"guest replay fixture={FIXTURE_ID} fixture_sha256={intent['sha256']} input_source=scripted_guest_controls max_frames=250 physical_controller_verified=false host_input_injected=false"
    if marker not in text:
        raise ValueError("Guest lacks exact replay fixture/input-source receipt")
    markers = verify_guest(text,revision,initial_resets=1)
    climb = verify_climb_guest(text)
    required = [r"jump frame=\d+ .* jump_kind=Jump", r"climb entered frame=", r"climb drained frame=",
                r"climb held frame=", r"climb released frame=", r"climb landed frame=", r"manual reset frame=\d+ .* resets=1 ",
                r"jump frame=\d+ .* resets=1 .* jump_kind=Jump", r"freeze transition frame=\d+ from=0 to=1 state=2",
                r"freeze transition frame=\d+ from=1 to=0 state=2", r"dash launch frame=", r"dash transition frame=\d+ from=2 to=0",
                r"death frame=", r"input frame=\d+ .* reset=1 exit=0", r"manual reset frame=\d+ .* resets=2 ",
                r"input frame=249 buttons=00000008 .* reset=0 exit=1", r"clean exit frame=249 ", r"guest replay completed samples=250"]
    offset = 0
    for pattern in required:
        match = re.search(pattern,text[offset:])
        if not match:
            raise ValueError("Guest replay lacks ordered observed event: "+pattern)
        offset += match.end()
    return {"markers":markers,"climb":climb,"samples":250,"exit_frame":249}
