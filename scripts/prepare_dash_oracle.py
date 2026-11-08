#!/usr/bin/env python3
"""Prepare missing private Dash/jump helper sources with the existing offline ILSpy."""

import hashlib
import json
import subprocess

from check_native_oracle import ROOT, PRIVATE, oracle_environment
from extract_native_oracle import INPUT_SHA, SOURCE_HASHES


def main():
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
    rows = []
    for name in ("Monocle.Engine", "Monocle.MInput", "Celeste.Celeste", "Monocle.Calc"):
        directory = ROOT / ".audit/native-wall-jumps/closure" if name == "Monocle.Calc" else output
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / (name + ".cs")
        if not destination.exists():
            command = [str(sdk), str(tool), "--disable-updatecheck", "-r", str(source / "inputs"), "-t", name, str(executable)]
            with destination.open("xb") as stdout, (directory / (name + ".stderr")).open("xb") as stderr:
                subprocess.run(command, env=oracle_environment(sdk), stdout=stdout, stderr=stderr, check=True, timeout=180)
            rows.append({"type": name, "command": command})
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        if digest != SOURCE_HASHES[name + ".cs"]:
            raise ValueError("Changed private source preserved for diagnosis: " + str(destination))
        print(name + " SHA256 " + digest)
    if rows:
        with (output / "preparation.json").open("x") as receipt:
            receipt.write(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    main()
