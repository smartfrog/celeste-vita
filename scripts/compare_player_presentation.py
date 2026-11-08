"""Validate the read-only common-input boundary and exact visual output records."""

from collections import Counter
import struct

from fixture_protocol import IDENTIFIER, float_bits, integer

PROJECTION_FIELDS = (
    "record", "case", "tick", "phase", "scaled_delta", "x", "y", "speed_x", "speed_y", "facing", "state",
    "effective_move_x", "raw_x", "raw_y", "climb_move", "wall_slide", "dash_attacking", "dashes", "ground", "ducking", "tired",
    "dash_x", "dash_y", "solid_body_probes", "solid_point_probes", "jump_thru_body_probes",
)
PHASES = {"scene_tick", "ground", "duck_turn", "components", "jump", "duck", "stand", "fast_fall", "landing",
          "select", "hair_color", "after_update", "render"}
VISUAL_COLUMNS = {"R": 40, "D": 17, "V": 12}


def fixture_ticks(text):
    result, current, tick = {}, None, 0
    for line in text.splitlines():
        f = line.split("=>", 1)[0].split()
        if not f or f[0].startswith("#"):
            continue
        if f[0] == "case":
            current, tick = f[1], 0
        elif f[0] in {"tick", "frames", "point", "die"}:
            if current is None:
                raise ValueError("Fixture operation has no case")
            count = integer(f[1], 1, 10000) if f[0] == "frames" else 1
            for _ in range(count):
                tick += 1
                if f[0] in {"tick", "frames"}:
                    offset = 2 if f[0] == "frames" else 1
                    result[current, tick] = (float_bits(f[offset]), f[offset + 1], f[offset + 2])
    return result


def validate_phase_order(phases):
    if phases == ["render"]:
        return
    if phases[:2] != ["scene_tick", "ground"] or phases[-1:] != ["render"]:
        raise ValueError("Invalid source phase grammar")
    middle = phases[2:-1]
    if middle[:1] == ["duck_turn"]:
        middle = middle[1:]
    if middle[:1] != ["components"] or middle.count("select") != 1:
        raise ValueError("Component/selector source phase order changed")
    index = middle.index("select")
    if any(phase not in {"jump", "duck", "stand", "fast_fall", "landing"} for phase in middle[1:index]):
        raise ValueError("Unexpected mutable-gameplay event in presentation input")
    if middle[index + 1:] not in ([], ["hair_color", "after_update"]):
        raise ValueError("Hair post-update source phase order changed")


def projection_input(native_text, fixtures, require_all=False):
    allowed = fixture_ticks(fixtures)
    selected, group, phases = [], None, []
    previous = {}
    visited = set()
    for line in native_text.splitlines():
        f = line.split("\t")
        if f[0] != "P":
            if f[0] not in VISUAL_COLUMNS:
                raise ValueError("Unrecognized native output record")
            continue
        if len(f) != len(PROJECTION_FIELDS) or not IDENTIFIER.fullmatch(f[1]) or f[3] not in PHASES:
            raise ValueError("Projection whitelist/schema violation")
        tick = integer(f[2], 1, 10000)
        key = f[1], tick
        if key not in allowed:
            raise ValueError("Projection is not declared by the actual input fixture")
        if (f[4], f[12], f[13]) != allowed[key]:
            raise ValueError("Projected delta/raw input differs from the actual fixture")
        if key != group:
            if group is not None:
                validate_phase_order(phases)
            if tick <= previous.get(f[1], 0):
                raise ValueError("Projection ticks are not strictly ordered")
            previous[f[1]], group, phases = tick, key, []
            visited.add(key)
        for index in (4, 5, 6, 7, 8, 21, 22):
            float_bits("@" + f[index])
        if struct.unpack(">f", bytes.fromhex(f[4]))[0] < 0:
            raise ValueError("Negative projection delta")
        if f[9] not in {"-1", "1"}:
            raise ValueError("Invalid projected facing")
        integer(f[10], 0, 2)
        for index in (11, 12, 13, 14, 15):
            integer(f[index], -1, 1)
        for index in range(16, 21):
            integer(f[index], 0, 1)
        for index, count in ((23, 2), (24, 4), (25, 2)):
            if len(f[index]) != count or set(f[index]) - {"0", "1"}:
                raise ValueError("Invalid exact point/full-body probe projection")
        phases.append(f[3])
        selected.append(line)
    if group is None:
        raise ValueError("Empty presentation projection input")
    validate_phase_order(phases)
    if require_all and visited != set(allowed):
        raise ValueError("Presentation fixture ticks were omitted from the common input")
    return "\n".join(selected) + "\n"


def visual_records(text):
    result = []
    for line in text.splitlines():
        f = line.split("\t")
        if f[0] == "P":
            continue
        if f[0] not in VISUAL_COLUMNS or len(f) != VISUAL_COLUMNS[f[0]]:
            raise ValueError("Invalid visual output schema")
        result.append(line)
    if not result:
        raise ValueError("Empty visual output cannot establish parity")
    return result


def compare_outputs(native, source):
    a, b = visual_records(native), visual_records(source)
    if len(a) != len(b):
        raise ValueError(f"Different filtered visual record counts: {len(a)} != {len(b)}")
    for index, (actual, expected) in enumerate(zip(a, b, strict=True)):
        if actual != expected:
            raise ValueError(f"Visual output mismatch at filtered record {index}: {actual.split(chr(9))[:4]}")
    return len(a)


def mutate_output(native, record, column, value, case=None):
    lines = native.splitlines()
    for index, line in enumerate(lines):
        fields = line.split("\t")
        if fields[0] == record and (case is None or fields[1] == case):
            fields[column] = value
            lines[index] = "\t".join(fields)
            return "\n".join(lines) + "\n"
    raise ValueError("Required independent mutation target is missing")


def coverage(source):
    rows = [line.split("\t") for line in visual_records(source)]
    poses = [f for f in rows if f[0] == "R"]
    by_case = {}
    for f in poses:
        by_case.setdefault(f[1], []).append(f)
    families = {
        "run_reversal": {"runSlow", "runFast", "flip"}, "jump_apex_land": {"jumpFast", "fallFast"},
        "duck_turn": {"duck"}, "fastfall_stumble": {"fallFast", "runStumble"}, "wallslide": {"wallslide"},
        "climb_up_lookback": {"climbUp", "climbLookBackStart", "climbLookBack"}, "climb_dangle": {"dangling"},
        "tired_boost": {"jumpSlow"}, "dash_freeze_tail_refill": {"dash"},
        "long_idle_rng": {"idle", "idleA", "idleB", "idleC"}, "push": {"push"}, "look_up": {"lookUp"},
        "edge_front": {"edge"}, "edge_back": {"edgeBack"}, "jump_slow_apex": {"jumpSlow", "fallSlow"}, "skid": {"skid"},
    }
    for name, expected in families.items():
        actual = {f[4] for f in by_case.get(name, [])}
        if not expected <= actual:
            raise ValueError(f"Independent source animation coverage missing: {name}: {expected - actual}")
    events = {f[3] for f in poses}
    if not {"duck_turn", "stand", "duck", "fast_fall", "landing", "jump"} <= events:
        raise ValueError("Independent source cosmetic-event coverage is incomplete")
    idle = by_case["long_idle_rng"]
    if max(int(f[37]) for f in idle) < 20 or max(struct.unpack(">f", bytes.fromhex(f[14]))[0] for f in idle) <= 3:
        raise ValueError("Long-idle RNG/callback coverage is missing")
    dash = by_case["dash_freeze_tail_refill"]
    if sum(f[3] == "render" for f in dash) <= sum(f[3] == "components" for f in dash):
        raise ValueError("Freeze did not skip presentation updates while rendering continued")
    colors = {tuple(f[21:25]) for f in dash}
    if ("255", "255", "255", "255") not in colors or ("172", "50", "50", "255") not in colors or len(colors) < 4:
        raise ValueError("Depleted/refill source hair-color coverage is missing")
    if not any(f[0] == "D" and f[1] == "tired_boost" and f[3] == "20" and f[12:16] == ["255", "0", "0", "255"] for f in rows):
        raise ValueError("Tired body tint was not drawn by the source")
    return {"families": 8, "cases": len(families), "source_pose_records": len(poses),
            "record_counts": dict(Counter(f[0] for f in rows)), "max_idle_rng_ordinal": max(int(f[37]) for f in idle)}


def main():
    import argparse
    import hashlib
    import json
    from pathlib import Path
    import subprocess

    from check_native_oracle import ROOT, oracle_environment, verify_extraction
    from native_room_revision import source_state
    from native_room_textures import atlas_metadata
    from prepare_room_visuals import MEMBERS
    from prepare_player_presentation_oracle import prepare, SOURCE_PINS, support_hashes, RECIPE_FILES

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--geometry-native", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True, help="Immutable private source-closed FNA-inclusive witness")
    parser.add_argument("--player-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / ".audit") or output.exists():
        parser.error("Output must be fresh and private beneath .audit")
    revision, changes = source_state(ROOT)
    if changes:
        parser.error("Exact committed source/config is required: " + "; ".join(changes))
    output.mkdir(parents=True)
    commands = []
    result = {"revision": revision, "source_before": {"revision": revision, "changes": changes},
              "scope": "Default-inventory Normal/Climb/Dash presentation at read-only kernel projections; separate physics oracles remain required",
              "diagnostic_seed": 0, "original_startup_rng_parity": False, "commands": commands, "fixtures": []}

    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def run(label, command):
        command = list(map(str, command))
        with (output / (label + ".log")).open("xb") as log:
            completed = subprocess.run(command, cwd=ROOT, env=oracle_environment(sdk), stdout=log, stderr=subprocess.STDOUT)
        commands.append({"command": command, "exit_code": completed.returncode, "log": label + ".log"})
        if completed.returncode:
            raise RuntimeError("Source/native command failed: " + str(output / (label + ".log")))

    sdk = ROOT / ".audit/native-oracle/tools/dotnet-8.0.425/dotnet"
    try:
        identity = verify_extraction(args.oracle)
        manifest = json.loads((args.oracle / "source-manifest.json").read_text())
        recipes = {name: digest(ROOT / name) for name in RECIPE_FILES}
        if manifest["support_sha256"] != support_hashes() or manifest["recipe_sha256"] != recipes:
            raise ValueError("Oracle was not prepared by the exact current tracked recipe/harness")
        for entry in manifest["extractions"]:
            if entry["source_sha256"] != SOURCE_PINS[entry["file"]]:
                raise ValueError("Unrecognized original method source")
        visual_source = Path(manifest["source_directory"])
        provenance = json.loads((visual_source / "provenance.json").read_text())
        if digest(visual_source / "provenance.json") != manifest["source_provenance_sha256"]:
            raise ValueError("Pinned private input/source provenance changed")
        reference = output / "reference-build"
        rebuilt_identity = prepare(visual_source, reference)
        if rebuilt_identity != identity:
            raise ValueError("Freshly reconstructed unchanged source bundle differs")
        for name in ("Celeste.exe", "FNA.dll", "mscorlib.dll"):
            if digest(Path(provenance["inputs"][name]["path"])) != MEMBERS[name]:
                raise ValueError("Original executable/framework member changed: " + name)
        for name in ("Sprites.xml", "Gameplay.meta"):
            member = "Content/Graphics/" + ("Atlases/" if name.endswith(".meta") else "") + name
            if digest(visual_source / name) != MEMBERS[member]:
                raise ValueError("Original sprite/atlas metadata changed")
        atlas = atlas_metadata((visual_source / "Gameplay.meta").read_bytes())
        if json.loads((args.oracle / "atlas.json").read_text()) != {key: list(value) for key, value in atlas.items()}:
            raise ValueError("Reference atlas differs from independent original metadata")
        if digest(args.oracle / "bank.json") != digest(reference / "bank.json"):
            raise ValueError("Fresh original source-exported frame bank changed")
        player_provenance = json.loads((args.player_dir / "provenance.json").read_text())
        if player_provenance["bank_sha256"] != digest(reference / "bank.json"):
            raise ValueError("Native assets came from a different source frame bank")
        for name, expected in player_provenance["files"].items():
            if digest(args.player_dir / name) != expected:
                raise ValueError("Prepared native player asset changed: " + name)
        result.update(source_identity=identity, source_support=manifest["support_sha256"], recipe_sha256=recipes,
                      caller_sources=manifest["caller_anchors"], original_inputs=provenance["inputs"], native_sha256=digest(args.native),
                      source_assembly_sha256=digest(reference / "bin/Release/net8.0/Oracle.dll"),
                      source_bank_sha256=digest(reference / "bank.json"), player_assets=player_provenance["files"],
                      reference_commands=json.loads((reference / "commands-run.json").read_text()), player_metadata_sha256=digest(args.player_dir / "player.txt"))
        geometry = output / "geometry-build"
        geometry.mkdir()
        (geometry / "NuGet.Config").write_bytes((reference / "NuGet.Config").read_bytes())
        (geometry / "Geometry.csproj").write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
<PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework><EnableDefaultCompileItems>false</EnableDefaultCompileItems><UseAppHost>false</UseAppHost><NuGetAudit>false</NuGetAudit></PropertyGroup>
<ItemGroup><Reference Include="Oracle"><HintPath>{reference / 'bin/Release/net8.0/Oracle.dll'}</HintPath></Reference><Compile Include="{ROOT / 'tests/native/oracle/presentation/GeometryRunner.cs'}"/></ItemGroup></Project>''')
        run("geometry-restore", [sdk, "restore", geometry / "Geometry.csproj", "--configfile", geometry / "NuGet.Config"])
        run("geometry-build", [sdk, "build", geometry / "Geometry.csproj", "--no-restore", "-c", "Release", "-p:UseSharedCompilation=false", "--disable-build-servers"])
        run("geometry-native", [args.geometry_native, args.player_dir / "player.txt"])
        run("geometry-source", [sdk, geometry / "bin/Release/net8.0/Geometry.dll", reference / "atlas.json", reference / "bank.json"])
        result["independent_geometry_contract"] = {
            "filtered_exact_records": compare_outputs((output / "geometry-native.log").read_text(), (output / "geometry-source.log").read_text()),
            "cases": 12, "scope": "Independent fixed caller parameters: both facings, fractional roots, signed squash, body/bangs/tail origins, zero/nonzero rotation; no native visual outputs supplied to the source",
            "native_sha256": digest(args.geometry_native), "source_driver_sha256": digest(ROOT / "tests/native/oracle/presentation/GeometryRunner.cs")}

        def replay(label, projection_path, source_path):
            run(label, [sdk, reference / "bin/Release/net8.0/Oracle.dll", reference / "atlas.json",
                        visual_source / "Sprites.xml", reference, projection_path, source_path])

        def prove_mutation(label, mutant, fixtures, projection_path, source_path):
            (output / (label + ".mutated-native.tsv")).write_text(mutant)
            mutation_input = output / (label + ".projections.tsv")
            mutation_input.write_text(projection_input(mutant, fixtures))
            if mutation_input.read_bytes() != projection_path.read_bytes():
                raise ValueError("Native visual output reached the original source input")
            mutation_reference = output / (label + ".source.tsv")
            replay(label + "-mutation-source", mutation_input, mutation_reference)
            if mutation_reference.read_bytes() != source_path.read_bytes():
                raise ValueError("Native visual output mutation changed original source output")
            try:
                compare_outputs(mutant, mutation_reference.read_text())
            except ValueError as error:
                return {"mutation": label, "comparison": "rejected", "reference_unchanged": True, "reason": str(error)}
            raise ValueError("Changed native visual output passed comparison")

        for name in ("presentation", "climb", "jumps", "dash"):
            native_path, projection_path, source_path = (output / (name + suffix) for suffix in (".native.tsv", ".projections.tsv", ".source.tsv"))
            run(name + "-native", [args.native, ROOT / "tests/native" / (name + ".fixtures"), args.player_dir / "player.txt"])
            native_path.write_bytes((output / (name + "-native.log")).read_bytes())
            native = native_path.read_text()
            fixtures = (ROOT / "tests/native" / (name + ".fixtures")).read_text()
            common = projection_input(native, fixtures, require_all=name == "presentation")
            projection_path.write_text(common)
            replay(name + "-source", projection_path, source_path)
            source = source_path.read_text()
            entry = {"fixture": name, "filtered_exact_records": compare_outputs(native, source),
                     "fixture_sha256": digest(ROOT / "tests/native" / (name + ".fixtures")),
                     "native_sha256": digest(native_path), "projection_sha256": digest(projection_path), "source_sha256": digest(source_path), "native_visual_output_reference_input_records": 0}
            if name == "presentation":
                entry["independent_source_coverage"] = coverage(source)
                mutant = mutate_output(native, "R", 37, "999999", case="long_idle_rng")
                entry["long_idle_rng_mutation"] = prove_mutation("long-idle-rng", mutant, fixtures, projection_path, source_path)
            if name == "climb":
                entry["output_mutation_proofs"] = [prove_mutation(kind, mutate_output(native, kind, 4, "tampered"), fixtures, projection_path, source_path) for kind in ("R", "D", "V")]
            result["fixtures"].append(entry)
        result["status"] = "source-closed-presentation-parity-and-output-independence-passed"
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        try:
            final_revision, final_changes = source_state(ROOT)
            result["source_after"] = {"revision": final_revision, "changes": final_changes}
            if final_revision != revision or final_changes:
                result["status"] = "invalidated-by-source-change"
        except Exception as error:
            result["source_after"] = {"error": {"type": type(error).__name__, "message": str(error)}}
            result["status"] = "invalidated-by-source-check-failure"
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    if result["status"] != "source-closed-presentation-parity-and-output-independence-passed":
        raise RuntimeError("Source/config changed during presentation verification")
    print(json.dumps({"status": result["status"], "revision": revision, "fixtures": result["fixtures"]}, indent=2))


if __name__ == "__main__":
    main()
