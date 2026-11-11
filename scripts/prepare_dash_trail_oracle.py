"""Generate an isolated recording-only trail profile over the accepted room-core source cut."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from xml.sax.saxutils import escape

from native_room_revision import file_identity
from prepare_player_presentation_oracle import source_block
from prepare_player_room_core_oracle import remove_fixture_class
import xml.etree.ElementTree as ET


PLAYER_RANGES = [(4191, 4209), (4211, 4219), (4221, 4274), (4276, 4314), (4316, 4332),
                 (4334, 4338), (4340, 4448), (4450, 4463), (4465, 4567)]


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("Expected one isolated profile replacement: " + old[:140])
    return text.replace(old, new)


def replace_guard(text, original, source_name=None):
    signature = original.split("\n", 1)[0].strip()
    suffix = r'[^"\n]+' if source_name is None else r'[^"\n]+/' + re.escape(source_name) + r':[^"\n]+'
    pattern = re.escape(signature) + r'\s*\{ throw new DeathOracle.UnsupportedClosure\("Excluded source member: ' + suffix + r'"\); \}'
    text, count = re.subn(pattern, lambda _: original, text)
    if count != 1:
        raise ValueError("Missing original guarded member: " + signature)
    return text


def generate(accepted, manifest_path, legacy_root, output):
    if output.exists():
        raise ValueError("Oracle output must be fresh")
    manifest = json.loads(manifest_path.read_text())
    inputs = {str(manifest_path): file_identity(manifest_path)}
    spans = []

    def original(name, ranges):
        entry = next((e for e in manifest["extractions"] if e["file"] == name), None)
        if entry:
            path = Path(entry["source_path"])
            path = path if path.is_absolute() else legacy_root / path
            sha = entry["source_sha256"]
        else:
            entry = next(e for group in ("executable_members", "declaration_contracts") for e in manifest[group]
                         if Path(e["File"]).name == name)
            path, sha = Path(entry["File"]), entry["SourceSha256"]
        blocks = source_block(path.read_bytes(), ranges, sha)
        inputs[str(path)] = file_identity(path)
        spans.append({"file": name, "source": str(path), "source_sha256": sha, "ranges": ranges,
                      "blocks_sha256": [hashlib.sha256(block).hexdigest() for block in blocks]})
        return [block.decode() for block in blocks]

    extracted = (accepted / "Extracted.cs").read_text()
    if hashlib.sha256(extracted.encode()).hexdigest() != manifest["extracted_sha256"]:
        raise ValueError("Accepted source extraction changed")
    for member in original("Celeste.Player.cs", PLAYER_RANGES):
        extracted = replace_guard(extracted, member)
    original("Celeste.Player.cs", [(1948, 1959), (4343, 4355), (4508, 4519), (4553, 4567)])
    original("Celeste.PlayerSprite.cs", [(224, 230)])
    original("Celeste.LightingRenderer.cs", [(36, 44)])
    extracted = remove_fixture_class(extracted, "TrailManager")
    extracted += "\nnamespace Celeste {\n" + original("Celeste.TrailManager.cs", [(7, 266)])[0] + "\n}\n"
    extracted = remove_fixture_class(extracted, "RasterizerState")
    extracted += "\nnamespace Microsoft.Xna.Framework.Graphics {\n" + original("Microsoft.Xna.Framework.Graphics.RasterizerState.cs", [(3, 101)])[0] + "\n}\n"
    joystick = original("Monocle.VirtualJoystick.cs", [(71, 233)])[0]
    extracted = replace_guard(extracted, joystick, "Monocle.VirtualJoystick.cs")
    extracted = replace_guard(extracted, original("Monocle.Calc.cs", [(895, 898)])[0])
    for member in original("Celeste.SpeedRing.cs", [(23, 31), (33, 41)]):
        extracted = replace_guard(extracted, member, "Celeste.SpeedRing.cs")
    extracted, count = re.subn(r'\{ throw new DeathOracle.UnsupportedClosure\("Excluded source member: [^"\n]+/Celeste.SpeedRing.cs:SpeedRing.implicit-ctor"\); \}', '{}', extracted)
    if count != 1:
        raise ValueError("Missing source SpeedRing implicit default constructor")
    previous = original("Monocle.VirtualJoystick.cs", [(43, 43)])[0]
    extracted, count = re.subn(r'public Vector2 PreviousValue \{ get\{ throw new DeathOracle.UnsupportedClosure\("[^"\n]+/Monocle.VirtualJoystick.cs:PreviousValue.get"\); \}private set\{ throw new DeathOracle.UnsupportedClosure\("[^"\n]+/Monocle.VirtualJoystick.cs:PreviousValue.set"\); \}\}', previous, extracted)
    if count != 1:
        raise ValueError("Missing original joystick PreviousValue property")
    extracted = re.sub(r'get\s*\{ throw new DeathOracle.UnsupportedClosure\("Excluded source member: [^"\n]+/Microsoft.Xna.Framework.Game.cs:GraphicsDevice.get"\); \}',
                       "get { return Monocle.Engine.Graphics.GraphicsDevice; }", extracted)
    extracted = re.sub(r'(public static void Rect\(float x, float y, float width, float height, Color color\))\s*\{ throw new DeathOracle.UnsupportedClosure\("Excluded source member: [^"\n]+"\); \}',
                       r'\1 { DeathOracle.TrailRecording.Rect(x,y,width,height,color); }', extracted)
    extracted = re.sub(r'(public void DirectionalShake\(Vector2 dir, float time = 0.3f\))\s*\{ throw new DeathOracle.UnsupportedClosure\("Excluded source member: [^"\n]+"\); \}',
                       r'\1 { DeathOracle.GpuRecords.Add("excluded-directional-shake",dir,time); }', extracted)
    extracted = replace_guard(extracted, 'public void CreateWallSlideParticles(int dir)\n{ DeathOracle.GpuRecords.Add("excluded-wallslide-particles",dir); }')
    # Optional particles are outside this profile; the original argument/RNG evaluation still executes.
    signature = "public void Emit(ParticleType type, Vector2 position, float direction)"
    start = extracted.index(signature)
    brace = extracted.index("{", start)
    depth, end = 1, brace + 1
    while depth:
        depth += (extracted[end] == "{") - (extracted[end] == "}")
        end += 1
    extracted = extracted[:brace] + '{ DeathOracle.GpuRecords.Add("excluded-particle",type,position,direction); }' + extracted[end:]

    shared = (accepted / "Shared.cs").read_text()
    shared = replace_once(shared, "public sealed class RecordingBatch\n    {", "public sealed class RecordingBatch\n    {\n"
        "        public void Begin(params object[] arguments) => DeathOracle.TrailRecording.Begin(arguments);\n"
        "        public void End() => DeathOracle.GpuRecords.Add(\"batch-end\");\n")
    shared = replace_once(shared, "            Geometry.Draw(texture, position, clip, color, rotation, origin, scale, effects, depth);",
        "            Geometry.Draw(texture, position, clip, color, rotation, origin, scale, effects, depth);\n"
        "            DeathOracle.TrailRecording.Draw(texture,position,clip,color,rotation,origin,scale,effects);")
    execution = (accepted / "RoomCoreExecution.cs").read_text()
    execution = execution.replace('Path.GetFullPath(".audit/native-player-death-respawn")', 'Path.GetFullPath(".audit")')
    execution = replace_once(execution, 'string privateRoot = Path.GetFullPath(".audit") + Path.DirectorySeparatorChar;',
        'string privateRoot = ' + json.dumps(str(accepted.parents[3])) + ' + Path.DirectorySeparatorChar;')
    execution = replace_once(execution, "Content = Path.GetDirectoryName(path);", "Content = " + json.dumps(str(accepted)) + ";")
    output.mkdir(parents=True)
    generated = {"DashExtracted.cs": extracted, "DashShared.cs": shared, "DashExecution.cs": execution}
    for name, text in generated.items():
        (output / name).write_text(text)
    files = [output / name for name in generated]
    omitted = {"Extracted.cs", "Shared.cs", "RoomCoreExecution.cs"}
    for item in ET.fromstring((accepted / "Oracle.csproj").read_text()).findall(".//Compile"):
        name = item.attrib["Include"]
        if name not in omitted:
            files.append(accepted / name)
    support = Path(__file__).resolve().parents[1] / "tests/native/oracle/dash/TrailProfile.cs"
    files.append(support)
    for path in (accepted / "Oracle.csproj", accepted / "Extracted.cs", accepted / "Shared.cs", accepted / "RoomCoreExecution.cs", *files):
        inputs[str(path)] = file_identity(path)
    project = ('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework>'
               '<UseAppHost>false</UseAppHost><AllowUnsafeBlocks>true</AllowUnsafeBlocks><EnableDefaultCompileItems>false</EnableDefaultCompileItems>'
               '<StartupObject>DeathOracle.RoomCoreExecution</StartupObject><DefineConstants>DEATH_SOURCE_GATE;GRID_ORACLE</DefineConstants>'
               '<NuGetAudit>false</NuGetAudit></PropertyGroup><ItemGroup>' + ''.join('<Compile Include="' + escape(str(p)) + '"/>' for p in files) + '</ItemGroup></Project>')
    (output / "Oracle.csproj").write_text(project)
    (output / "NuGet.Config").write_text('<configuration><packageSources><clear/></packageSources></configuration>')
    record = {"schema": 1, "profile": "isolated-dash-trail-recording", "inputs": inputs, "original_spans": spans,
              "generated": {name: file_identity(output / name) for name in generated},
              "recording_leaves": ["SpriteBatch.Begin/End/Draw", "Draw.Rect", "Game.GraphicsDevice getter"],
              "excluded_effect_leaves": ["Level.DirectionalShake", "SlashFx.Burst", "Player.CreateWallSlideParticles", "ParticleSystem.Emit(ParticleType,Vector2,float)"],
              "claim": "Original TrailManager/CreateTrail/Dash callsites and existing sprite/hair geometry. Recording backend only; no original GPU/pixels/body parity. Legacy source profiles are untouched; native particles/audio/shake/displacement/slash remain excluded."}
    (output / "dash-profile.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def compile_recording(output, sdk):
    files = [item.attrib["Include"] for item in ET.parse(output / "Oracle.csproj").findall(".//Compile")]
    references = sorted((sdk.parent / "packs/Microsoft.NETCore.App.Ref/8.0.31/ref/net8.0").glob("*.dll"))
    if not references:
        raise ValueError("Pinned SDK reference assemblies missing")
    command = [str(sdk), str(sdk.parent / "sdk/8.0.425/Roslyn/bincore/csc.dll"), "-nologo", "-target:exe", "-unsafe", "-optimize+",
               "-define:DEATH_SOURCE_GATE,GRID_ORACLE", "-main:DeathOracle.RoomCoreExecution", "-out:" + str(output / "Oracle.dll"),
               *["-r:" + str(path) for path in references], *files]
    environment = dict(os.environ, HOME=str(output.parent / "home"), TMPDIR=str(output.parent / "tmp"), DOTNET_EnableDiagnostics="0")
    with (output / "csc.log").open("x") as log:
        result = subprocess.run(command, env=environment, stdout=log, stderr=subprocess.STDOUT)
    (output / "compiler-command.json").write_text(json.dumps(command, indent=2) + "\n")
    if result.returncode:
        raise RuntimeError("Source profile compile failed: " + str(output / "csc.log"))
    (output / "Oracle.runtimeconfig.json").write_text(json.dumps({"runtimeOptions": {"tfm": "net8.0", "framework": {
        "name": "Microsoft.NETCore.App", "version": "8.0.31"}}}) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("accepted", "manifest", "legacy-root", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--sdk", type=Path)
    args = parser.parse_args()
    record = generate(args.accepted.resolve(), args.manifest.resolve(), args.legacy_root.resolve(), args.output.resolve())
    if args.sdk:
        compile_recording(args.output.resolve(), args.sdk.resolve())
    print(json.dumps(record, indent=2))
