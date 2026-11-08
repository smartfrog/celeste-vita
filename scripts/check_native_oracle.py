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


def oracle_environment(sdk):
    return os.environ | {
        "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1", "DOTNET_NOLOGO": "1",
        "DOTNET_CLI_HOME": str(PRIVATE / "tools/cli"), "NUGET_PACKAGES": str(PRIVATE / "tools/packages"),
        "DOTNET_ROOT": str(sdk.parent), "DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE": "1", "MSBUILDDISABLENODEREUSE": "1",
    }


def verify_extraction(private):
    manifest = json.loads((private / "source-manifest.json").read_text())
    extracted = (private / "Extracted.cs").read_bytes()
    if hashlib.sha256(extracted).hexdigest() != manifest["extracted_sha256"]:
        raise ValueError("Generated extraction changed after its source manifest")
    blocks = 0
    for entry in manifest["extractions"]:
        source = (ROOT / entry["source_path"]).read_bytes()
        if hashlib.sha256(source).hexdigest() != entry["source_sha256"]:
            raise ValueError("Source hash changed: " + entry["file"])
        lines = source.decode().splitlines(keepends=True)
        for (start, end), digest in zip(entry["lines_inclusive"], entry["blocks_sha256"], strict=True):
            block = "".join(lines[start - 1:end]).encode()
            if hashlib.sha256(block).hexdigest() != digest or block not in extracted:
                raise ValueError("Unchanged source block identity failed: " + entry["file"])
            blocks += 1
    return {"blocks": blocks, "source_entries": len(manifest["extractions"]), "extracted_sha256": manifest["extracted_sha256"],
            "verification": "Every selected source block is byte-identical and present unchanged in generated source"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", choices=("movement", "scheduling", "input", "player", "grid", "hazards", "dash"), default="movement")
    parser.add_argument("--native", type=Path, help="Host native_trace_runner executable")
    parser.add_argument("--compile-only", action="store_true", help="Prove extracted dependency closure only; no behavioral comparison")
    parser.add_argument("--fixtures", type=Path)
    parser.add_argument("--jump-family", action="store_true", help="Require nine-family behavioral coverage using the Dash source closure")
    parser.add_argument("--climb-family", action="store_true", help="Include the bounded static Climb closure")
    parser.add_argument("--output", type=Path, help="Fresh private extraction/build/evidence directory; never overwrite existing evidence")
    args = parser.parse_args()
    if args.jump_family and args.domain != "dash":
        parser.error("--jump-family requires --domain dash")
    if args.climb_family and (args.domain != "dash" or args.jump_family):
        parser.error("--climb-family requires --domain dash and excludes --jump-family")
    if not args.compile_only and args.native is None:
        parser.error("--native is required unless --compile-only is selected")
    if args.fixtures is None:
        args.fixtures = ROOT / f"tests/native/{'climb' if args.climb_family else 'jumps' if args.jump_family else args.domain}.fixtures"
    private = PRIVATE if args.domain == "movement" else PRIVATE / args.domain
    if args.output is not None:
        private = args.output.resolve()
        if not private.is_relative_to(ROOT / ".audit") or private.exists():
            parser.error("--output must be a fresh directory beneath .audit")
    if args.compile_only:
        compare_domain, field_count = None, None
    elif args.domain == "scheduling":
        from compare_scheduling_traces import compare as compare_domain, FIELDS
        field_count = len(FIELDS)
    elif args.domain == "input":
        from compare_input_traces import compare as compare_domain, FIELDS
        field_count = len(FIELDS)
    elif args.domain == "player":
        from compare_player_traces import compare as compare_domain, FIELDS
        field_count = len(FIELDS)
    elif args.domain == "grid":
        from compare_grid_traces import compare as compare_domain, FIELDS
        field_count = len(FIELDS)
    elif args.domain == "hazards":
        from compare_hazard_traces import compare as compare_domain, FIELDS
        field_count = len(FIELDS)
    elif args.domain == "dash":
        if args.climb_family:
            from compare_climb_traces import compare as compare_domain, FIELDS
        elif args.jump_family:
            from compare_jump_traces import compare as compare_domain, FIELDS
        else:
            from compare_dash_traces import compare as compare_domain, FIELDS
        field_count = len(FIELDS)
    else:
        compare_domain, field_count = compare, 16
    sdk = PRIVATE / "tools/dotnet-8.0.425/dotnet"
    if not sdk.is_file():
        parser.error("Private SDK missing; run scripts/bootstrap_native_oracle.py first")
    evidence = private / "verification"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "result.json").unlink(missing_ok=True)
    if args.compile_only:
        (evidence / "compile-result.json").unlink(missing_ok=True)
    environment = oracle_environment(sdk)
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
    run([sys.executable, ROOT / "scripts/extract_native_oracle.py", "--domain", args.domain] +
        (["--climb-family"] if args.climb_family else []) +
        (["--output", private] if args.output else []), "extraction.log")
    identity = verify_extraction(private)
    (evidence / "source-identity.json").write_text(json.dumps(identity, indent=2) + "\n")
    run([sdk, "restore", private / "Oracle.csproj", "--configfile", private / "NuGet.Config"], "restore.log")
    run([sdk, "build", private / "Oracle.csproj", "--no-restore", "-c", "Release",
         "-p:UseSharedCompilation=false", "--disable-build-servers"], "build.log")
    if args.compile_only:
        report = {"domain": args.domain, "commands": commands, "source_manifest": "../source-manifest.json",
                  "claim": "Compilation/dependency closure only, not behavioral parity"}
        (evidence / "compile-result.json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"COMPILED: {args.domain}; {evidence}; no behavioral comparison")
        return
    run([sdk, private / "bin/Release/net8.0/Oracle.dll", args.fixtures.resolve()], "reference.tsv")
    run([args.native.resolve(), args.fixtures.resolve()], "native.tsv")
    reference = (evidence / "reference.tsv").read_text().splitlines()
    native = (evidence / "native.tsv").read_text().splitlines()
    rows = compare_domain(reference, native, fixtures=args.fixtures)
    report = {"rows": rows, "scenarios": len({line.split('\t')[0] for line in reference}),
               "family": "climb" if args.climb_family else "jumps" if args.jump_family else args.domain,
              "fields_per_row": field_count, "comparison": "exact text and float32 bits; no epsilon",
              "fixture_sha256": hashlib.sha256(args.fixtures.read_bytes()).hexdigest(),
              "source_manifest": "../source-manifest.json", "commands": commands,
              "claim": "Extracted-method compatibility, not full game execution"}
    (evidence / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"MATCH: {report['scenarios']} scenarios, {rows} rows, {field_count} exact fields per row; {evidence}")


if __name__ == "__main__":
    main()
