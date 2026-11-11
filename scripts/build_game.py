#!/usr/bin/env python3
"""Build and verify a private first-room VPK; never install or launch it."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from native_room_revision import REPO_ROOT, validate_source_state, source_identity
from prepare_game import preparation_output


def toolchain_environment(vitasdk, vitagl):
    vitasdk = vitasdk.resolve()
    if not (vitasdk / "share/vita.toolchain.cmake").is_file():
        raise ValueError("Supply a valid VitaSDK via --vitasdk or VITASDK")
    if not vitagl.is_file():
        raise ValueError("Supply the compatible no-splash vitaGL archive via --vitagl-library")
    return os.environ | {"VITASDK": str(vitasdk), "PATH": str(vitasdk / "bin") + os.pathsep + os.environ.get("PATH", "")}


def vitagl_include_directory(vitasdk, vitagl, explicit=None):
    candidates = [explicit] if explicit is not None else [vitagl.parent / "source", vitasdk / "arm-vita-eabi/include"]
    for directory in candidates:
        if (directory / "vitaGL.h").is_file():
            return directory.resolve()
    raise ValueError("Matching vitaGL.h missing; supply --vitagl-include /path/to/vitaGL/source")


def read_preparation(path, root=REPO_ROOT):
    record = json.loads(path.read_text())
    keys = ("archive", "mask_dir", "hazard_dir", "visual_dir", "player_dir", "decal_dir")
    if record.get("schema") != 1 or record.get("status") != "prepared" or any(key not in record for key in keys):
        raise ValueError("A completed preparation.json from prepare_game.py is required")
    private = root.resolve() / ".audit"
    for value in [path, *(Path(record[key]) for key in keys)]:
        if not value.resolve().is_relative_to(private):
            raise ValueError("Preparation inputs must remain private beneath this checkout's .audit")
    return record


def build(prepared, output, vitasdk, vitagl, jobs=2, allow_dirty=False, vitagl_include=None):
    if jobs < 1:
        raise ValueError("Build jobs must be positive")
    record = read_preparation(prepared)
    environment = toolchain_environment(vitasdk, vitagl)
    include = vitagl_include_directory(vitasdk, vitagl, vitagl_include)
    before = source_identity() if allow_dirty else validate_source_state()
    output = preparation_output(output)
    output.mkdir(parents=True)
    temporary = output / "tmp"
    temporary.mkdir()
    environment["TMPDIR"] = str(temporary)
    staging, native_build = output / "staging", output / "build"
    expected_args = []
    expected_cmake = []
    if allow_dirty:
        expected = output / "expected-source-state.json"
        expected.write_text(json.dumps(before, indent=2) + "\n")
        expected_args = ["--expected-source-state", str(expected)]
        expected_cmake = ["-DCELESTE_EXPECTED_SOURCE_STATE=" + str(expected)]
    report = {"schema": 1, "status": "building", "source": before, "commands": [], "runtime_tested": False}
    report_path = output / "build.json"

    def save():
        report_path.write_text(json.dumps(report, indent=2) + "\n")

    def run(label, command):
        print(label, flush=True)
        log = output / (label + ".log")
        with log.open("x") as stream:
            result = subprocess.run(list(map(str, command)), cwd=REPO_ROOT, env=environment,
                                    stdout=stream, stderr=subprocess.STDOUT)
        report["commands"].append({"label": label, "argv": list(map(str, command)), "exit_code": result.returncode, "log": str(log)})
        save()
        if result.returncode:
            raise RuntimeError(f"{label} failed ({result.returncode}); see {log}")

    def script(name):
        return [sys.executable, "-B", REPO_ROOT / "scripts" / name]

    save()
    try:
        run("stage", [*script("stage_native_room.py"), "--archive", record["archive"], "--output", staging,
                      *[part for key in ("mask_dir", "hazard_dir", "visual_dir", "player_dir", "decal_dir")
                        for part in ("--" + key.replace("_", "-"), record[key])], *expected_args])
        run("configure", ["cmake", "-G", "Unix Makefiles", "-S", REPO_ROOT, "-B", native_build,
                          "-DCMAKE_TOOLCHAIN_FILE=" + str(vitasdk.resolve() / "share/vita.toolchain.cmake"),
                          "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_TESTING=OFF", "-DCELESTE_VITA=ON",
                          "-DCELESTE_VITAGL_LIBRARY=" + str(vitagl.resolve()), "-DCELESTE_ROOM_STAGING=" + str(staging),
                          "-DCELESTE_VITAGL_INCLUDE_DIR=" + str(include),
                          "-DCELESTE_ROOM_TEXTURED=ON", "-DCELESTE_ROOM_SPIKE_ART=ON",
                          "-DCELESTE_ROOM_ANIMATED_PLAYER=ON", "-DCELESTE_ROOM_DECALS=ON", *expected_cmake])
        run("compile", ["cmake", "--build", native_build, "--parallel", str(jobs)])
        vpk = native_build / "src/vita/celeste_native_room.vpk"
        run("verify", [*script("verify_native_room_vpk.py"), "--vpk", vpk,
                       "--build", native_build / "src/vita", "--staging", staging, *expected_args])
        validate_source_state(before)
        report.update(status="verified", vpk=str(vpk), verification=str(output / "verify.log"))
        save()
    except Exception as error:
        report.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
        save()
        raise
    print("PRIVATE_VPK " + str(vpk), flush=True)
    return vpk


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, default=REPO_ROOT / ".audit/prepared-game/preparation.json")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / ".audit/vita-game", help="Fresh private build directory")
    parser.add_argument("--vitasdk", type=Path, default=Path(os.environ["VITASDK"]) if os.environ.get("VITASDK") else None)
    parser.add_argument("--vitagl-library", type=Path, required=True, help="Compatible no-splash libvitaGL.a")
    parser.add_argument("--vitagl-include", type=Path, help="Matching vitaGL.h directory; defaults to the library's source checkout or SDK include directory")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--allow-dirty", action="store_true", help="Explicitly bind exact uncommitted source bytes; never label them a clean commit")
    args = parser.parse_args()
    if args.vitasdk is None:
        parser.error("Supply --vitasdk or set VITASDK")
    build(args.prepared, args.output, args.vitasdk, args.vitagl_library, args.jobs, args.allow_dirty, args.vitagl_include)
