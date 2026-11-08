#!/usr/bin/env python3
"""Compare a static corrective package with the previously executed diagnostic."""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import zipfile

from native_room_revision import REPO_ROOT, source_state
from verify_native_room_vpk import verify

RUNTIME_TARGETS = ("celeste_native_kernel", "celeste_room_diagnostic", "celeste_native_room")


def normalized_revision(data, revision):
    return data.replace(revision.encode("ascii"), b"<REVISION>")


def require_equal(before, after, label):
    if before != after:
        raise ValueError("Runtime reuse identity differs: " + label)
    return {"baseline_sha256": hashlib.sha256(before).hexdigest(), "current_sha256": hashlib.sha256(after).hexdigest(), "equal": True}


def resident_sections(path, revision):
    data = path.read_bytes()
    if len(data) < 52 or data[:7] != b"\x7fELF\x01\x01\x01":
        raise ValueError("Expected original ELF32 little-endian ARM image")
    offset = struct.unpack_from("<I", data, 32)[0]
    size, count, strings = struct.unpack_from("<HHH", data, 46)
    if size != 40 or strings >= count or offset + count * size > len(data):
        raise ValueError("Invalid bounded ELF section table")
    sections = [struct.unpack_from("<10I", data, offset + index * size) for index in range(count)]
    names_header = sections[strings]
    names = data[names_header[4]:names_header[4] + names_header[5]]
    result = {}
    for section in sections:
        name = names[section[0]:].split(b"\0", 1)[0].decode("ascii")
        if not section[2] & 2 and name != ".sce.rel":
            continue
        payload = b"" if section[1] == 8 else data[section[4]:section[4] + section[5]]
        if section[1] != 8 and len(payload) != section[5]:
            raise ValueError("Truncated resident ELF section")
        result[name] = {"flags": section[2], "address": section[3], "bytes": section[5],
                        "normalized_sha256": hashlib.sha256(normalized_revision(payload, revision)).hexdigest()}
    if not result:
        raise ValueError("Missing resident ELF image")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True, help="Existing complete d4 native-feedback root")
    parser.add_argument("--build", type=Path, required=True, help="New static Vita CMake build root")
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--fresh-player-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(REPO_ROOT / ".audit") or output.exists():
        parser.error("Evidence must be fresh and private")
    revision, changes = source_state(REPO_ROOT)
    if changes:
        parser.error("Runtime identity requires a clean exact corrective revision")
    output.mkdir(parents=True)
    baseline = json.loads((args.baseline / "feedback.json").read_text())
    old_revision = baseline["revision"]
    report = {"baseline_guest_revision": old_revision, "corrective_revision": revision,
              "new_package_guest_executed": False, "baseline_feedback": str(args.baseline / "feedback.json")}
    try:
        if not all(baseline["stages"].values()) or baseline["errors"] or baseline["source_after"] != {"revision": old_revision, "changes": []}:
            raise ValueError("Baseline is not a closed clean native guest proof")
        old_build = args.baseline / "vita-app"
        old_staging = args.baseline / "staging"
        new_vpk = args.build / "src/vita/celeste_native_room.vpk"
        package = verify(new_vpk, args.build / "src/vita", args.staging)
        old_vpk = Path(baseline["vpk"]["path"])
        if hashlib.sha256(old_vpk.read_bytes()).hexdigest() != baseline["vpk"]["sha256"]:
            raise ValueError("Executed baseline VPK changed")
        for artifact in baseline["artifacts"].values():
            if hashlib.sha256(Path(artifact["path"]).read_bytes()).hexdigest() != artifact["sha256"]:
                raise ValueError("Executed native image/readback/receipt changed")
        source_files = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", old_revision, "--", "src"], cwd=REPO_ROOT, text=True).splitlines()
        sources = {}
        for name in source_files:
            original = subprocess.check_output(["git", "show", old_revision + ":" + name], cwd=REPO_ROOT)
            sources[name] = require_equal(original, (REPO_ROOT / name).read_bytes(), name)
        report["runtime_sources_and_shared_headers"] = sources
        old_cmake = subprocess.check_output(["git", "show", old_revision + ":CMakeLists.txt"], cwd=REPO_ROOT)
        new_cmake = (REPO_ROOT / "CMakeLists.txt").read_bytes()
        report["cmake_runtime_prefix"] = require_equal(old_cmake.split(b"if(BUILD_TESTING)", 1)[0], new_cmake.split(b"if(BUILD_TESTING)", 1)[0], "non-test CMake")

        def normalize_build(data, build, staging, sha):
            return normalized_revision(data, sha).replace(str(build.resolve()).encode(), b"<BUILD>").replace(str(staging.resolve()).encode(), b"<STAGING>")

        settings = {}
        for target in RUNTIME_TARGETS:
            folder = Path("src/vita") if target == "celeste_native_room" else Path()
            for filename in ("flags.make", "link.txt"):
                relative = folder / "CMakeFiles" / (target + ".dir") / filename
                before = normalize_build((old_build / relative).read_bytes(), old_build, old_staging, old_revision)
                after = normalize_build((args.build / relative).read_bytes(), args.build, args.staging, revision)
                settings[str(relative)] = require_equal(before, after, str(relative))
        report["effective_compile_and_link_settings"] = settings
        assets = {}
        with zipfile.ZipFile(old_vpk) as original, zipfile.ZipFile(new_vpk) as current:
            if set(original.namelist()) != set(current.namelist()):
                raise ValueError("Packaged runtime file set changed")
            if original.read("eboot.bin") != (old_build / "src/vita/eboot.bin").read_bytes():
                raise ValueError("Baseline SELF is not tied to the executed VPK")
            for name in original.namelist():
                if name == "eboot.bin":
                    continue
                before, after = original.read(name), current.read(name)
                if name == "assets/native-room/provenance.json":
                    before, after = normalized_revision(before, old_revision), normalized_revision(after, revision)
                assets[name] = require_equal(before, after, name)
            player = json.loads(original.read("assets/native-room/provenance.json"))["player"]
            fresh = {}
            for name in player["files"]:
                fresh[name] = require_equal(original.read("assets/native-room/" + name), (args.fresh_player_dir / name).read_bytes(), "fresh source-prepared " + name)
        report["all_packaged_assets_and_commands"] = assets
        report["fresh_source_bank_pages_match_executed_package"] = fresh
        for filename in ("celeste_native_room", "celeste_native_room.velf"):
            before = resident_sections(old_build / "src/vita" / filename, old_revision)
            after = resident_sections(args.build / "src/vita" / filename, revision)
            if before != after:
                raise ValueError("Resident application/linked-dependency/import/relocation bytes differ: " + filename)
            report.setdefault("resident_application_and_linked_dependency_bytes", {})[filename] = before
        velf = report["resident_application_and_linked_dependency_bytes"]["celeste_native_room.velf"]
        metadata = [value for name, value in velf.items() if name.startswith(".sce") and name != ".sce.rel"]
        metadata_start = min(value["address"] for value in metadata)
        metadata_end = max(value["address"] + value["bytes"] for value in metadata)
        init = velf[".init_array"]["address"]
        report["sce_layout"] = {"gap_before_sce": init - metadata_start, "metadata_bytes": metadata_end - metadata_start, "clearance": init - metadata_end}
        if report["sce_layout"]["clearance"] <= 0:
            raise ValueError("New SCE metadata overlaps writable application data")
        report.update(status="runtime-reuse-identities-passed", new_vpk_sha256=package["vpk_sha256"], baseline_vpk_sha256=baseline["vpk"]["sha256"],
                      dependency_scope="Actual resident linked static-dependency and import/relocation bytes compared with original built images tied to the executed VPK; no claim about historically unused SDK archive members",
                      metadata_exception="Generated revision text only; neither identical VPK bytes nor corrective-tip guest execution is claimed")
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        try:
            final_revision, final_changes = source_state(REPO_ROOT)
            report["source_after"] = {"revision": final_revision, "changes": final_changes}
            if revision != final_revision or final_changes:
                report["status"] = "invalidated-by-source-change"
        except Exception as error:
            report["source_after"] = {"error": {"type": type(error).__name__, "message": str(error)}}
            report["status"] = "invalidated-by-source-check-failure"
        (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    if report["status"] != "runtime-reuse-identities-passed":
        raise RuntimeError("Source changed during runtime identity verification")
    print(json.dumps({key: report[key] for key in ("status", "corrective_revision", "baseline_guest_revision", "new_vpk_sha256", "sce_layout", "new_package_guest_executed")}, indent=2))


if __name__ == "__main__":
    main()
