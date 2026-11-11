"""Run existing exact comparators with explicitly selected immutable legacy source artifacts."""

import argparse
import importlib
import json
from pathlib import Path
import subprocess

from check_native_oracle import ROOT, oracle_environment, verify_extraction
from native_oracle_sdk import sdk_path
from native_room_revision import file_identity, validate_source_state
from compare_player_presentation import compare_outputs, coverage, projection_input, mutate_output

DOMAINS = {
    "movement": ("native_trace_runner", "compare_native_traces"),
    "grid": ("native_trace_runner", "compare_grid_traces"),
    "scheduling": ("native_scheduling_trace_runner", "compare_scheduling_traces"),
    "input": ("native_input_trace_runner", "compare_input_traces"),
    "player": ("native_player_trace_runner", "compare_player_traces"),
    "hazards": ("native_hazard_trace_runner", "compare_hazard_traces"),
    "dash": ("native_dash_trace_runner", "compare_dash_traces"),
    "jumps": ("native_dash_trace_runner", "compare_jump_traces"),
    "climb": ("native_climb_trace_runner", "compare_climb_traces"),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proof", type=Path, required=True, help="Accepted legacy proof with oracles/, assets/ and presentation/")
    parser.add_argument("--source-root", type=Path, required=True, help="Explicit original source root recorded by legacy manifests")
    parser.add_argument("--native-build", type=Path, required=True)
    parser.add_argument("--expected-source-state", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    expected = json.loads(args.expected_source_state.read_text()) if args.expected_source_state else None
    before = validate_source_state(expected)
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / ".audit") or output.exists():
        parser.error("Output must be fresh and private beneath .audit")
    output.mkdir(parents=True)
    artifacts, commands = {}, []
    result = {"source_before": before, "artifacts": artifacts, "commands": commands, "domains": {}, "presentation": {},
              "claim": "current native base plus exact dirty bytes against immutable legacy extracted-source assemblies; no clean-SHA or new original-source build claim"}

    def pin(path):
        path = path.resolve()
        artifacts[str(path)] = file_identity(path)

    def oracle(directory):
        identity = verify_extraction(directory, args.source_root)
        manifest = json.loads((directory / "source-manifest.json").read_text())
        for name in ("source-manifest.json", "Extracted.cs"):
            pin(directory / name)
        for entry in manifest["extractions"]:
            pin(args.source_root / entry["source_path"])
        for path in (directory / "bin/Release/net8.0").iterdir():
            if path.is_file():
                pin(path)
        return directory / "bin/Release/net8.0/Oracle.dll", identity

    def run(label, command):
        command = list(map(str, command))
        with (output / (label + ".log")).open("x") as stream:
            subprocess.run(command, cwd=ROOT, env=oracle_environment(sdk_path(ROOT)), stdout=stream, stderr=subprocess.STDOUT, check=True)
        commands.append(command)
        return (output / (label + ".log")).read_text()

    try:
        sdk = sdk_path(ROOT)
        pin(sdk)
        for domain, (runner, comparator) in DOMAINS.items():
            native = args.native_build / runner
            fixture = ROOT / "tests/native" / (domain + ".fixtures")
            pin(native); pin(fixture)
            assembly, identity = oracle(args.proof / "oracles" / domain)
            actual = run(domain + "-native", [native, fixture])
            source = run(domain + "-source", [sdk, assembly, fixture])
            module = importlib.import_module(comparator)
            rows = module.compare(source.splitlines(), actual.splitlines(), fixture)
            result["domains"][domain] = {"comparison": rows, "source_identity": identity}
        reference = args.proof / "oracle"
        assembly, identity = oracle(reference)
        manifest = json.loads((reference / "source-manifest.json").read_text())
        visual_source = Path(manifest["source_directory"])
        metadata = args.proof / "assets/player.txt"
        for path in (metadata, reference / "atlas.json", reference / "bank.json", visual_source / "Sprites.xml"):
            pin(path)
        for name in ("presentation", "climb", "jumps", "dash"):
            native = args.native_build / "native_presentation_trace_runner"
            fixture = ROOT / "tests/native" / (name + ".fixtures")
            pin(native); pin(fixture)
            actual = run(name + "-visual-native", [native, fixture, metadata])
            common = projection_input(actual, fixture.read_text(), require_all=name == "presentation")
            projection = output / (name + ".input.tsv")
            projection.write_text(common)
            source_path = output / (name + ".source.tsv")
            command = [sdk, assembly, reference / "atlas.json", visual_source / "Sprites.xml", reference, projection, source_path]
            run(name + "-visual-source", command)
            source = source_path.read_text()
            entry = {"records": compare_outputs(actual, source), "source_identity": identity,
                     "input": file_identity(projection), "source_output": file_identity(source_path)}
            if name == "presentation":
                entry["coverage"] = coverage(source)
                mutant = mutate_output(actual, "R", 37, "999999", case="long_idle_rng")
                if projection_input(mutant, fixture.read_text()) != common:
                    raise ValueError("Native visual mutation reached source input")
                try:
                    compare_outputs(mutant, source)
                except ValueError:
                    entry["rng_mutation"] = "rejected; source input/output unchanged"
                else:
                    raise ValueError("Native RNG ordinal mutation passed")
            result["presentation"][name] = entry
        native_geometry = args.native_build / "native_presentation_geometry_runner"
        geometry = args.proof / "presentation/geometry-build/bin/Release/net8.0"
        pin(native_geometry)
        for path in geometry.iterdir():
            if path.is_file(): pin(path)
        actual = run("geometry-native", [native_geometry, metadata])
        source = run("geometry-source", [sdk, geometry / "Geometry.dll", reference / "atlas.json", reference / "bank.json"])
        result["geometry_records"] = compare_outputs(actual, source)
        result["status"] = "passed"
    except Exception as error:
        result["status"] = "failed"
        result["error"] = str(error)
        raise
    finally:
        result["source_after"] = validate_source_state(before)
        for path, identity in artifacts.items():
            if file_identity(Path(path)) != identity:
                raise ValueError("Immutable input/oracle/native artifact drift: " + path)
        (output / "checks.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "domains": list(result["domains"]), "presentation": list(result["presentation"]), "geometry_records": result["geometry_records"]}))


if __name__ == "__main__":
    main()
