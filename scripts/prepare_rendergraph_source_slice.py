"""Separate original-source render API prerequisite slice; never Level/GPU closure."""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
from xml.sax.saxutils import escape

from native_room_revision import canonical_digest, file_identity, verify_file_identities
from prepare_dash_trail_oracle import compile_recording
from prepare_gameplay_draw_profile import verify_profile as verify_draw_profile
from prepare_player_presentation_oracle import source_block
from rendergraph_effect_contract import ARCHIVE, original_effects

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = Path("/home/fred/projects/celeste-vita")
AUDIT = ROOT / ".audit/native-room-transition-vita/rendergraph-source-slice-01"
KIND = "native-room-transition-rendergraph-source-slice-v1"
CLAIM = "Original GameplayBuffers lifecycle, Lighting.Render and GFX indexed helper API slice; not BeforeRender, full Level, GPU, pixels or Vita"
DRAW_BINDING = "c6ee452419e5d276b38e2257a53a0f052a9a46f5eb0a63da7d2ff0761007a2b6"
FNA = CANONICAL / ".audit/ilspy/inputs/FNA.dll"
FNA_SHA = "00349b572636c0ed4c97d4e4f74344b3450160c42d4a6b52bcf5e0f2d5193a31"
SDK = CANONICAL / ".audit/native-oracle/tools/dotnet-8.0.425-linux-x64/dotnet"
BUFFERS = CANONICAL / ".audit/native-room-transition-vita/draw-source-closure-01/GameplayBuffers.cs"
TARGET = CANONICAL / ".audit/native-player-death-respawn/room-core-probe-42/source/Monocle.VirtualRenderTarget.cs"
LIGHTING = TARGET.parent / "Celeste.LightingRenderer.cs"
GFX = CANONICAL / ".audit/private-push-20261111/committed-preparation/player-sources/Celeste.GFX.cs"
PINS = {
    BUFFERS: "643b739788f51ac5c3345cc6173474708c89e6bcb0b5e6ede44ffd3a5393e27b",
    TARGET: "c07a60d04e613876f2f3cdbe897f98522c9d0697d4138ec3327c4f0837d79404",
    LIGHTING: "01bb8ef633506f709da14649b2aae54268cf73bca08bfd3260d71ce72de07eb2",
    GFX: "b263291f1235c4c3b4ff25f1e185a5014019bad1b4aacdf84e5dd75137475918",
    FNA: FNA_SHA,
}


def validate_profile(record):
    if type(record.get("schema")) is not int or record.get("schema") != 1 or record.get("kind") != KIND:
        raise ValueError("Expected separate rendergraph source-slice profile kind/version")
    if record.get("binding") != canonical_digest({k: v for k, v in record.items() if k != "binding"}):
        raise ValueError("Rendergraph source-slice binding changed")
    if record.get("claim") != CLAIM:
        raise ValueError("Rendergraph source-slice scope changed")


def verify_profile(profile):
    record = json.loads((profile / "transition-profile.json").read_text())
    validate_profile(record)
    if record["profile_directory"] != str(profile.resolve()) or not profile.resolve().is_relative_to(AUDIT):
        raise ValueError("Rendergraph source-slice profile namespace mismatch")
    if set(record.get("generated", {})) != {"LightingRenderSlice.cs", "IndexedHelperSlice.cs", "Framework.cs", "effects.json", "Oracle.csproj"}:
        raise ValueError("Missing generated source-slice identities")
    if set(record.get("compiled_artifacts", {})) != {"Oracle.dll", "Oracle.runtimeconfig.json", "compiler-command.json"}:
        raise ValueError("Missing compiled source-slice identities")
    for path, sha in PINS.items():
        if record.get("inputs", {}).get(str(path), {}).get("sha256") != sha:
            raise ValueError("Missing pinned original source-slice identity: " + str(path))
    source_profile = Path(record["source_profile"])
    source = verify_draw_profile(source_profile)
    if source["binding"] != DRAW_BINDING:
        raise ValueError("Expected accepted gate1 source profile")
    command = json.loads((profile / "compiler-command.json").read_text())
    required = [Path(command[0]), Path(command[1]), *[Path(value[3:]) for value in command if value.startswith("-r:")]]
    required += [Path(__file__).resolve(), ROOT / "scripts/rendergraph_effect_contract.py",
                 *[ROOT / "tests/native/oracle/transition" / name for name in ("RendergraphRecording.cs", "RendergraphSourceSlice.cs")]]
    if any(str(path) not in record["inputs"] for path in required):
        raise ValueError("Missing compiler/observer input identities")
    if command[0] != str(SDK) or record["inputs"][str(SDK)] != source["inputs"][str(SDK)]:
        raise ValueError("Unpinned source-slice SDK")
    verify_file_identities(record["inputs"])
    verify_file_identities({str(profile / name): identity for name, identity in record["generated"].items()})
    verify_file_identities({str(profile / name): identity for name, identity in record["compiled_artifacts"].items()})
    if json.loads((profile / "effects.json").read_text()) != original_effects():
        raise ValueError("Effect metadata does not match original resource structures")
    return record


def prepare(source_profile, output):
    if output.exists() or not output.resolve().is_relative_to(AUDIT):
        raise ValueError("Output must be fresh beneath separate rendergraph source-slice namespace")
    source = verify_draw_profile(source_profile)
    if source["binding"] != DRAW_BINDING:
        raise ValueError("Expected accepted gate1 source profile")
    for path, sha in PINS.items():
        if file_identity(path)["sha256"] != sha:
            raise ValueError("Pinned original input changed: " + str(path))
    effects = original_effects()
    spans = []

    def blocks(path, ranges):
        values = source_block(path.read_bytes(), ranges, PINS[path])
        spans.append({"path": str(path), "sha256": PINS[path], "ranges": ranges,
                      "blocks_sha256": [hashlib.sha256(value).hexdigest() for value in values]})
        return "\n".join(value.decode() for value in values)

    using = "using Microsoft.Xna.Framework;\nusing Microsoft.Xna.Framework.Graphics;\nusing Monocle;\n"
    lighting = using + "namespace Celeste { public class LightingRenderer : Renderer {\n" + blocks(LIGHTING, [(66, 66), (572, 579)]) + "\n}}\n"
    gfx = using + "namespace Celeste { public static class GFX {\n" + blocks(GFX, [(37, 37), (41, 41), (83, 91), (230, 245)]) + "\n}}\n"
    extracted = source_profile / "TransitionExtracted.cs"
    allowed = {"Vector2", "Color", "Rectangle", "MathHelper", "Point", "SpriteEffects", "BlendState", "Blend", "BlendFunction",
               "ColorWriteChannels", "GraphicsResource", "IVertexType", "VertexElement", "VertexElementFormat", "VertexElementUsage",
               "VertexDeclaration", "Viewport", "CompareFunction", "CullMode", "DepthStencilState", "FillMode", "RasterizerState",
               "SpriteSortMode", "StencilOperation", "TextureAddressMode", "VertexPositionColor", "VertexPositionColorTexture", "PresentInterval", "DisplayOrientation"}
    chunks = []
    for chunk in re.split(r"(?=^namespace )", extracted.read_text(), flags=re.M):
        declaration = re.search(r"public (?:static |abstract |partial )*(?:class|struct|enum|interface) (\w+)", chunk)
        if chunk.startswith("namespace Microsoft.Xna.Framework") and declaration and declaration.group(1) in allowed:
            chunks.append(chunk)
    gpu = next(Path(path) for path in source["compiled_sources"] if Path(path).name == "RoomCoreGpu.cs")
    probe = next(Path(path) for path in source["compiled_sources"] if Path(path).name == "RoomCoreProbe.cs")
    gpu_text = gpu.read_text()
    state_structs = gpu_text[gpu_text.index("    internal static partial class FNA3D"):gpu_text.index("    public sealed class GraphicsDevice")]
    framework = "using System;\nusing System.Collections.Generic;\nusing System.Runtime.InteropServices;\nusing System.Text;\n" + "".join(chunks)
    framework += "\nnamespace Microsoft.Xna.Framework.Graphics {\n" + state_structs + "\n}\n"
    framework += "".join(probe.read_text().splitlines(keepends=True)[2:13])
    files = [BUFFERS, TARGET, *[ROOT / "tests/native/oracle/transition" / name for name in ("RendergraphRecording.cs", "RendergraphSourceSlice.cs")],
             output / "LightingRenderSlice.cs", output / "IndexedHelperSlice.cs", output / "Framework.cs"]
    generated = {"LightingRenderSlice.cs": lighting, "IndexedHelperSlice.cs": gfx,
                 "effects.json": json.dumps(effects, indent=2) + "\n", "Framework.cs": framework,
                 "Oracle.csproj": '<Project><ItemGroup>' + ''.join('<Compile Include="' + escape(str(path)) + '"/>' for path in files) + '</ItemGroup></Project>'}
    inputs = {str(path): file_identity(path) for path in (*PINS, ARCHIVE, source_profile / "transition-profile.json",
              ROOT / "scripts/native_room_revision.py", ROOT / "scripts/prepare_dash_trail_oracle.py",
              ROOT / "scripts/prepare_player_presentation_oracle.py", ROOT / "scripts/rendergraph_effect_contract.py", Path(__file__).resolve(), extracted, gpu, probe, *files[:4])}
    for path, identity in source["inputs"].items():
        if path == str(SDK) or path.startswith(str(SDK.parent / "packs")) or path.endswith("/Roslyn/bincore/csc.dll"):
            inputs[path] = identity
    if str(SDK) not in inputs:
        raise ValueError("Pinned SOURCE SDK missing")
    verify_file_identities(inputs)
    output.mkdir(parents=True)
    for directory in ("home", "tmp"):
        (output.parent / directory).mkdir(exist_ok=True)
    for name, text in generated.items():
        (output / name).write_text(text)
    compile_recording(output, SDK)
    record = {"schema": 1, "kind": KIND, "claim": CLAIM, "profile_directory": str(output.resolve()),
              "inputs": inputs, "source_profile": str(source_profile), "original_spans": spans, "whole_original_sources": [str(BUFFERS), str(TARGET)],
              "framework_reuse": {"path": str(extracted), "sha256": inputs[str(extracted)]["sha256"], "types": sorted(allowed),
                                  "execution": "Unchanged already-accepted framework namespace chunks; all existing unsupported guards retained. No original assembly patched or loaded."},
              "fixture_boundary": "Original Lighting.Render body and Alpha field only; constructor/BeforeRender not executed. Original indexed helper receives explicit fixture vertices, not generated lighting geometry.",
              "original_payload_copies": [], "generated": {name: file_identity(output / name) for name in generated},
              "compiled_artifacts": {name: file_identity(output / name) for name in ("Oracle.dll", "Oracle.runtimeconfig.json", "compiler-command.json")}}
    record["binding"] = canonical_digest(record)
    (output / "transition-profile.json").write_text(json.dumps(record, indent=2) + "\n")
    verify_profile(output)
    return record


def run(profile, output):
    record = verify_profile(profile)
    if output.exists() or not output.resolve().is_relative_to(AUDIT):
        raise ValueError("Execution output must be fresh beneath separate rendergraph source-slice namespace")
    command = [str(SDK), str(profile / "Oracle.dll"), str(profile / "effects.json")]
    output.mkdir(parents=True)
    environment = dict(os.environ, HOME=str(profile.parent / "home"), TMPDIR=str(profile.parent / "tmp"), DOTNET_EnableDiagnostics="0")
    with (output / "trace.jsonl").open("x") as trace, (output / "stderr.log").open("x") as errors:
        result = subprocess.run(command, cwd=profile, env=environment, stdout=trace, stderr=errors, timeout=60)
    receipt = {"kind": KIND, "binding": record["binding"], "command": command, "returncode": result.returncode,
               "trace": file_identity(output / "trace.jsonl"), "stderr": file_identity(output / "stderr.log")}
    (output / "execution.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if result.returncode:
        raise RuntimeError("Rendergraph source-slice failed: " + str(output / "stderr.log"))
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
