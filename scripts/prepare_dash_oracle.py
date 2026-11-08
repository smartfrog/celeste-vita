#!/usr/bin/env python3
"""Prepare missing private Dash/jump helper sources with the existing offline ILSpy."""

import hashlib
import argparse
import json
import subprocess

from check_native_oracle import ROOT, PRIVATE, oracle_environment
from extract_native_oracle import INPUT_SHA, SOURCE_HASHES


def main(include_climb=False):
    source = ROOT / ".audit/ilspy"
    output = ROOT / ".audit/native-dash/closure"
    sdk = PRIVATE / "tools/dotnet-8.0.425/dotnet"
    tool = source / "tools/ilspycmd-9.1.0.7988/tools/net8.0/any/ilspycmd.dll"
    executable = source / "inputs/Celeste.exe"
    if not sdk.is_file() or not tool.is_file():
        raise FileNotFoundError("Existing private SDK/ILSpy required; this script never downloads dependencies")
    if hashlib.sha256(executable.read_bytes()).hexdigest() != INPUT_SHA:
        raise ValueError("Unexpected private reference executable")
    output.mkdir(parents=True, exist_ok=True)
    names = ("Monocle.Engine", "Monocle.MInput", "Celeste.Celeste", "Monocle.Calc") + (("Monocle.Scene",) if include_climb else ())
    for name in names:
        directory = ROOT / ".audit/native-climb/closure" if name == "Monocle.Scene" else ROOT / ".audit/native-wall-jumps/closure" if name == "Monocle.Calc" else output
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / (name + ".cs")
        command = None
        if not destination.exists():
            command = [str(sdk), str(tool), "--disable-updatecheck", "-r", str(source / "inputs"), "-t", name, str(executable)]
            with destination.open("xb") as stdout, (directory / (name + ".stderr")).open("xb") as stderr:
                subprocess.run(command, env=oracle_environment(sdk), stdout=stdout, stderr=stderr, check=True, timeout=180)
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        if digest != SOURCE_HASHES[name + ".cs"]:
            raise ValueError("Changed private source preserved for diagnosis: " + str(destination))
        if command is not None:
            with (directory / (name + ".preparation.json")).open("x") as receipt:
                receipt.write(json.dumps({"type": name, "command": command, "input_sha256": INPUT_SHA,
                                          "source_sha256": digest}, indent=2) + "\n")
        print(name + " SHA256 " + digest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--climb", action="store_true", help="Also verify/prepare the pinned Scene point-query helper")
    main(parser.parse_args().climb)
