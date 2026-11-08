#!/usr/bin/env python3
"""Extract unchanged private method/property ranges; never export the game runtime."""

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT_SHA = "fd73f8a2311fa5737ded550cbad4b75c85b7686b36432f59185e940fcb65fcfe"
SOURCE_HASHES = {
    "Celeste.Actor.cs": "0a67f10b020c880837a87a3acf1dc2c3d14553743c8d1244b232eda09470a296",
    "Celeste.CollisionData.cs": "d979c71e59e4d5fce02c37008ae93181d169ecfb80dc83db236cc8111e8cb2b8",
    "Monocle.Collide.cs": "503d4ad4db3da34a2b2599828ce2b84385854cd7d766287742e26765fb42488a",
    "Monocle.Entity.cs": "771cb46f515138a2d4f55f03ed2234e3a065ee37ed678036e0d4981bb3d35d6b",
    "Monocle.Collider.cs": "eaad9d3ccf63d710519c6e8eee3e025b8f4922f1cb4a0dc03f20bfee0dd25dec",
    "Monocle.Hitbox.cs": "7bf2a0e6dbac16b79be9ef2d57a0d732a95a8aaf89934dc4dae7b29f070d51d6",
    "Monocle.Coroutine.cs": "d4cd81b29b8535146931606aeafac396ce739df00a24763a1b51c337325fae33",
    "Monocle.StateMachine.cs": "92091f4cdf54a87cab34832d33698d0d5dd33be4c11d8e61c42d1be07e5bdf4e",
    "Monocle.VirtualButton.cs": "ae7c19ab7a08ddf2c2f5e8e31e2305ba9334f149573f9b01d78cac16291e8cbb",
    "Celeste.Player.cs": "47413e0a774802c6dac9baff96aca6f6fda01edd8f28b1dd9bb86e0075cd4d9a",
    "Celeste.PlayerInventory.cs": "fca9bed434019cba9bbe937e18e5d170c420cbbe51740926a4e9d70aeac7ec5f",
    "Monocle.Grid.cs": "3bc25f4b4abea06d93297abb74a4907b4a9eccab8fad212bd997e3922191263e",
    "Celeste.LevelData.cs": "ad1957dcd4f3919396e6db60095f1da7ab767d0c37e51bad90fbd9603809b239",
    "Celeste.SolidTiles.cs": "6deb8cd77d6b6ffdd28dccb637ce73530f453da315f70947480a19c139598735",
    "Celeste.LevelLoader.cs": "b35b6f5c0479b0eccaf5d5a1c6affaca388c6733a585248b910208a354c6af7f",
    "Celeste.MapData.cs": "e820408a848bfee05aba0d98cf698cf5061438ac3cf1f6640f44cf7db1d8a898",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / ".audit/ilspy")
    parser.add_argument("--domain", choices=("movement", "scheduling", "input", "player", "grid"), default="movement")
    args = parser.parse_args()
    actual = hashlib.sha256((args.source / "inputs/Celeste.exe").read_bytes()).hexdigest()
    if actual != INPUT_SHA:
        raise RuntimeError(f"Unexpected reference input SHA256: {actual}")
    output = ROOT / ".audit/native-oracle"
    if args.domain != "movement":
        output /= args.domain
    output.mkdir(parents=True, exist_ok=True)
    manifest = {"input_sha256": actual, "version": "PC 1.4.0.0", "extractions": []}

    def extract(filename, ranges):
        source_path = args.source / "cs" / filename
        if filename in {"Celeste.LevelLoader.cs", "Celeste.MapData.cs"}:
            source_path = ROOT / ".audit/native-static-tilemap" / filename
        source = source_path.read_bytes()
        if hashlib.sha256(source).hexdigest() != SOURCE_HASHES[filename]:
            raise RuntimeError(f"Changed decompilation input: {filename}")
        lines = source.decode().splitlines(keepends=True)
        blocks = ["".join(lines[start - 1:end]) for start, end in ranges]
        manifest["extractions"].append({"file": filename, "source_sha256": hashlib.sha256(source).hexdigest(),
                                         "lines_inclusive": ranges,
                                         "blocks_sha256": [hashlib.sha256(b.encode()).hexdigest() for b in blocks]})
        return "\n".join(blocks)

    if args.domain in {"movement", "player", "grid"}:
        header = "using System;\nusing System.Collections;\nusing System.Collections.Generic;\nusing Microsoft.Xna.Framework;\nusing Monocle;\n"
        if args.domain == "player":
            header += "using Microsoft.Xna.Framework.Input;\n"
        content = header + "namespace Celeste { public partial class Actor {\n"
        content += extract("Celeste.Actor.cs", [(186, 281)]) + "\n} }\n"
        content += "namespace Celeste {\n" + extract("Celeste.CollisionData.cs", [(5, 18)]) + "\n}\n"
        content += "namespace Monocle { public static class Collide {\n"
        content += extract("Monocle.Collide.cs", [(8, 101)] if args.domain == "player" else [(8, 28), (51, 70)]) + "\n} }\n"
        content += "namespace Monocle { public partial class Entity {\n"
        content += extract("Monocle.Entity.cs", [(682, 690), (728, 738)]) + "\n} }\n"
        content += "namespace Monocle { public abstract partial class Collider {\n"
        collider_ranges = [(8, 22), (205, 253 if args.domain in {"grid", "player"} else 251), (255, 258)]
        content += extract("Monocle.Collider.cs", collider_ranges) + "\n} }\n"
        content += "namespace Monocle { public class Hitbox : Collider {\n"
        content += extract("Monocle.Hitbox.cs", [(7, 98), (180, 188 if args.domain in {"grid", "player"} else 183)]) + "\n} }\n"
        if args.domain in {"grid", "player"}:
            content += "namespace Monocle { public class Grid : Collider {\n"
            content += extract("Monocle.Grid.cs", [(8, 56), (76, 129), (315, 346), (418, 429), (481, 484)]) + "\n} }\n"
        if args.domain == "grid":
            content += "namespace Celeste { public partial class LevelData {\n"
            content += extract("Celeste.LevelData.cs", [(76, 76), (113, 138)]) + "\n} } } } }\n"
            content += "namespace Celeste { public partial class MapData {\n"
            content += extract("Celeste.MapData.cs", [(47, 47)]) + "\npublic void ComputeBounds() {\n"
            content += extract("Celeste.MapData.cs", [(192, 235)]) + "\n} }\n"
            content += "public class MaskLoader { public VirtualMap<char> Build(MapData mapData) {\n"
            content += extract("Celeste.LevelLoader.cs", [(95, 266)]) + "\nreturn virtualMap2; } }\n"
            content += "public class SolidTiles : Solid { public Grid Grid; public SolidTiles(VirtualMap<char> data) {\n"
            content += extract("Celeste.SolidTiles.cs", [(26, 48)]) + "\n} } }\n"
            content = "using System.Text.RegularExpressions;\n" + content
        if args.domain == "player":
            content += "namespace Monocle { public partial class Entity {\n"
            content += extract("Monocle.Entity.cs", [(531, 540), (551, 581), (648, 658), (762, 776)]) + "\n} }\n"
            content += "namespace Monocle {\n"
            content += extract("Monocle.Coroutine.cs", [(6, 102)]) + "\n"
            content += extract("Monocle.StateMachine.cs", [(6, 202)]) + "\n"
            content += extract("Monocle.VirtualButton.cs", [(5, 163)]) + "\n}\n"
            content += "namespace Celeste {\n" + extract("Celeste.PlayerInventory.cs", [(6, 37)]) + "\n"
            content += "public partial class Player : Actor {\n"
            content += extract("Celeste.Player.cs", [(605, 613), (934, 954), (956, 1044), (1048, 1088),
                                                    (1092, 1102), (2353, 2362), (2436, 2478), (2521, 2546),
                                                    (2824, 2832), (2910, 2929), (3135, 3473), (3531, 3550),
                                                    (3557, 3843), (4179, 4189)])
            content += "\npublic void SourceGround() {\n"
            content += extract("Celeste.Player.cs", [(1431, 1431), (1437, 1437), (1499, 1541)]) + "\n}\n"
            content += "public void SourcePreamble() {\n"
            content += extract("Celeste.Player.cs", [(1542, 1550), (1555, 1682)]) + "\n}\n"
            for method, ranges in [("SourceBoost", [(1787, 1790)]), ("SourceUnduck", [(1795, 1798)]),
                                   ("SourceHorizontal", [(1799, 1802)]), ("SourceVertical", [(1803, 1806)])]:
                content += f"public void {method}() {{\n" + extract("Celeste.Player.cs", ranges) + "\n}\n"
            content += "public void SourceHazards() {\n"
            content += extract("Celeste.Player.cs", [(1898, 1914)]) + "\n}\n"
            content += "public void SourceComplete() {\n" + extract("Celeste.Player.cs", [(1944, 1945)]) + "\n}\n} }\n"
    elif args.domain == "scheduling":
        content = "using System;\nusing System.Collections;\nusing System.Collections.Generic;\nnamespace Monocle {\n"
        content += extract("Monocle.Coroutine.cs", [(6, 102)]) + "\n"
        content += extract("Monocle.StateMachine.cs", [(6, 202)]) + "\n}\n"
    else:
        content = "using Microsoft.Xna.Framework.Input;\nnamespace Monocle {\n"
        content += extract("Monocle.VirtualButton.cs", [(5, 163)]) + "\n}\n"
    (output / "Extracted.cs").write_text(content)
    manifest["stub_boundaries"] = [
        "Two-float Vector2 addition/multiplication; no FNA runtime",
        "Entity position, collider ownership and Collidable fields only",
        "Explicit ordered Scene.Tracker Solid/JumpThru lists; no game scene/tracker initialization",
        "Collider dispatch supports Hitbox only, otherwise throws",
        "Platform/Solid/JumpThru identity shells; no platform movement",
        "Synthetic fixture callbacks, no Player logic",
    ]
    manifest["claim"] = "Extracted-method compatibility only, not original CIL execution or full gameplay"
    if args.domain == "scheduling":
        manifest["stub_boundaries"] = [
            "Component active/visible/entity attachment and synthetic RemoveSelf counter only",
            "Entity.Scene and empty Scene; explicit Engine float32 delta fields",
            "Synthetic IEnumerator scripts and callbacks, outside extracted source",
            "Private-field inspection for trace instrumentation only, no game execution",
            "Calc.Log and Calc.GetMethod throw; diagnostic and reflection methods retained unchanged but excluded",
        ]
    elif args.domain == "input":
        manifest["stub_boundaries"] = [
            "Stable pre-resolved Binding held/pressed/released booleans; no hardware, threshold or gamepad mapping",
            "MInput.Disabled and a sampled debug-key-held bool; Keys has one synthetic identity",
            "VirtualInput abstract Update only; no input registration or engine lifecycle",
            "Engine.DeltaTime is an explicit supplied float32; no full frame clock or freeze policy",
            "Private-field inspection only in the runner, outside the unchanged extracted class",
        ]
    elif args.domain == "player":
        manifest["stub_boundaries"] = [
            "Linked accepted Actor/Hitbox, scheduling and sampled-button shims; explicit scalar Vector2/MathHelper/Calc operations",
            "Unchanged full NormalUpdate, Jump, collisions, guards/properties and source frame blocks; synthetic driver calls preamble, scheduler, postamble, validated-empty hazards",
            "Default inventory, ordinary gravity/core, zero LiftSpeed; no other-state entry or arbitrary timer snapshots",
            "Static ordered Solid/JumpThru only, explicit Safe; no platform gameplay callbacks, movers, blockers, water, hazards, triggers, carry or assists",
            "Unsupported shells throw; validated-absent collections empty; presentation shells inert",
            "Bounds enforcement disabled, bounds retained for ClimbBoundsCheck; stats/replay services excluded, source TotalJumps increments an isolated counter",
        ]
    elif args.domain == "grid":
        manifest["stub_boundaries"] = [
            "Accepted Actor/Hitbox shells with target Grid dispatch; other shape combinations throw",
            "Rectangle uses strict integer overlap; dense checked VirtualMap storage throws outside valid cells",
            "Raw map scalars/text supplied by a synthetic JSON driver; relevant LevelData constructor cases unchanged",
            "MapData bounds, complete LevelLoader 95-266 and SolidTiles 26-48 unchanged; no runtime loading, rendering or autotiling",
            "Dense AnyInSegmentAtTile always scans valid segments; default char zero makes omitted empty segments collision-equivalent",
        ]
    (output / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    maintained = ROOT / "tests/native/oracle"
    if args.domain != "movement":
        maintained /= args.domain
    extra = ""
    if args.domain == "player":
        extra = "\n".join(f'    <Compile Include="{ROOT / "tests/native/oracle" / name / "Shims.cs"}" />'
                          for name in ("scheduling", "input"))
        extra += f'\n    <Compile Include="{ROOT / "tests/native/oracle/Shims.cs"}" />'
        extra += f'\n    <Compile Include="{ROOT / "tests/native/oracle/grid/Shims.cs"}" />'
    elif args.domain == "grid":
        extra = f'    <Compile Include="{ROOT / "tests/native/oracle/Shims.cs"}" />'
        extra += f'\n    <Compile Include="{ROOT / "tests/native/oracle/Runner.cs"}" />'
    (output / "Oracle.csproj").write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework>
    <EnableDefaultCompileItems>false</EnableDefaultCompileItems>
    <UseAppHost>false</UseAppHost><CheckForOverflowUnderflow>false</CheckForOverflowUnderflow>
    <NuGetAudit>false</NuGetAudit>
    <DefineConstants>{"PLAYER_ORACLE;GRID_ORACLE" if args.domain == "player" else "GRID_ORACLE" if args.domain == "grid" else ""}</DefineConstants>
  </PropertyGroup>
  <ItemGroup>
    <Compile Include="Extracted.cs" />
    <Compile Include="{maintained / 'Shims.cs'}" />
    <Compile Include="{maintained / 'Runner.cs'}" />
{extra}
  </ItemGroup>
</Project>
''')
    (output / "NuGet.Config").write_text('<configuration><packageSources><clear /></packageSources></configuration>\n')
    print(f"Extracted {len(manifest['extractions'])} source files to {output}")


if __name__ == "__main__":
    main()
