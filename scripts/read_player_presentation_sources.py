#!/usr/bin/env python3
"""Extract the pinned bounded presentation closure with existing offline ILSpy."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

from check_native_oracle import ROOT, PRIVATE, oracle_environment
from prepare_room_visuals import MEMBERS

SOURCE_PINS = {
    "System.Random.cs": "4d50e548631225ad23a4f2fbc48e6263e8424ed9033f2e5a4a1fe33c95060c52",
    "Microsoft.Xna.Framework.Vector2.cs": "5029bb0ed057cf28a506168082e78d80d862ec0399935abbd231780ef9a34dc3",
    "Microsoft.Xna.Framework.Color.cs": "2eaf5b1aaafb1acba38bfe46bb3629907b7dfa171248f1db7a9c2aace60a5ed7",
    "Microsoft.Xna.Framework.MathHelper.cs": "b3f8b47286150f786779f5b2362ee29f770efab9f9368283021c9797a519b92c",
    "Microsoft.Xna.Framework.Rectangle.cs": "b3fd25e76f83b62e26dacd78877088ad64b30d8c625347ffca750ddd54e195cc",
    "Microsoft.Xna.Framework.Graphics.SpriteEffects.cs": "f4e1fb57e8f77996ad20c30b76749b3532bbe1f1f95a056d44c6294f406767ec",
    "Microsoft.Xna.Framework.Graphics.SpriteBatch.cs": "00446c9efcf427a01a2a55f0ac23feb22ecbb030842401faf65c77328931bcf2",
    "Monocle.Sprite.cs": "5095f3b86a78844a4076e1744b28e8ee493923baa920bb06b3497d7f253ebfee",
    "Monocle.Image.cs": "aa87a22589821fc3781672126e68f2195fb46348f261013d8a01c070b53821d3",
    "Monocle.SpriteData.cs": "19c2f1d957dc4d452a6ea8570c1a4d6fe06afbceff982e9264a2ff227391db53",
    "Monocle.SpriteBank.cs": "bcac39a656b8ec0400bbdfb5037a358544bda0f61ad57b61367c68830dd83c45",
    "Monocle.Chooser_1.cs": "70248406369a656e39d151b223f42e7722ccd36fa74709405ebf296a3c6abfd0",
    "Monocle.GraphicsComponent.cs": "7aea400b2428df2708b31c844f0dd15b797c419a4a63f945a473127ab3c4c210",
    "Monocle.SpriteDataSource.cs": "8c6f4811a8b3efa4ed2a099d8915a4295577e3b9cc57a6d848cb177d9cb80b6b",
    "Monocle.Atlas.cs": "95deee77a169baa04e91a5eeca76a7fd0a933ac338f2c17a847e217d7780cf70",
    "Monocle.MTexture.cs": "45847f23970911b07541e4bc367cbd156f3b4b1846b63b33d3fed9c7b65ebf6b",
    "Monocle.Calc.cs": "53ba72dc68ea5f6fed05e5394dc2fa0e867ea9317cb1f3271bd0c9c6fec38669",
    "Monocle.ComponentList.cs": "8ce914cfba10d41711598668e01f43015e53314fcda2b9c2c8d7a11548fb50a3",
    "Monocle.Scene.cs": "741b780cc262406f1c0b6cc862af5656de6698bd594068c77ddfbefa08bdf71a",
    "Celeste.Player.cs": "47413e0a774802c6dac9baff96aca6f6fda01edd8f28b1dd9bb86e0075cd4d9a",
    "Celeste.PlayerSprite.cs": "6473955ba7cedbc5121707e219001e443d36b66a9534d9818a86c58f99be09bc",
    "Celeste.PlayerHair.cs": "a7496be9f8284c259a30fd1ac20e27821da3f83682bb4d01b0a7471f5ea7cc13",
    "Celeste.PlayerSpriteMode.cs": "08042718c933e185b425a22d9a92213916490be92c9d5a6f19844a6cb26d222e",
    "Celeste.PlayerAnimMetadata.cs": "f2c3ef46b078a4a1423e156679886b6a73452160232ab4af1d4c4f15662b99db",
    "Celeste.Facings.cs": "402c6bcbb5580bc5fbcfcdcc8e85b92f3ab796bc4c98910c628ff2e3c0459226",
    "Celeste.Level.cs": "3f2b9dcee1d9904177f6b9c71d703f826f85dc768c2b63335cb3db2a60c4d849",
    "Celeste.PlayerInventory.cs": "fca9bed434019cba9bbe937e18e5d170c420cbbe51740926a4e9d70aeac7ec5f",
    "Celeste.AreaData.cs": "d69d1c309aa4867ed0fd40e699cbbba4757a2d9fc6d2197174e162ce3be40876",
    "Celeste.GFX.cs": "b263291f1235c4c3b4ff25f1e185a5014019bad1b4aacdf84e5dd75137475918",
    "Celeste.Spikes.cs": "fb485592822286d316d93fe029acf92b83e4a0b119492dd3d2fa77f6b5e11901",
}
ILSPY_SHA = "58ef1a86bea09f2e5a114720b607dd0bdaaf91cfe498c6b7a3412bd960d0f57d"
ARCHIVE_SHA = "a613430411dbef3c0c45a0474f90f4845122964c7d177d69e88965bcb84741bf"


def source_type(filename):
    name = filename.removesuffix(".cs").replace("_1", "`1")
    return ("FNA.dll" if name.startswith("Microsoft.") else "mscorlib.dll" if name == "System.Random" else "Celeste.exe"), name


def extract(inputs, archive_path, output):
    output = output.resolve()
    if not output.is_relative_to(ROOT / ".audit") or output.exists():
        raise ValueError("Source output must be fresh and private below .audit")
    sdk = PRIVATE / "tools/dotnet-8.0.425/dotnet"
    tool = ROOT / ".audit/ilspy/tools/ilspycmd-9.1.0.7988/tools/net8.0/any/ilspycmd.dll"
    if hashlib.sha256(tool.read_bytes()).hexdigest() != ILSPY_SHA:
        raise ValueError("Existing offline ILSpy identity changed")
    identities = {}
    for name in ("Celeste.exe", "FNA.dll", "mscorlib.dll"):
        data = (inputs / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != MEMBERS[name]:
            raise ValueError("Original private executable/framework identity changed: " + name)
        identities[name] = {"path": str(inputs / name), "bytes": len(data), "sha256": MEMBERS[name]}
    if archive_path.stat().st_size != 883881658:
        raise ValueError("Original private archive length changed")
    with archive_path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != ARCHIVE_SHA:
            raise ValueError("Original private archive identity changed")
    output.mkdir(parents=True)
    receipt = {"inputs": identities, "tool_sha256": ILSPY_SHA, "archive": {"path": str(archive_path), "bytes": 883881658, "sha256": ARCHIVE_SHA}, "sources": [], "commands": []}

    def run(command, stdout, stderr=None):
        command = list(map(str, command))
        with stdout.open("xb") as log:
            if stderr is None:
                result = subprocess.run(command, cwd=ROOT, env=oracle_environment(sdk), stdout=log, stderr=subprocess.STDOUT)
            else:
                with stderr.open("xb") as errors:
                    result = subprocess.run(command, cwd=ROOT, env=oracle_environment(sdk), stdout=log, stderr=errors)
        receipt["commands"].append({"command": command, "exit_code": result.returncode, "log": stdout.name})
        (output / "provenance.json").write_text(json.dumps(receipt, indent=2) + "\n")
        if result.returncode:
            raise RuntimeError("Offline source extraction command failed: " + str(stdout))

    run([sdk, "--version"], output / "sdk.log")
    run([sdk, "--list-runtimes"], output / "runtime.log")
    if (output / "sdk.log").read_text().strip() != "8.0.425" or "Microsoft.NETCore.App 8.0.31 [" not in (output / "runtime.log").read_text():
        raise ValueError("Pinned offline SDK/runtime changed")
    for filename, expected in SOURCE_PINS.items():
        assembly, name = source_type(filename)
        path = output / filename
        run([sdk, tool, "--disable-updatecheck", "-r", inputs, "-t", name, inputs / assembly], path, output / (filename + ".stderr"))
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("Pinned decompiled source identity changed: " + filename)
        receipt["sources"].append({"type": name, "assembly": assembly, "file": filename, "bytes": len(data), "sha256": expected})
    with zipfile.ZipFile(archive_path) as archive:
        for name in ("Content/Graphics/Sprites.xml", "Content/Graphics/Atlases/Gameplay.meta"):
            data = archive.read(name)
            if hashlib.sha256(data).hexdigest() != MEMBERS[name]:
                raise ValueError("Original sprite/atlas member changed")
            (output / name.rsplit("/", 1)[1]).write_bytes(data)
    receipt["recipe_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (output / "provenance.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=ROOT / ".audit/ilspy/inputs")
    parser.add_argument("--archive", type=Path, default=ROOT / "game/celeste-linux.zip")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = extract(args.inputs.resolve(), args.archive.resolve(), args.output)
    print(f"Extracted {len(receipt['sources'])} pinned source types offline: {args.output}")
