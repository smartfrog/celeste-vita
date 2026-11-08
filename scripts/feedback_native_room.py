#!/usr/bin/env python3
"""Build, package, run and preserve feedback from OUR native renderer; no OS capture."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from native_room_feedback import new_feedback, save_feedback
from native_room_revision import REPO_ROOT, source_state


def record_failure(feedback, stage, error):
    feedback["errors"].append({"stage":stage,"type":type(error).__name__,"message":str(error)})
    feedback["stages"]["full_completion"] = False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--frame-only",action="store_true",help="Stop after closed native frame feedback; do not inject input")
    parser.add_argument("--guest-replay",action="store_true",help="Unattended bounded guest-controls smoke; never open X11, inject host input, or request desktop permissions")
    parser.add_argument("--textured",action="store_true",help="Explicit partial static source-textured presentation, not debug hitboxes")
    parser.add_argument("--spike-art",action="store_true",help="Use the nineteen source spike images instead of red diagnostic markers")
    parser.add_argument("--visual-dir",type=Path,help="Verified private six- or eight-texture preparation required for --textured")
    parser.add_argument("--player-dir",type=Path,help="Verified private animated player and simulated hair; requires --textured")
    capture = parser.add_mutually_exclusive_group()
    capture.add_argument("--after-wall-jump",action="store_true",help="Capture once after a real input-driven WallJump, then retain the normal Dash/death/reset smoke")
    capture.add_argument("--after-climb",action="store_true",help="Capture once during real airborne drained Climb, then retain the normal Dash/death/reset smoke")
    args = parser.parse_args()
    if args.textured != (args.visual_dir is not None):
        parser.error("Use --textured and --visual-dir together")
    if args.player_dir is not None and not args.textured:
        parser.error("Animated player requires --textured and --visual-dir")
    if args.spike_art and not args.textured:
        parser.error("Source spike art requires --textured and --visual-dir")
    if args.frame_only and (args.after_wall_jump or args.after_climb):
        parser.error("Post-WallJump capture requires input; it cannot use --frame-only")
    if args.guest_replay and (args.frame_only or not args.after_climb):
        parser.error("Guest replay requires --after-climb and cannot use --frame-only")
    output = args.output.resolve()
    if not output.is_relative_to(REPO_ROOT / ".audit/native-room-vita"):
        parser.error("Feedback output must remain under private diagnostic evidence")
    output.mkdir(parents=True,exist_ok=False)
    revision, changes = source_state(REPO_ROOT)
    initial_changes = list(changes)
    build, staging = output / "vita-app", output / "staging"
    vpk = build / "src/vita/celeste_native_room.vpk"
    feedback_path = output / "feedback.json"
    feedback = new_feedback(revision,vpk)
    feedback["requested_scope"] = "guest_replay_smoke" if args.guest_replay else "native_frame_only" if args.frame_only else "full_runtime_smoke"
    if args.guest_replay:
        feedback.update(input_source="scripted_guest_controls",physical_controller_verified=False,
                        host_input_injected=False,portal_requests=0)
    feedback["capture_policy"] = "climb" if args.after_climb else "wall_jump" if args.after_wall_jump else "spawn"
    feedback["render_style"] = "animated_player_partial" if args.player_dir else "textured_partial" if args.textured else "debug"
    feedback["spike_art"] = bool(args.spike_art)
    feedback["commands"] = []
    save_feedback(feedback_path,feedback)
    sdk = "/home/fred/cloudpunk-vita/tools/vitasdk"
    archive = "/home/fred/cloudpunk-vita/tools/vita3k/vitagl-source/libvitaGL.a"
    env = os.environ | {"VITASDK":sdk,"PATH":sdk+"/bin:"+os.environ["PATH"],"LC_ALL":"C"}

    def run(label, arguments):
        nonlocal feedback
        started = time.monotonic()
        log = output / (label+".log")
        with log.open("xb") as stream:
            result = subprocess.run(arguments,cwd=REPO_ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,
                                    timeout=None if label == "runtime" else 600)
        feedback = json.loads(feedback_path.read_text())
        feedback["commands"].append({"label":label,"argv":arguments,"log":str(log),"exit_code":result.returncode,
                                      "elapsed_seconds":time.monotonic()-started})
        save_feedback(feedback_path,feedback)
        if result.returncode:
            raise RuntimeError(f"{label} failed with code {result.returncode}; evidence: {log}")

    try:
        if changes:
            raise ValueError("Current source/config is not clean: "+"; ".join(changes))
        run("stage",[sys.executable,"-B","scripts/stage_native_room.py","--output",str(staging)]+
             (["--visual-dir",str(args.visual_dir.resolve())] if args.textured else [])+
            (["--player-dir",str(args.player_dir.resolve())] if args.player_dir else [])+
            (["--guest-replay"] if args.guest_replay else []))
        run("configure",["/usr/bin/cmake","-S",".","-B",str(build),"-DCMAKE_TOOLCHAIN_FILE="+sdk+"/share/vita.toolchain.cmake",
                         "-DCMAKE_BUILD_TYPE=Release","-DBUILD_TESTING=OFF","-DCELESTE_VITA=ON",
                         "-DCELESTE_VITAGL_LIBRARY="+archive,"-DCELESTE_ROOM_STAGING="+str(staging),
                         "-DCELESTE_ROOM_CAPTURE_AFTER_WALL_JUMP="+("ON" if args.after_wall_jump else "OFF"),
                          "-DCELESTE_ROOM_CAPTURE_AFTER_CLIMB="+("ON" if args.after_climb else "OFF"),
                          "-DCELESTE_ROOM_GUEST_REPLAY="+("ON" if args.guest_replay else "OFF"),
                         "-DCELESTE_ROOM_TEXTURED="+("ON" if args.textured else "OFF"),
                         "-DCELESTE_ROOM_SPIKE_ART="+("ON" if args.spike_art else "OFF"),
                         "-DCELESTE_ROOM_ANIMATED_PLAYER="+("ON" if args.player_dir else "OFF")])
        run("build",["/usr/bin/cmake","--build",str(build),"--verbose","-j2"])
        feedback["stages"]["build"] = True
        save_feedback(feedback_path,feedback)
        run("package",[sys.executable,"-B","scripts/verify_native_room_vpk.py","--vpk",str(vpk),"--build",str(build / "src/vita"),"--staging",str(staging)])
        package = json.loads((output / "package.log").read_text())
        feedback["package"] = package
        feedback["vpk"]["sha256"] = package["vpk_sha256"]
        feedback["stages"]["package_verified"] = True
        save_feedback(feedback_path,feedback)
        run("runtime",[sys.executable,"-B","scripts/smoke_native_room.py","--state",str(output / "vita3k-state"),
                       "--output",str(output / "runtime"),"--vpk",str(vpk),"--feedback",str(feedback_path)]+
                       (["--frame-only"] if args.frame_only else [])+(["--after-wall-jump"] if args.after_wall_jump else [])+
                        (["--after-climb"] if args.after_climb else [])+(["--guest-replay"] if args.guest_replay else []))
    except Exception as error:
        feedback = json.loads(feedback_path.read_text())
        record_failure(feedback,"toolchain",error)
        save_feedback(feedback_path,feedback)
        raise
    finally:
        feedback = json.loads(feedback_path.read_text())
        source_failure = source_cause = None
        try:
            final_revision, changes = source_state(REPO_ROOT)
            feedback["source_after"] = {"revision":final_revision,"changes":changes}
            if final_revision != revision or changes != initial_changes:
                source_failure = RuntimeError("Source/config changed during feedback command")
        except Exception as error:
            feedback["source_after"] = {"revision":None,"changes":None,
                                        "error":{"type":type(error).__name__,"message":str(error)}}
            source_failure = RuntimeError("Final source/Git state could not be verified: "+str(error))
            source_cause = error
        if source_failure:
            record_failure(feedback,"source_after",source_failure)
        save_feedback(feedback_path,feedback)
        print("FEEDBACK_JSON "+str(feedback_path),flush=True)
        if source_failure:
            if source_cause:
                raise source_failure from source_cause
            raise source_failure


if __name__ == "__main__":
    main()
