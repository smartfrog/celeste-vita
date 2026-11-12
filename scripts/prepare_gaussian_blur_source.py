"""Execute unchanged private GaussianBlur source through the restricted render API observer."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from native_room_revision import canonical_digest, file_identity, verify_file_identities
from prepare_dash_trail_oracle import compile_recording
from prepare_player_presentation_oracle import source_block
from prepare_rendergraph_source_slice import CANONICAL, GFX, ROOT, SDK, PINS, verify_profile as verify_rendergraph
from rendergraph_effect_contract import gaussian_effect

AUDIT = ROOT / ".audit/native-room-transition-vita/gaussian-blur-contract-01"
KIND = "native-room-transition-gaussian-blur-source-api-v1"
CLAIM = "Original GaussianBlur.Blur Both-direction API execution; observer-owned RectangleDraw, not FNA quads/default shader, BeforeRender, full Level, GPU, pixels or Vita"
SOURCE = CANONICAL / ".audit/native-room-transition-vita/gaussian-blur-source-01/Celeste.GaussianBlur.cs"
MANIFEST = SOURCE.parent / "manifest.json"
SOURCE_PINS = {SOURCE: "149eb925e87bff910b902585befaf0da93c3702ce2b66efd7a4c43f353661f50",
               MANIFEST: "8df1d889f264e5cd3a22fd15cd3309dc9f33472c9e67b35107d28f73c959cb73"}
OBSERVER = ROOT / "tests/native/oracle/transition/GaussianBlurSource.cs"
GENERATED = {"GaussianGfx.cs", "effects.json", "Oracle.csproj"}
ARTIFACTS = {"Oracle.dll", "Oracle.runtimeconfig.json", "compiler-command.json"}


def validate_profile(record):
    if type(record.get("schema")) is not int or record["schema"] != 1 or record.get("kind") != KIND:
        raise ValueError("Expected separate Gaussian source API kind/version")
    if record.get("binding") != canonical_digest({k: v for k, v in record.items() if k != "binding"}):
        raise ValueError("Gaussian source API binding changed")
    if record.get("claim") != CLAIM:
        raise ValueError("Gaussian source API scope changed")


def verify_profile(profile):
    record = json.loads((profile / "transition-profile.json").read_text())
    validate_profile(record)
    if record.get("profile_directory") != str(profile.resolve()) or not profile.resolve().is_relative_to(AUDIT):
        raise ValueError("Gaussian profile namespace mismatch")
    if set(record.get("generated", {})) != GENERATED or set(record.get("compiled_artifacts", {})) != ARTIFACTS:
        raise ValueError("Missing Gaussian generated/artifact identities")
    parent = verify_rendergraph(Path(record["source_profile"]))
    if record.get("source_binding") != parent["binding"]:
        raise ValueError("Gaussian prerequisite binding changed")
    required = {str(path) for path in (*SOURCE_PINS, OBSERVER, Path(__file__).resolve(),
                                     ROOT / "scripts/rendergraph_effect_contract.py")}
    command = json.loads((profile / "compiler-command.json").read_text())
    parent_command = json.loads((Path(record["source_profile"]) / "compiler-command.json").read_text())
    if command[:2] != parent_command[:2]:
        raise ValueError("Unpinned Gaussian compiler")
    required.update(str(Path(value[3:])) for value in command if value.startswith("-r:"))
    required.update(command[:2])
    required.update(item.attrib["Include"] for item in ET.parse(profile / "Oracle.csproj").findall(".//Compile")
                    if not Path(item.attrib["Include"]).is_relative_to(profile))
    if not required.issubset(record.get("inputs", {})):
        raise ValueError("Missing Gaussian compiler/source/observer identities")
    for path, sha in SOURCE_PINS.items():
        if record["inputs"][str(path)]["sha256"] != sha:
            raise ValueError("Missing pinned original Gaussian provenance")
    if command[0] != str(SDK) or record["inputs"][str(SDK)] != parent["inputs"][str(SDK)]:
        raise ValueError("Unpinned Gaussian SDK")
    verify_file_identities(record["inputs"])
    for key in ("generated", "compiled_artifacts"):
        verify_file_identities({str(profile / name): value for name, value in record[key].items()})
    if json.loads((profile / "effects.json").read_text()) != {"GaussianBlur": gaussian_effect()}:
        raise ValueError("Gaussian metadata does not match original shader resource")
    return record


def prepare(source_profile, output):
    if output.exists() or not output.resolve().is_relative_to(AUDIT):
        raise ValueError("Gaussian output must be fresh beneath separate namespace")
    parent = verify_rendergraph(source_profile)
    for path, sha in SOURCE_PINS.items():
        if file_identity(path)["sha256"] != sha:
            raise ValueError("Pinned original Gaussian input changed: " + str(path))
    manifest = json.loads(MANIFEST.read_text())
    provenance = {item["path"]: {"bytes": item["bytes"], "sha256": item["sha256"]} for item in manifest["pins"].values()}
    verify_file_identities(provenance)
    effects = {"GaussianBlur": gaussian_effect()}
    field = source_block(GFX.read_bytes(), [(35, 35)], PINS[GFX])[0].decode()
    gfx = (source_profile / "IndexedHelperSlice.cs").read_text().replace("public static class GFX {", "public static class GFX {\n" + field)
    files = [Path(item.attrib["Include"]) for item in ET.parse(source_profile / "Oracle.csproj").findall(".//Compile")
             if Path(item.attrib["Include"]).name not in ("RendergraphSourceSlice.cs", "IndexedHelperSlice.cs")]
    files += [SOURCE, OBSERVER, output / "GaussianGfx.cs"]
    generated = {"GaussianGfx.cs": gfx, "effects.json": json.dumps(effects, indent=2) + "\n",
                 "Oracle.csproj": '<Project><ItemGroup>' + ''.join('<Compile Include="' + escape(str(path)) + '"/>' for path in files) + '</ItemGroup></Project>'}
    inputs = dict(parent["inputs"], **provenance)
    inputs.update({str(path): file_identity(path) for path in (*SOURCE_PINS, OBSERVER, Path(__file__).resolve(),
                   source_profile / "transition-profile.json", *[p for p in files if p != output / "GaussianGfx.cs"])})
    verify_file_identities(inputs)
    output.mkdir(parents=True)
    for directory in ("home", "tmp"):
        (output.parent / directory).mkdir(exist_ok=True)
    marker = output.parent / "home/.local/share/NuGet/Migrations/1"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch(exist_ok=True)
    for name, text in generated.items():
        (output / name).write_text(text)
    compile_recording(output, SDK)
    record = {"schema": 1, "kind": KIND, "claim": CLAIM, "profile_directory": str(output.resolve()),
              "source_profile": str(source_profile), "source_binding": parent["binding"], "inputs": inputs,
              "whole_original_sources": [str(SOURCE)], "original_payload_copies": [],
              "boundaries": {"fixture": "Original GameplayBuffers.Create/Unload and VirtualRenderTarget allocation; Light/TempA/TempB distinct actual targets",
                             "rectangle": "Observer-owned API adapter; original FNA quad/default vertex shader not executed",
                             "depth": "Original previously accepted DepthStencilState.Default implementation resolved by observer",
                             "unsupported": ["H/V default shader", "target alias hazards", "full Lighting.BeforeRender", "GPU/pixels/Vita"]},
              "generated": {name: file_identity(output / name) for name in GENERATED},
              "compiled_artifacts": {name: file_identity(output / name) for name in ARTIFACTS}}
    record["binding"] = canonical_digest(record)
    (output / "transition-profile.json").write_text(json.dumps(record, indent=2) + "\n")
    verify_profile(output)
    return record


def run(profile, output):
    record = verify_profile(profile)
    if output.exists() or not output.resolve().is_relative_to(AUDIT):
        raise ValueError("Gaussian execution must be fresh beneath separate namespace")
    command = [str(SDK), str(profile / "Oracle.dll"), str(profile / "effects.json")]
    output.mkdir(parents=True)
    environment = dict(os.environ, HOME=str(profile.parent / "home"), TMPDIR=str(profile.parent / "tmp"), DOTNET_EnableDiagnostics="0")
    with (output / "trace.jsonl").open("x") as trace, (output / "stderr.log").open("x") as errors:
        result = subprocess.run(command, cwd=profile, env=environment, stdout=trace, stderr=errors, timeout=60)
    receipt = {"kind": KIND, "binding": record["binding"], "command": command, "returncode": result.returncode,
               "trace": file_identity(output / "trace.jsonl"), "stderr": file_identity(output / "stderr.log")}
    (output / "execution.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if result.returncode:
        raise RuntimeError("Original Gaussian source execution failed: " + str(output / "stderr.log"))
    verify_profile(profile)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "run"))
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = (prepare if args.mode == "prepare" else run)(args.profile.resolve(), args.output.resolve())
    print(json.dumps({key: result[key] for key in ("kind", "binding")}))
