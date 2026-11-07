#!/usr/bin/env python3
"""Build the private extracted-method reference offline and compare synthetic traces."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
from compare_native_traces import compare


ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / ".audit/native-oracle"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", choices=("movement", "scheduling"), default="movement")
    parser.add_argument("--native", type=Path, required=True, help="Host native_trace_runner executable")
    parser.add_argument("--fixtures", type=Path)
    args = parser.parse_args()
    if args.fixtures is None:
        args.fixtures = ROOT / f"tests/native/{args.domain}.fixtures"
    private = PRIVATE if args.domain == "movement" else PRIVATE / "scheduling"
    if args.domain == "scheduling":
        from compare_scheduling_traces import compare as compare_domain, FIELDS
        field_count = len(FIELDS)
    else:
        compare_domain, field_count = compare, 16
    sdk = PRIVATE / "tools/dotnet-8.0.425/dotnet"
    if not sdk.is_file():
        parser.error("Private SDK missing; run scripts/bootstrap_native_oracle.py first")
    evidence = private / "verification"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "result.json").unlink(missing_ok=True)
    environment = os.environ | {
        "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1", "DOTNET_NOLOGO": "1",
        "DOTNET_CLI_HOME": str(PRIVATE / "tools/cli"), "NUGET_PACKAGES": str(PRIVATE / "tools/packages"),
        "DOTNET_ROOT": str(sdk.parent), "DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE": "1",
        "MSBUILDDISABLENODEREUSE": "1",
    }
    commands = []

    def run(command, filename):
        command = [str(part) for part in command]
        with (evidence / filename).open("w") as output:
            result = subprocess.run(command, cwd=ROOT, env=environment, stdout=output, stderr=subprocess.STDOUT)
        commands.append({"command": command, "exit_code": result.returncode, "log": filename})
        if result.returncode:
            raise RuntimeError(f"Command failed ({result.returncode}): {command}; see {evidence / filename}")

    run([sdk, "--version"], "sdk-version.log")
    if (evidence / "sdk-version.log").read_text().strip() != "8.0.425":
        raise RuntimeError("Unexpected private SDK version")
    run([sdk, "--list-runtimes"], "runtimes.log")
    if "Microsoft.NETCore.App 8.0.31 [" not in (evidence / "runtimes.log").read_text():
        raise RuntimeError("Expected private runtime 8.0.31 is missing")
    run([sys.executable, ROOT / "scripts/extract_native_oracle.py", "--domain", args.domain], "extraction.log")
    run([sdk, "restore", private / "Oracle.csproj", "--configfile", private / "NuGet.Config"], "restore.log")
    run([sdk, "build", private / "Oracle.csproj", "--no-restore", "-c", "Release",
         "-p:UseSharedCompilation=false", "--disable-build-servers"], "build.log")
    run([sdk, private / "bin/Release/net8.0/Oracle.dll", args.fixtures.resolve()], "reference.tsv")
    run([args.native.resolve(), args.fixtures.resolve()], "native.tsv")
    reference = (evidence / "reference.tsv").read_text().splitlines()
    native = (evidence / "native.tsv").read_text().splitlines()
    rows = compare_domain(reference, native, fixtures=args.fixtures)
    report = {"rows": rows, "scenarios": len({line.split('\t')[0] for line in reference}),
              "fields_per_row": field_count, "comparison": "exact text and float32 bits; no epsilon",
              "fixture_sha256": hashlib.sha256(args.fixtures.read_bytes()).hexdigest(),
              "source_manifest": "../source-manifest.json", "commands": commands,
              "claim": "Extracted-method compatibility, not full game execution"}
    (evidence / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"MATCH: {report['scenarios']} scenarios, {rows} rows, {field_count} exact fields per row; {evidence}")


if __name__ == "__main__":
    main()
