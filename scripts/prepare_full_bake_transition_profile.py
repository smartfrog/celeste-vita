"""Prepare and run a separate pinned full-terrain, two-room SOURCE CPU contract."""

import argparse
import json
from pathlib import Path
from xml.sax.saxutils import escape

from native_room_revision import canonical_digest, file_identity, verify_file_identities
from prepare_dash_trail_oracle import compile_recording, replace_once
from prepare_native_transition_fixture import catalog_text, room_records
from prepare_room_transition_oracle import verify_inputs
from prepare_static_tilemap import build_mask, read_mask
from run_room_transition_probe import run

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / ".audit/native-room-transition-vita/full-bake-contract-01"
KIND = "native-room-transition-full-bake-source-cpu-v1"
DRIVER_ID = {"bytes": 83698, "sha256": "2f7555abf2d9dd6d4e56429009d674551b2857304fd794d00e18958eef2563c6"}
MASK_ID = {"bytes": 238195, "sha256": "7631f1aa8dc9dff9930bffc6838973a5a5a6d7c86903c43b996db54c796f2aa4"}
MASK_PROVENANCE_ID = {"bytes": 1376, "sha256": "5375c373b762df8a5457bd43c383ab4615b2b619906adb0c21e5b12196fc8990"}
SOURCE_ID = {"bytes": 28800, "sha256": "91f7a2d44bb4b49046a94b267a6b46e6e20af3b11144add7622ef7d21d665b06"}
SOURCE_RECHECK_ID = {"bytes": 8352, "sha256": "76ff2644342b74c9e406572e738924f9797031bc20615d8ad8ba2d02b9ccb924"}
REFERENCES = {
    "Celeste.exe": {"bytes": 2572800, "sha256": "fd73f8a2311fa5737ded550cbad4b75c85b7686b36432f59185e940fcb65fcfe"},
    "FNA.dll": {"bytes": 773632, "sha256": "00349b572636c0ed4c97d4e4f74344b3450160c42d4a6b52bcf5e0f2d5193a31"},
    "mscorlib.dll": {"bytes": 3976192, "sha256": "1da089aee864876d1f7d303e91087a1e2f3c9f7b989514a780a5ba9188053341"},
}


def verify_pinned(path, expected, label):
    if file_identity(path) != expected:
        raise ValueError("Pinned " + label + " changed: " + str(path))


def validate_terrain_metadata(driver, mask, provenance):
    if len(driver["levels"]) != 38 or len(driver["filler"]) != 22:
        raise ValueError("Full terrain requires 38 rooms and 22 fillers")
    if mask[:4] != (-64, -3272, 541, 440) or provenance.get("origin") != [-64, -3272] or provenance.get("dimensions") != [541, 440]:
        raise ValueError("Full terrain metadata bounds changed")
    if build_mask(driver) != mask:
        raise ValueError("Shipped mask differs from the independently constructed driver terrain")


def verify_references(result):
    inputs = json.loads(result.read_text())["inputs"]
    identities = {}
    for name, expected in REFERENCES.items():
        entry = inputs.get(name, {})
        if {key: entry.get(key) for key in ("bytes", "sha256")} != expected:
            raise ValueError("Pinned reference assembly provenance changed: " + name)
        path = Path(entry["path"])
        verify_pinned(path, expected, "reference assembly")
        identities[str(path)] = expected
    return identities


def verify_source(profile, source_recheck):
    verify_pinned(source_recheck, SOURCE_RECHECK_ID, "reviewed SOURCE binding")
    source_manifest = profile / "transition-profile.json"
    verify_pinned(source_manifest, SOURCE_ID, "historical SOURCE profile")
    source = json.loads(source_manifest.read_text())
    inputs = json.loads(source_recheck.read_text())["artifact_and_input_pins"]
    if any(path not in inputs for path in source["compiled_sources"]):
        raise ValueError("Reviewed binding omits a SOURCE compiler input")
    verify_inputs(inputs, source["compiled_sources"])
    inputs[str(source_recheck)] = file_identity(source_recheck)
    inputs[str(source_manifest)] = file_identity(source_manifest)
    return source, inputs


def validate_profile(record):
    if record.get("schema") != 1 or record.get("kind") != KIND:
        raise ValueError("Expected separate full-bake profile kind/version")
    if record.get("binding") != canonical_digest({key: value for key, value in record.items() if key != "binding"}):
        raise ValueError("Full-bake provenance binding changed")
    if record.get("terrain") != {"driver": DRIVER_ID, "mask": MASK_ID, "origin": [-64, -3272], "dimensions": [541, 440]}:
        raise ValueError("Full-bake terrain identity changed")


def verify_profile(profile):
    record = json.loads((profile / "transition-profile.json").read_text())
    validate_profile(record)
    verify_inputs(record["inputs"], record["compiled_sources"])
    for group in ("generated", "compiled_artifacts"):
        verify_file_identities({str(profile / name): value for name, value in record[group].items()})
    return record


def prepare(profile, source_recheck, prepared, references, sdk, output):
    if output.exists() or not output.is_relative_to(AUDIT):
        raise ValueError("Full-bake output must be fresh beneath its separate private namespace")
    source, inputs = verify_source(profile, source_recheck)
    if str(sdk) not in source["inputs"]:
        raise ValueError("Only the existing pinned SOURCE SDK is authorized")
    verify_pinned(sdk, source["inputs"][str(sdk)], "SOURCE SDK")
    driver_path, mask_path = prepared / "driver.json", prepared / "global.mask"
    verify_pinned(driver_path, DRIVER_ID, "driver")
    verify_pinned(mask_path, MASK_ID, "mask")
    provenance_path = prepared / "provenance.json"
    verify_pinned(provenance_path, MASK_PROVENANCE_ID, "mask provenance")
    validate_terrain_metadata(json.loads(driver_path.read_text()), read_mask(mask_path.read_text()), json.loads(provenance_path.read_text()))
    inputs.update(verify_references(references))
    for path in (driver_path, mask_path, provenance_path, references, *[profile / name for name in source["generated"]]):
        inputs[str(path)] = file_identity(path)
    originals = {Path(path).name: Path(path) for path in source["compiled_sources"]}
    caller = replace_once(originals["TransitionCaller.cs"].read_text(),
                          'Path.Combine(TransitionProfile.DataRoot, "two-rooms.json")', "FullBakeProfile.RoomsPath")
    observer = replace_once(originals["TransitionProfile.cs"].read_text(),
                            "RoomCoreTileBake.Build(probe.Level, probe.Level.Session.MapData);", "probe.Write(FullBakeProfile.Build(probe.Level));")
    execution = replace_once(originals["TransitionExecution.cs"].read_text(),
                             '.audit/native-room-transition/source-contract-01', '.audit/native-room-transition-vita/full-bake-contract-01')
    output.mkdir(parents=True)
    for directory in ("home", "tmp"):
        (output.parent / directory).mkdir(exist_ok=True)
    generated = {"TransitionCaller.cs": caller, "TransitionProfile.cs": observer, "TransitionExecution.cs": execution,
                 "full-bake-input.json": json.dumps({"driver": str(driver_path), "rooms": str(profile / "two-rooms.json")}) + "\n",
                 "catalog.txt": catalog_text(room_records(json.loads((profile / "two-rooms.json").read_text())))}
    for name, text in generated.items():
        (output / name).write_text(text)
    files = [str(output / Path(path).name) if Path(path).name in generated else path for path in source["compiled_sources"]]
    files.append(str(ROOT / "tests/native/oracle/transition/FullBakeProfile.cs"))
    project = '<Project><ItemGroup>' + ''.join('<Compile Include="' + escape(path) + '"/>' for path in files) + '</ItemGroup></Project>'
    (output / "Oracle.csproj").write_text(project)
    dependencies = ("run_room_transition_probe.py", "prepare_dash_trail_oracle.py", "native_room_revision.py",
                    "prepare_native_transition_fixture.py", "prepare_room_transition_oracle.py", "prepare_static_tilemap.py", "binary_map.py")
    for path in (Path(__file__).resolve(), *[ROOT / "scripts" / name for name in dependencies], *map(Path, files)):
        if path.parent != output:
            inputs[str(path)] = file_identity(path)
    compile_recording(output, sdk)
    command = json.loads((output / "compiler-command.json").read_text())
    compiler_inputs = [Path(command[0]), Path(command[1]), *[Path(value[3:]) for value in command if value.startswith("-r:")]]
    inputs.update({str(path): file_identity(path) for path in compiler_inputs})
    record = {"schema": 1, "kind": KIND, "terrain": {"driver": DRIVER_ID, "mask": MASK_ID, "origin": [-64, -3272], "dimensions": [541, 440]},
              "inputs": inputs, "compiled_sources": files,
              "generated": {name: file_identity(output / name) for name in (*generated, "Oracle.csproj")},
              "compiled_artifacts": {name: file_identity(output / name) for name in ("Oracle.dll", "Oracle.runtimeconfig.json", "compiler-command.json")},
              "source_extraction_reused_in_place": str(originals["TransitionExtracted.cs"]),
              "original_payload_copies": [], "claim": "Full-terrain SOURCE CPU experiment; route/native/DRAW acceptance requires separate checks"}
    record["binding"] = canonical_digest(record)
    (output / "transition-profile.json").write_text(json.dumps(record, indent=2) + "\n")
    verify_profile(output)
    return record


def validate_collision_grid(observed, expected):
    actual = (*observed["origin"], *observed["dimensions"], observed["cells"])
    if actual != expected or type(observed["seed"]) is not int or observed["seed"] != 553:
        raise ValueError("SOURCE full collision grid differs from the shipped mask")


def check_terrain(rows, mask_path):
    verify_pinned(mask_path, MASK_ID, "mask")
    expected = read_mask(mask_path.read_text())
    observations = [row for row in rows if row.get("event") == "full-bake-terrain"]
    if len(observations) != 1:
        raise ValueError("Missing unique independently constructed SOURCE collision grid")
    observed = observations[0]
    validate_collision_grid(observed, expected)
    return {"cells_compared": len(expected[4]), "origin": list(expected[:2]), "dimensions": list(expected[2:4]), "source_seed": observed["seed"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preparation = commands.add_parser("prepare")
    for name in ("profile", "source-recheck", "prepared", "references", "sdk", "output"):
        preparation.add_argument("--" + name, type=Path, required=True)
    execution = commands.add_parser("run")
    for name in ("profile", "sdk", "content", "controls", "output"):
        execution.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        record = prepare(*(getattr(args, name).resolve() for name in ("profile", "source_recheck", "prepared", "references", "sdk", "output")))
        print(json.dumps({"kind": record["kind"], "binding": record["binding"]}))
    else:
        profile = args.profile.resolve()
        verify_profile(profile)
        receipt = run(profile, args.sdk.resolve(), args.content.resolve(), args.controls.resolve(), args.output.resolve())
        verify_profile(profile)
        print(json.dumps(receipt))
        raise SystemExit(1 if receipt["exit_code"] else 0)


if __name__ == "__main__":
    main()
