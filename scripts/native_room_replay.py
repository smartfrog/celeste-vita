"""Identity and observed completion contract for one explicit guest-only diagnostic."""

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from native_room_revision import REPO_ROOT, source_state

FIXTURE_ID = "first_room_climb_dash_v1"
FIXTURE_FRAMES = 250
FIXTURE_SOURCE = "src/vita/guest_replay.hpp"
AUTOMATIC_ID = "first_room_auto_death_v2"
AUTOMATIC_SOURCE = "src/vita/guest_automatic_replay.hpp"
AUTOMATIC_SOURCE_TRACE = "b2123d17ef324e44535f20f75963ea9a177ea38217c8255162a2c97c45c04260"
DASH_PROBE_ID = "first_room_dash_trails_v1"
DASH_PROBE_SOURCE = "src/vita/guest_dash_probe.hpp"
HARNESS_FILES = ("scripts/smoke_native_room.py", "scripts/vita_room_emulator.py",
                 "scripts/native_room_replay.py", "scripts/native_room_revision.py")
AUTOMATIC_HARNESS_FILES = HARNESS_FILES + ("scripts/feedback_native_room.py", "scripts/native_room_feedback.py")


def dash_probe_intent(root=REPO_ROOT):
    return {"id":DASH_PROBE_ID, "samples":360, "exit_frame":359, "source":DASH_PROBE_SOURCE,
            "sha256":hashlib.sha256((Path(root) / DASH_PROBE_SOURCE).read_bytes()).hexdigest()}


def dash_probe_inputs():
    return [dict(x=0, y=-int(40 <= frame < 60), jump=0, dash=int(frame == 40), reset=0, exit=int(frame == 359))
            for frame in range(360)]


def replay_intent(root=REPO_ROOT):
    return {"id":FIXTURE_ID,"frames":FIXTURE_FRAMES,"source":FIXTURE_SOURCE,
            "sha256":hashlib.sha256((Path(root) / FIXTURE_SOURCE).read_bytes()).hexdigest()}


def harness_fingerprint(root=REPO_ROOT, automatic=False, dash_probe=False):
    digest = hashlib.sha256()
    files = AUTOMATIC_HARNESS_FILES if automatic or dash_probe else HARNESS_FILES
    files += ("scripts/native_room_dash_runtime.py", "scripts/native_room_dash_probe.py", "scripts/convert_native_frame.py")
    for name in files:
        digest.update(name.encode("utf-8") + b"\0")
        digest.update(hashlib.sha256((Path(root) / name).read_bytes()).digest())
    return digest.hexdigest()


def verify_replay_source(provenance, source_checkout, host_root=REPO_ROOT):
    source_checkout = Path(source_checkout).resolve()
    if not source_checkout.is_dir():
        raise FileNotFoundError(f"Missing replay source checkout: {source_checkout}")
    revision, changes = source_state(source_checkout)
    if revision != provenance.get("revision") or provenance.get("tracked_changes"):
        raise ValueError("Replay source checkout is not at the exact VPK source revision")
    if changes:
        raise ValueError("Replay source checkout is not clean: " + "; ".join(changes))
    verify_replay_intent(provenance, True, source_checkout)
    host_revision, host_changes = source_state(host_root)
    return {"source_checkout":str(source_checkout),"source_revision":revision,"source_clean":True,
            "fixture":replay_intent(source_checkout),
            "host_harness":{"root":str(Path(host_root).resolve()),"revision":host_revision,
                            "changes":host_changes,"fingerprint_sha256":harness_fingerprint(host_root)}}


def verify_replay_intent(provenance, enabled, root=REPO_ROOT):
    intent = provenance.get("guest_replay")
    if bool(intent) != enabled:
        raise ValueError("Guest replay intent differs from requested execution mode")
    if enabled and intent != replay_intent(root):
        raise ValueError("Guest replay fixture identity differs from this source")


def completion_receipt(revision, automatic=False):
    fixture = AUTOMATIC_ID if automatic else FIXTURE_ID
    return f"complete revision={revision} input_source=scripted_guest_controls fixture={fixture} status=0\n"


def verify_replay_guest(text, revision, intent, root=REPO_ROOT):
    from smoke_native_room import verify_guest, verify_climb_guest
    verify_replay_intent({"guest_replay":intent},True,root)
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


def verify_automatic_intent(provenance, enabled):
    if provenance.get("guest_automatic") != (AUTOMATIC_ID if enabled else None):
        raise ValueError("Guest automatic fixture intent differs from requested execution mode")
    if enabled and provenance.get("guest_replay"):
        raise ValueError("Guest automatic and legacy replay are mutually exclusive")
    if not enabled and provenance.get("guest_automatic_fixture") is not None:
        raise ValueError("Disabled guest automatic mode cannot carry an automatic fixture pin")


def automatic_inputs():
    # Input-only runs from the accepted source trace AUTOMATIC_SOURCE_TRACE; no native outcomes.
    runs = ((36, 0, 0), (37, 1, 1), (64, 1, 0), (68, 0, 0), (199, 0, 1),
            (200, 0, 0), (201, 1, 1), (228, 1, 0), (232, 0, 0), (235, 0, 1),
            (362, 0, 0), (363, 0, 1), (364, 1, 1))
    inputs = []
    for end, x, jump in runs:
        inputs.extend(dict(x=x, y=0, jump=jump, reset=0, exit=0) for _ in range(end-len(inputs)))
    return inputs + [dict(x=0, y=0, jump=0, reset=0, exit=1)]


def automatic_fields(line, prefix, required):
    fields = {}
    for token in line[len(prefix):].split():
        key, separator, value = token.partition("=")
        if not separator or key in fields or not value:
            raise ValueError("Malformed or duplicate automatic field")
        fields[key] = value
    if not set(required) <= fields.keys() or fields.get("fixture") != AUTOMATIC_ID:
        raise ValueError("Missing automatic fields or wrong fixture")
    for key in required - {"fixture"}:
        if not re.fullmatch(r"0|-?[1-9][0-9]*", fields[key]):
            raise ValueError("Invalid automatic integer: " + key)
        fields[key] = int(fields[key])
    return fields


def verify_automatic_guest(text, revision, intent, fixture):
    verify_automatic_intent({"guest_automatic": intent}, True)
    if fixture.get("id") != intent or fixture.get("samples") != 365 or fixture.get("exit_frame") != 364 or fixture.get("source") != AUTOMATIC_SOURCE or not re.fullmatch(r"[0-9a-f]{64}", fixture.get("sha256", "")):
        raise ValueError("Automatic fixture receipt lacks its pinned native header identity")
    marker = f"guest automatic fixture={AUTOMATIC_ID} fixture_sha256={fixture['sha256']} input_source=scripted_guest_controls samples=365 exit_frame=364 physical_controller_verified=false host_input_injected=false"
    if text.splitlines().count(marker) != 1:
        raise ValueError("Guest lacks exact automatic fixture/input-source receipt")
    if not text.endswith("\n") or "FATAL" in text or "manual reset frame=" in text or "guest replay" in text or re.search(r"\breset=1\b|\bTriangle=(true|1)\b", text):
        raise ValueError("Truncated, failed, manual or mislabeled automatic guest log")
    lines = text.splitlines()
    for line in lines:
        if line.startswith("input ") and any(int(buttons, 16) & 0x1000 for buttons in re.findall(r"\bbuttons=([0-9a-fA-F]+)\b", line)):
            raise ValueError("Automatic guest sampled forbidden Triangle input")
    boot = [line for line in lines if "DIAGNOSTIC boot revision=" in line]
    if len(boot) != 1 or f"DIAGNOSTIC boot revision={revision} fixed_step=1/60" not in boot[0]:
        raise ValueError("Automatic guest boot revision differs from package")
    for marker in ("assets ready", "frame ready"):
        if not any(line.startswith(marker) for line in lines):
            raise ValueError("Automatic guest lacks startup marker: " + marker)
    sample_keys = {"fixture", "frame", "x", "y", "jump", "reset", "exit", "state", "dead", "reloads", "room_deaths", "save_deaths", "jumps"}
    end_keys = {"fixture", "samples", "exit_frame", "reloads", "room_deaths", "save_deaths", "jumps", "full_completion"}
    samples, end = [], None
    last_sample_offset = -1
    for index, line in enumerate(lines):
        if line.startswith("guest_automatic "):
            if end is not None:
                raise ValueError("Automatic sample follows completion")
            samples.append(automatic_fields(line, "guest_automatic ", sample_keys))
            last_sample_offset = index
        elif line.startswith("guest_automatic_complete "):
            if end is not None:
                raise ValueError("Duplicate automatic completion")
            end = automatic_fields(line, "guest_automatic_complete ", end_keys)
        elif line.startswith("guest_automatic"):
            raise ValueError("Malformed automatic record")
    expected = automatic_inputs()
    if len(samples) != len(expected) or end is None:
        raise ValueError("Incomplete automatic samples/completion")
    previous = dict(state=14, dead=0, reloads=0, room_deaths=0, save_deaths=0, jumps=0)
    deaths, reloads, jumps, normals = [], [], [], []
    normal_seen = False
    cycle_jumps = 0
    counters = ("reloads", "room_deaths", "save_deaths", "jumps")
    for frame, (sample, controls) in enumerate(zip(samples, expected, strict=True)):
        if sample["frame"] != frame or any(sample[key] != value for key, value in controls.items()):
            raise ValueError("Automatic input/order differs from accepted source sequence")
        if sample["state"] not in (0, 14) or sample["dead"] not in (0, 1):
            raise ValueError("Unexpected automatic state/dead value")
        delta = {key: sample[key]-previous[key] for key in counters}
        if any(value not in (0, 1) for value in delta.values()):
            raise ValueError("Automatic counters are not monotonic single events")
        died = sample["dead"] == 1 and previous["dead"] == 0
        if delta["room_deaths"] != int(died) or delta["save_deaths"] != int(died):
            raise ValueError("Automatic death counters disagree with actual death rising edges")
        if died:
            if not normal_seen or cycle_jumps != 1 or sample["reloads"] != len(deaths):
                raise ValueError("Automatic death lacks the preceding Normal/actual Jump cycle")
            deaths.append(frame)
        if delta["reloads"]:
            if not previous["dead"] or sample["dead"] or sample["state"] != 14 or len(deaths) != len(reloads)+1:
                raise ValueError("Automatic reload lacks dead-to-Respawn14 reconstruction")
            reloads.append(frame)
            normal_seen, cycle_jumps = False, 0
        elif previous["dead"] and not sample["dead"]:
            raise ValueError("Automatic death cleared without a reload")
        if previous["state"] == 14 and sample["state"] == 0:
            if normal_seen or sample["dead"]:
                raise ValueError("Unexpected automatic Respawn14-to-Normal transition")
            normals.append(frame)
            normal_seen = True
        elif previous["state"] == 0 and sample["state"] == 14 and not delta["reloads"]:
            raise ValueError("Respawn14 without automatic reload")
        if delta["jumps"]:
            if not normal_seen or sample["dead"] or sample["state"] != 0 or not sample["jump"] or cycle_jumps:
                raise ValueError("Automatic Jump counter lacks a live input-driven Normal action")
            jumps.append(frame)
            cycle_jumps += 1
        if frame == 364:
            observed = sample.keys() - controls.keys() - {"frame", "fixture"}
            if observed != previous.keys() - controls.keys() - {"frame", "fixture"} or any(sample[key] != previous[key] for key in observed):
                raise ValueError("Automatic exit record stepped or changed the final session")
        previous = sample
    if samples[0]["state"] != 14 or samples[0]["dead"] or len(deaths) != 2 or len(reloads) != 2 or len(jumps) != 3 or len(normals) != 3 or previous["dead"] or previous["state"] != 0:
        raise ValueError("Automatic samples do not complete two production lifecycle cycles")
    expected_end = dict(fixture=AUTOMATIC_ID, samples=365, exit_frame=364, reloads=2, room_deaths=2, save_deaths=2, jumps=3, full_completion=1)
    if any(end[key] != value for key, value in expected_end.items()):
        raise ValueError("Automatic completion disagrees with recomputed samples")
    clean = [i for i, line in enumerate(lines) if line.startswith("clean exit ")]
    clean_state = dict(frame=364, dead=0, resets=0, state=0)
    if len(clean) != 1 or clean[0] < last_sample_offset or any(re.findall(r"\b"+key+r"=(\d+)\b", lines[clean[0]]) != [str(value)] for key, value in clean_state.items()):
        raise ValueError("Automatic guest lacks its final live clean exit")
    return {"markers":["guest_automatic_complete", "clean exit"], "samples":365, "exit_frame":364,
            "deaths":len(deaths), "reloads":len(reloads), "jumps":len(jumps), "death_frames":deaths,
            "reload_frames":reloads, "jump_frames":jumps, "respawn_normal_frames":normals,
            "input_source_trace_sha256":AUTOMATIC_SOURCE_TRACE}


def verify_automatic_source(provenance, vpk, source_root, build, staging, expected_source_state=None):
    source_root = Path(source_root).resolve()
    verify_automatic_intent(provenance, True)
    if provenance.get("render_style") != "animated_player_partial" or not provenance.get("player", {}).get("death_animation_extension"):
        raise ValueError("Automatic package requires the production animated death lifecycle profile")
    package = verify_native_package(provenance,vpk,source_root,build,staging,expected_source_state)
    revision, changes = source_state()
    return {"source_checkout":str(source_root), "source":package["source_before"],
            "source_clean":not package["exact_wip"], "package":package,
            "fixture":{"id":AUTOMATIC_ID, "source":AUTOMATIC_SOURCE,
                       "sha256":hashlib.sha256((source_root / AUTOMATIC_SOURCE).read_bytes()).hexdigest()},
            "host_harness":{"root":str(REPO_ROOT), "revision":revision, "changes":changes,
                            "fingerprint_sha256":harness_fingerprint(automatic=True)}}


def verify_dash_probe_source(provenance, vpk, source_root, build, staging, expected_source_state=None):
    from native_room_dash_runtime import verify_dash_probe_intent
    source_root = Path(source_root).resolve()
    verify_dash_probe_intent(provenance,True,source_root)
    if not provenance.get('visuals',{}).get('spike_textures') or not provenance.get('decals'):
        raise ValueError('Dash package requires the animated/textured/spike/decal profile')
    package = verify_native_package(provenance,vpk,source_root,build,staging,expected_source_state)
    if package['build_binding'].get('capture_policy')!='dash_trails':
        raise ValueError('Dash package lacks the exact resident dash_trails capture policy')
    revision,changes = source_state()
    return dict(source_checkout=str(source_root),source=package['source_before'],source_clean=not package['exact_wip'],
                package=package,fixture=dash_probe_intent(source_root),
                host_harness=dict(root=str(REPO_ROOT),revision=revision,changes=changes,
                                  fingerprint_sha256=harness_fingerprint(dash_probe=True)))


def verify_native_package(provenance, vpk, source_root, build, staging, expected_source_state):
    command = [sys.executable, "-B", str(source_root / "scripts/verify_native_room_vpk.py"),
               "--vpk", str(vpk), "--build", str(build), "--staging", str(staging)]
    if expected_source_state is not None:
        command += ["--expected-source-state", str(expected_source_state)]
    try:
        result = subprocess.run(command, cwd=source_root, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as error:
        raise ValueError("Native authoritative VPK verification failed: " + (error.stderr or error.stdout or str(error))) from error
    package = json.loads(result.stdout)
    return validate_native_package(provenance,vpk,package,expected_source_state)


def validate_native_package(provenance, vpk, package, expected_source_state):
    binding = package.get("build_binding")
    if package["exact_wip"] and expected_source_state is None:
        raise ValueError("Exact WIP verification requires explicit expected-source-state opt-in")
    if not binding or not binding.get("self_matches_rebuilt_chain") or package["staging"] != provenance or package["vpk_sha256"] != hashlib.sha256(Path(vpk).read_bytes()).hexdigest():
        raise ValueError("Native VPK lacks exact source/resident binary/asset binding")
    if package["source_before"] != package["source_after"] or binding["source"] != package["source_before"]:
        raise ValueError("Native VPK source identity drifted")
    return package


def native_source_identity(source_root, expected_source_state=None):
    program = ("import json,sys; from pathlib import Path; from native_room_revision import validate_source_state; "
               "expected=json.loads(Path(sys.argv[1]).read_text()) if sys.argv[1] else None; "
               "print(json.dumps(validate_source_state(expected)))")
    try:
        result = subprocess.run([sys.executable, "-B", "-c", program,
                                 str(expected_source_state) if expected_source_state else ""],
                                cwd=Path(source_root) / "scripts", check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as error:
        raise ValueError("Native complete source verification failed: " + (error.stderr or error.stdout or str(error))) from error
    return {"identity":json.loads(result.stdout),
            "expected_manifest_sha256":hashlib.sha256(Path(expected_source_state).read_bytes()).hexdigest() if expected_source_state else None,
            "host_harness_sha256":harness_fingerprint(automatic=True)}
