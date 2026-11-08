#!/usr/bin/env python3
"""Build, package, run and preserve feedback from OUR native renderer; no OS capture."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from native_room_feedback import new_feedback, save_feedback
from native_room_revision import REPO_ROOT, source_state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
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
            result = subprocess.run(arguments,cwd=REPO_ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=600)
        feedback = json.loads(feedback_path.read_text())
        feedback["commands"].append({"label":label,"argv":arguments,"log":str(log),"exit_code":result.returncode,
                                      "elapsed_seconds":time.monotonic()-started})
        save_feedback(feedback_path,feedback)
        if result.returncode:
            raise RuntimeError(f"{label} failed with code {result.returncode}; evidence: {log}")

    try:
        if changes:
            raise ValueError("Current source/config is not clean: "+"; ".join(changes))
        run("stage",["python3","-B","scripts/stage_native_room.py","--output",str(staging)])
        run("configure",["/usr/bin/cmake","-S",".","-B",str(build),"-DCMAKE_TOOLCHAIN_FILE="+sdk+"/share/vita.toolchain.cmake",
                         "-DCMAKE_BUILD_TYPE=Release","-DBUILD_TESTING=OFF","-DCELESTE_VITA=ON",
                         "-DCELESTE_VITAGL_LIBRARY="+archive,"-DCELESTE_ROOM_STAGING="+str(staging)])
        run("build",["/usr/bin/cmake","--build",str(build),"--verbose","-j2"])
        feedback["stages"]["build"] = True
        save_feedback(feedback_path,feedback)
        run("package",["python3","-B","scripts/verify_native_room_vpk.py","--vpk",str(vpk),"--build",str(build / "src/vita"),"--staging",str(staging)])
        package = json.loads((output / "package.log").read_text())
        feedback["package"] = package
        feedback["vpk"]["sha256"] = package["vpk_sha256"]
        feedback["stages"]["package_verified"] = True
        save_feedback(feedback_path,feedback)
        run("runtime",["python3","-B","scripts/smoke_native_room.py","--state",str(output / "vita3k-state"),
                       "--output",str(output / "runtime"),"--vpk",str(vpk),"--feedback",str(feedback_path)])
    except Exception as error:
        feedback = json.loads(feedback_path.read_text())
        feedback["errors"].append({"stage":"toolchain","type":type(error).__name__,"message":str(error)})
        save_feedback(feedback_path,feedback)
        raise
    finally:
        final_revision, changes = source_state(REPO_ROOT)
        feedback = json.loads(feedback_path.read_text())
        feedback["source_after"] = {"revision":final_revision,"changes":changes}
        save_feedback(feedback_path,feedback)
        print("FEEDBACK_JSON "+str(feedback_path),flush=True)
        if final_revision != revision or changes != initial_changes:
            raise RuntimeError("Source/config changed during feedback command")


if __name__ == "__main__":
    main()
