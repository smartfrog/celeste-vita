#!/usr/bin/env python3
"""Narrow offline discovery of the private death/reload scheduling closure."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from check_native_oracle import ROOT, PRIVATE, oracle_environment
from prepare_room_visuals import MEMBERS
from read_player_presentation_sources import ILSPY_SHA, source_type, extract as extract_presentation, SOURCE_PINS as PRESENTATION_PINS
from extract_native_oracle import SOURCE_HASHES

EXTRA_PINS = {
    "Celeste.PlayerDeadBody.cs": "6574be9e406977faaa4dbac3fcd236a6ca2220b19b32913759028df242804f7b",
    "Celeste.DeathEffect.cs": "92db0b010c7e22c86b83fda3e12b3f4aa0c996c0280f5d493a63efb440692843",
    "Monocle.Tween.cs": "14f46d0fb8cfb46740cc2271924ce959ee0c7b20b4843c93f845eb4946d4e69f",
    "Monocle.EntityList.cs": "4ae4205ff0826a0fa53354148a1271317b0e0af1e38fa8e3661f2139e2bf9fac",
    "Celeste.ScreenWipe.cs": "a3ba0b23e5d570db2a8deca3f4f83cff39186547d3e5a6ac781387ae22c4bd20",
    "Celeste.AngledWipe.cs": "0940e975109e22895605b585ba758803fb4bdfc57aa459f29137db011a5ba55b",
    "Monocle.Ease.cs": "71e4281d0dcc831ce918b67e0c57d70cce757d82009ed6d776b893f34a0ba52f",
    "Monocle.RendererList.cs": "17dbdc565b3f185d94879dbcc81b83746374a73317a0d1054afdd683e5d18c34",
    "Monocle.TagLists.cs": "52774446f867bb1c6acfb036e338fb36d9f2e12f13030b613a756a07f63e326f",
    "Monocle.Tracker.cs": "b32e56dda320e73d99453150585a47580427bac012861e131ac7623940bfdbd8",
    "Monocle.Renderer.cs": "b01c1f7ab70d6e460cab2a5e947a40d1e83ba8f513c8383def9eba75b1cfad94",
    "Celeste.DisplacementRenderer.cs": "18dd57e5218b3f25b9dfb2492c45e28d606e2a45af24156b846cd12d09679a4c",
    "Celeste.WindController.cs": "96caa6d45ba0d1e97c3ed64b1c6b5a8416518679a89b914c1da38a7347c11098",
    "Monocle.Component.cs": "7c16c7fc976557595c0e30ac1013705261f1637f9b585d4d53533960ed01f464",
} | {name: SOURCE_HASHES[name] for name in (
    "Monocle.Entity.cs", "Monocle.Coroutine.cs", "Monocle.StateMachine.cs", "Monocle.Scene.cs",
    "Monocle.Engine.cs", "Celeste.Celeste.cs",
)}
SOURCE_PINS = PRESENTATION_PINS | EXTRA_PINS


def extract(inputs, archive, output):
    output = output.resolve()
    if not output.is_relative_to(ROOT / ".audit/native-player-death-respawn") or output.exists():
        raise ValueError("Death source output must be fresh and private")
    sdk = PRIVATE / "tools/dotnet-8.0.425/dotnet"
    tool = ROOT / ".audit/ilspy/tools/ilspycmd-9.1.0.7988/tools/net8.0/any/ilspycmd.dll"
    if hashlib.sha256(tool.read_bytes()).hexdigest() != ILSPY_SHA:
        raise ValueError("Offline ILSpy identity changed")
    identities = {}
    for name in ("Celeste.exe", "FNA.dll", "mscorlib.dll"):
        digest = hashlib.sha256((inputs / name).read_bytes()).hexdigest()
        if digest != MEMBERS[name]:
            raise ValueError("Pinned private input changed: " + name)
        identities[name] = digest
    output.mkdir(parents=True)
    extract_presentation(inputs, archive, output / "presentation")
    receipt = {"inputs": identities, "tool_sha256": ILSPY_SHA, "sources": [], "commands": [],
               "recipe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    commands = [([sdk, "--version"], "sdk.log"), ([sdk, "--list-runtimes"], "runtime.log")]
    for filename in EXTRA_PINS:
        assembly, type_name = source_type(filename)
        commands.append(([sdk, tool, "--disable-updatecheck", "-r", inputs, "-t", type_name, inputs / assembly], filename))
    for command, filename in commands:
        command = list(map(str, command))
        with (output / filename).open("xb") as stdout, (output / (filename + ".stderr")).open("xb") as stderr:
            result = subprocess.run(command, cwd=ROOT, env=oracle_environment(sdk), stdout=stdout, stderr=stderr)
        receipt["commands"].append({"command": command, "exit_code": result.returncode})
        (output / "provenance.json").write_text(json.dumps(receipt, indent=2) + "\n")
        if result.returncode:
            raise RuntimeError("Offline extraction failed: " + filename)
        if filename == "sdk.log" and (output / filename).read_text().strip() != "8.0.425":
            raise ValueError("Pinned SDK changed")
        if filename == "runtime.log" and "Microsoft.NETCore.App 8.0.31 [" not in (output / filename).read_text():
            raise ValueError("Pinned runtime changed")
        if filename.endswith(".cs"):
            digest = hashlib.sha256((output / filename).read_bytes()).hexdigest()
            if digest != EXTRA_PINS[filename]:
                raise ValueError("Pinned decompiled source changed: " + filename)
            receipt["sources"].append({"file": filename, "sha256": digest})
    (output / "provenance.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=ROOT / ".audit/ilspy/inputs")
    parser.add_argument("--archive", type=Path, default=ROOT / "game/celeste-linux.zip")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(extract(args.inputs.resolve(), args.archive.resolve(), args.output), indent=2))
