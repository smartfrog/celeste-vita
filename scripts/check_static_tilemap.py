#!/usr/bin/env python3
"""Compare every global mask cell with the unchanged private loader-block oracle."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from check_native_oracle import ROOT, PRIVATE, oracle_environment
from compare_loader_traces import compare as compare_loader
from compare_grid_traces import compare as compare_grid
from prepare_static_tilemap import INPUT_SHA, MAP_SHA, build_mask, read_mask


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, default=ROOT / ".audit/native-static-tilemap/prepared")
    parser.add_argument("--output", type=Path, default=ROOT / ".audit/native-static-tilemap/mask-verification")
    parser.add_argument("--native", type=Path, required=True)
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT / ".audit"):
        parser.error("Private evidence must stay under .audit")
    args.output.mkdir(parents=True, exist_ok=True)
    sdk = PRIVATE / "tools/dotnet-8.0.425/dotnet"
    oracle = PRIVATE / "grid/bin/Release/net8.0/Oracle.dll"
    manifest = json.loads((PRIVATE / "grid/source-manifest.json").read_text())
    if manifest["input_sha256"] != INPUT_SHA:
        raise ValueError("Unexpected oracle provenance")
    provenance = json.loads((args.prepared / "provenance.json").read_text())
    if provenance["input_sha256"] != INPUT_SHA or provenance["map_sha256"] != MAP_SHA or provenance["selected_room"] != "1":
        raise ValueError("Unexpected prepared input provenance")
    if set(provenance["files"]) != {"driver.json", "global.mask", "geometry.fixtures", "player.fixtures"}:
        raise ValueError("Missing/foreign prepared artifact")
    for name, expected in provenance["files"].items():
        if hashlib.sha256((args.prepared / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Changed prepared artifact: {name}")
    commands = []

    def run(command, log):
        command = [str(value) for value in command]
        with (args.output / log).open("w") as out:
            result = subprocess.run(command, cwd=ROOT, env=oracle_environment(sdk), stdout=out, stderr=subprocess.STDOUT)
        commands.append({"command": command, "exit_code": result.returncode, "log": log})
        if result.returncode:
            raise RuntimeError(f"Command failed; see {args.output / log}")

    driver = json.loads((args.prepared / "driver.json").read_text())
    fixtures = json.loads((ROOT / "tests/native/loader.fixtures.json").read_text())
    fixtures["cases"].append({"case": "actual_forsaken_city_global", **driver})
    fixture_path = args.output / "loader.fixtures.json"
    fixture_path.write_text(json.dumps(fixtures, ensure_ascii=True, separators=(",", ":")) + "\n")
    run([sdk, oracle, "--mask-cases", fixture_path, args.output / "reference-loader.tsv"], "loader.log")
    native_rows = []
    for case in fixtures["cases"]:
        x, y, columns, rows, cells = build_mask(case)
        native_rows.extend("\t".join(map(str, (case["case"], row, x, y + row * 8, columns, cells[row * columns:(row + 1) * columns]))) for row in range(rows))
    (args.output / "prepared-loader.tsv").write_text("\n".join(native_rows) + "\n")
    rows = compare_loader((args.output / "reference-loader.tsv").read_text().splitlines(), native_rows, fixture_path)
    run([sdk, oracle, "--mask", args.prepared / "driver.json", args.output / "reference.mask"], "actual-mask.log")
    reference = read_mask((args.output / "reference.mask").read_text())
    prepared = read_mask((args.prepared / "global.mask").read_text())
    if reference != prepared:
        raise ValueError("Prepared mask differs from source oracle")
    selected = next(level for level in driver["levels"] if level["name"] == "lvl_1")
    isolated = selected["solids"].split("\n")
    x, y, columns, height, cells = prepared
    for row, text in enumerate(isolated):
        for column, char in enumerate(text):
            index = (row - y // 8) * columns + column - x // 8
            if cells[index] != ("1" if char != "0" else "0"):
                raise ValueError("Room 1 interior changed in global construction")
    isolated_probes = []
    for px, py in ((-1, 144), (16, -1), (240, -1)):
        cx, cy = px // 8, py // 8
        isolated_probes.append(0 <= cy < len(isolated) and 0 <= cx < len(isolated[cy]) and isolated[cy][cx] != "0")
    if any(isolated_probes):
        raise ValueError("Expected outside-isolated-mask probes")
    run([sdk, oracle, args.prepared / "geometry.fixtures"], "reference-grid.tsv")
    run([args.native.resolve(), args.prepared / "geometry.fixtures"], "native-grid.tsv")
    geometry_rows = (args.output / "reference-grid.tsv").read_text().splitlines()
    matched = compare_grid(geometry_rows, (args.output / "native-grid.tsv").read_text().splitlines(), args.prepared / "geometry.fixtures")
    query_results = [row.split("\t")[3] for row in geometry_rows if row.split("\t")[2] == "query"]
    if query_results != ["0", "1", "1", "1", "1"]:
        raise ValueError("Actual spawn/ground/global-edge acceptance failed")
    result = {"input_sha256": INPUT_SHA, "map_sha256": MAP_SHA, "loader_scenarios": len(fixtures["cases"]), "loader_rows": rows,
              "all_actual_cells_compared": reference[2] * reference[3], "actual_occupied": reference[4].count("1"),
              "room1_interior_cells_compared": sum(map(len, isolated)), "isolated_outside_probes": isolated_probes,
              "geometry_scenarios": 3, "geometry_rows": matched, "query_results": query_results, "commands": commands,
              "claim": "Extracted loader/Grid method compatibility; not game execution, startup selection or playable room",
              "artifacts": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in args.output.iterdir() if path.is_file() and path.name != "result.json"}}
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"MATCH: {len(fixtures['cases'])} loader cases/{rows} complete rows; all {result['all_actual_cells_compared']} actual cells; {matched} actual Grid rows")


if __name__ == "__main__":
    main()
