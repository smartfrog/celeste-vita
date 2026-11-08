#!/usr/bin/env python3
"""Re-read two pinned private types with the existing offline ILSpy; retain immutable provenance."""

import hashlib
import json
import subprocess

from check_native_oracle import ROOT, PRIVATE, oracle_environment
from extract_native_oracle import INPUT_SHA, SOURCE_HASHES


def retain_sources(output, names):
    exe = ROOT / ".audit/ilspy/inputs/Celeste.exe"
    if hashlib.sha256(exe.read_bytes()).hexdigest() != INPUT_SHA:
        raise ValueError("Unexpected private executable hash")
    sdk = PRIVATE / "tools/dotnet-8.0.425/dotnet"
    ilspy = ROOT / ".audit/ilspy/tools/ilspycmd-9.1.0.7988/tools/net8.0/any/ilspycmd.dll"
    output.mkdir(parents=True, exist_ok=True)
    for name in names:
        path = output / (name + ".cs")
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest() != SOURCE_HASHES[path.name]:
                raise ValueError(f"Changed retained source: {path}")
            print(f"Verified retained private source {name}")
            continue
        command = [str(sdk), str(ilspy), "--disable-updatecheck", "-r", str(exe.parent), "-t", name, str(exe)]
        result = subprocess.run(command, env=oracle_environment(sdk), capture_output=True, check=True, timeout=180)
        source_hash = hashlib.sha256(result.stdout).hexdigest()
        if source_hash != SOURCE_HASHES[path.name]:
            raise ValueError(f"Changed ILSpy output for {name}: {source_hash}")
        with path.open("xb") as out:
            out.write(result.stdout)
        with (output / (name + ".stderr")).open("xb") as out:
            out.write(result.stderr)
        with (output / (name + ".provenance.json")).open("x") as out:
            json.dump({"command": command, "input_sha256": INPUT_SHA, "source_sha256": source_hash,
                       "ilspy_sha256": hashlib.sha256(ilspy.read_bytes()).hexdigest()}, out, indent=2)
            out.write("\n")
        print(f"Retained private source {name}")


if __name__ == "__main__":
    retain_sources(ROOT / ".audit/native-static-tilemap", ("Celeste.LevelLoader", "Celeste.MapData"))
