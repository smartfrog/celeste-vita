"""Run a pinned private source experiment; a completed process is not acceptance."""

import argparse
import json
import os
from pathlib import Path
import resource
import subprocess

from native_room_revision import file_identity, verify_file_identities
from prepare_room_transition_oracle import ROOT, verify_inputs


def validate_controls(value):
    if set(value) != {"schema", "seed", "runs"} or type(value["schema"]) is not int or value["schema"] != 1:
        raise ValueError("Input fixture requires only schema, seed and runs")
    if type(value["seed"]) is not int or not -(2 ** 31) <= value["seed"] < 2 ** 31:
        raise ValueError("Input seed must be int32")
    if not isinstance(value["runs"], list) or not 1 <= len(value["runs"]) <= 128:
        raise ValueError("Input run count exceeds the bounded profile")
    total = 0
    for run in value["runs"]:
        if set(run) != {"frames", "keys"} or type(run["frames"]) is not int or run["frames"] <= 0:
            raise ValueError("Input runs permit only positive frames and keys")
        keys = run["keys"]
        if not isinstance(keys, list) or any(key not in ("Left", "Right", "Up", "Down", "C", "X", "Z") for key in keys):
            raise ValueError("Only Dpad, Jump, Dash and Climb are legal")
        if len(set(keys)) != len(keys) or {"Left", "Right"} <= set(keys) or {"Up", "Down"} <= set(keys):
            raise ValueError("Duplicate or opposite Dpad inputs are outside the fixture profile")
        total += run["frames"]
    if total > 3600:
        raise ValueError("Input fixture exceeds the 3600-frame bound")
    return total


def execution_namespace(record, profile=None):
    kind = record.get("kind")
    if kind is None:
        if "binding" in record:
            raise ValueError("Bound SOURCE profile kind is required")
        return ROOT / ".audit/native-room-transition/source-contract-01"
    if kind == "native-room-transition-full-bake-source-cpu-v1":
        if profile is None:
            raise ValueError("Full-bake profile path is required")
        from prepare_full_bake_transition_profile import verify_profile
        if verify_profile(profile) != record:
            raise ValueError("Full-bake profile path/content mismatch")
        return ROOT / ".audit/native-room-transition-vita/full-bake-contract-01"
    if kind == "native-room-transition-gameplay-draw-v1":
        if profile is None:
            raise ValueError("Gameplay-DRAW profile path is required")
        from prepare_gameplay_draw_profile import AUDIT, verify_profile
        if verify_profile(profile) != record:
            raise ValueError("Gameplay-DRAW profile path/content mismatch")
        return AUDIT
    raise ValueError("Unknown SOURCE profile kind")


def run(profile, sdk, content, controls, output):
    record = json.loads((profile / "transition-profile.json").read_text())
    output_root = execution_namespace(record, profile)
    if record.get("kind") == "native-room-transition-gameplay-draw-v1" and record["inputs"].get(str(sdk)) != file_identity(sdk):
        raise ValueError("Gameplay-DRAW execution requires the pinned SOURCE SDK")
    if output.exists() or not output.resolve().is_relative_to(output_root):
        raise ValueError("Execution output must be fresh and private")
    validate_controls(json.loads(controls.read_text()))
    verify_inputs(record["inputs"], record["compiled_sources"])
    verify_file_identities({str(profile / name): value for name, value in record["generated"].items()})
    verify_file_identities({str(profile / name): value for name, value in record["compiled_artifacts"].items()})
    compiler = json.loads((profile / "compiler-command.json").read_text())
    if compiler[-len(record["compiled_sources"]):] != record["compiled_sources"]:
        raise ValueError("Compiled source/import-guard binding changed")
    output.mkdir(parents=True)
    for directory in ("home", "tmp"):
        (output / directory).mkdir()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    command = list(map(str, [sdk, profile / "Oracle.dll", output / "trace.jsonl", content, profile, controls]))
    inputs = {str(path): file_identity(path) for path in (sdk, profile / "Oracle.dll", profile / "Oracle.runtimeconfig.json", controls)}
    with (output / "execution.log").open("x") as log:
        result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=120,
                                env=dict(os.environ, HOME=str(output / "home"), TMPDIR=str(output / "tmp"), DOTNET_EnableDiagnostics="0"))
    verify_inputs(record["inputs"], record["compiled_sources"])
    verify_file_identities(inputs)
    receipt = {"schema": 1, "exit_code": result.returncode, "command": command, "inputs": inputs,
                "status": "blocked-or-unaccepted-experiment", "claim": "No two-room transition acceptance or native execution"}
    if record.get("kind") == "native-room-transition-gameplay-draw-v1":
        receipt.update(profile_binding=record["binding"], trace=file_identity(output / "trace.jsonl"))
    (output / "execution.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("profile", "sdk", "content", "controls", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    receipt = run(*(getattr(args, name).resolve() for name in ("profile", "sdk", "content", "controls", "output")))
    print(json.dumps({key: receipt[key] for key in ("exit_code", "status", "claim")}))
    raise SystemExit(1 if receipt["exit_code"] else 0)
