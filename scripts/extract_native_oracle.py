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
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / ".audit/ilspy")
    parser.add_argument("--domain", choices=("movement", "scheduling"), default="movement")
    args = parser.parse_args()
    actual = hashlib.sha256((args.source / "inputs/Celeste.exe").read_bytes()).hexdigest()
    if actual != INPUT_SHA:
        raise RuntimeError(f"Unexpected reference input SHA256: {actual}")
    output = ROOT / ".audit/native-oracle"
    if args.domain == "scheduling":
        output /= "scheduling"
    output.mkdir(parents=True, exist_ok=True)
    manifest = {"input_sha256": actual, "version": "PC 1.4.0.0", "extractions": []}

    def extract(filename, ranges):
        source = (args.source / "cs" / filename).read_bytes()
        if hashlib.sha256(source).hexdigest() != SOURCE_HASHES[filename]:
            raise RuntimeError(f"Changed decompilation input: {filename}")
        lines = source.decode().splitlines(keepends=True)
        blocks = ["".join(lines[start - 1:end]) for start, end in ranges]
        manifest["extractions"].append({"file": filename, "source_sha256": hashlib.sha256(source).hexdigest(),
                                         "lines_inclusive": ranges,
                                         "blocks_sha256": [hashlib.sha256(b.encode()).hexdigest() for b in blocks]})
        return "\n".join(blocks)

    if args.domain == "movement":
        header = "using System;\nusing System.Collections.Generic;\nusing Microsoft.Xna.Framework;\nusing Monocle;\n"
        content = header + "namespace Celeste { public partial class Actor {\n"
        content += extract("Celeste.Actor.cs", [(186, 281)]) + "\n} }\n"
        content += "namespace Celeste {\n" + extract("Celeste.CollisionData.cs", [(5, 18)]) + "\n}\n"
        content += "namespace Monocle { public static class Collide {\n"
        content += extract("Monocle.Collide.cs", [(8, 28), (51, 70)]) + "\n} }\n"
        content += "namespace Monocle { public partial class Entity {\n"
        content += extract("Monocle.Entity.cs", [(682, 690), (728, 738)]) + "\n} }\n"
        content += "namespace Monocle { public abstract partial class Collider {\n"
        content += extract("Monocle.Collider.cs", [(8, 22), (205, 251), (255, 258)]) + "\n} }\n"
        content += "namespace Monocle { public class Hitbox : Collider {\n"
        content += extract("Monocle.Hitbox.cs", [(7, 98), (180, 183)]) + "\n} }\n"
    else:
        content = "using System;\nusing System.Collections;\nusing System.Collections.Generic;\nnamespace Monocle {\n"
        content += extract("Monocle.Coroutine.cs", [(6, 102)]) + "\n"
        content += extract("Monocle.StateMachine.cs", [(6, 202)]) + "\n}\n"
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
    (output / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    maintained = ROOT / "tests/native/oracle"
    if args.domain == "scheduling":
        maintained /= "scheduling"
    (output / "Oracle.csproj").write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework>
    <EnableDefaultCompileItems>false</EnableDefaultCompileItems>
    <UseAppHost>false</UseAppHost><CheckForOverflowUnderflow>false</CheckForOverflowUnderflow>
    <NuGetAudit>false</NuGetAudit>
  </PropertyGroup>
  <ItemGroup>
    <Compile Include="Extracted.cs" />
    <Compile Include="{maintained / 'Shims.cs'}" />
    <Compile Include="{maintained / 'Runner.cs'}" />
  </ItemGroup>
</Project>
''')
    (output / "NuGet.Config").write_text('<configuration><packageSources><clear /></packageSources></configuration>\n')
    print(f"Extracted {len(manifest['extractions'])} source files to {output}")


if __name__ == "__main__":
    main()
