"""Explicit opt-in staging of existing pinned gameplay resources, without extraction or generation."""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import time

from native_material_pack import verify_pin, write_new
from native_room_revision import (REPO_ROOT, cache_values, canonical_digest, validate_source_state, source_binding,
                                  staging_binding, verify_file_identities, file_identity)
from stage_native_room import asset_pins_text, checksum
from fixture_protocol import integer
from bind_native_material_validator import (EXPECTED_ARCHIVES, EXPECTED_OBJECTS, TARGET as VALIDATOR_TARGET,
                                            TOKEN_PREFIX)

VALIDATOR_TIMEOUT = 10.0
VALIDATOR_STDOUT_LIMIT = 4096
VALIDATOR_STDERR_LIMIT = 8192

METADATA = {"global.mask": "CSTM1", "hazards.txt": "CSH1", "player.txt": "CSPP1",
            "rooms.txt": "CROOM1", "owners.txt": "CDO1", "decals-catalog.txt": "CDSC2",
            "terrain.txt": "CSTV1", "spikes-catalog.txt": "CSPK1", "jumpthru.txt": "CJTC1",
            "strawberries.txt": "CSTR1", "spring.txt": "CSPR1", "dust.txt": "CDUS1",
            "player-original.txt": "CPLAYERDRAW1", "materials.txt": "CSMT1"}


def verified_profile(path, digest):
    profile = json.loads(verify_pin({"path": str(path), "bytes": path.stat().st_size, "sha256": digest}))
    if set(profile) != {"schema", "mode", "files"} or profile["schema"] != 1 or profile["mode"] != "automatic-transition":
        raise ValueError("Gameplay requires explicit schema 1 automatic-transition profile")
    files = profile["files"]
    if not isinstance(files, dict) or not set(METADATA) <= files.keys() or len(files) > 128:
        raise ValueError("Gameplay profile lacks the complete bounded metadata inventory")
    inputs = {str(path.resolve()): file_identity(path)}
    payload = {}
    for name, pin in files.items():
        if (not isinstance(name, str) or not name or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789.-" for c in name) or
                not isinstance(pin, dict) or set(pin) != {"path", "bytes", "sha256"} or
                type(pin["bytes"]) is not int or not 0 < pin["bytes"] <= 32_000_000):
            raise ValueError("Invalid gameplay file pin: " + str(name))
        payload[name] = verify_pin(pin)
        inputs[str(Path(pin["path"]).resolve())] = {key: pin[key] for key in ("bytes", "sha256")}
    for name, magic in METADATA.items():
        if payload[name].split(b"\n", 1)[0] != magic.encode():
            raise ValueError("Gameplay metadata protocol mismatch: " + name)
    lines = payload["materials.txt"].decode("ascii").splitlines()
    if len(lines) < 3:
        raise ValueError("Gameplay material table lacks canonical header/page rows")
    count = integer(lines[1], 1, 64)
    expected = set(METADATA)
    rgba_bytes = 0
    for line in lines[2:2 + count]:
        fields = line.split(" ")
        if len(fields) != 3:
            raise ValueError("Noncanonical gameplay material page row")
        page = integer(fields[0], -2147483648, 2147483647)
        width = integer(fields[1], -2147483648, 2147483647)
        height = integer(fields[2], -2147483648, 2147483647)
        name = f"page{page}.rgba"
        if page < 0 or not 1 <= width <= 128 or not 1 <= height <= 128 or name in expected:
            raise ValueError("Invalid or duplicate gameplay page ID/dimensions")
        expected.add(name)
        if name not in payload or len(payload[name]) != width * height * 4:
            raise ValueError("Gameplay page dimension/byte count mismatch: " + name)
        rgba_bytes += width * height * 4
    if len(lines) < 2 + count + 1:
        raise ValueError("Gameplay material table lacks all page or binding count rows")
    if rgba_bytes > 512 * 1024:
        raise ValueError("Gameplay RGBA exceeds existing bounded 512 KiB upload profile")
    if len(expected) != len(METADATA) + count or set(payload) != expected:
        raise ValueError("Gameplay payload inventory differs from the complete material page set")
    verify_file_identities(inputs)
    return profile, payload, inputs


def gameplay_pins_text(manifest):
    rows = [f'    {{"{name}",{pin["bytes"]},{pin["fnv1a32"]}u}},' for name, pin in sorted(manifest["files"].items())]
    return ('#pragma once\n#include "gameplay_resources.hpp"\nnamespace celeste::diagnostic {\n'
            'inline const std::vector<GameplayFilePin> gameplay_file_pins{\n' + "\n".join(rows) + '\n};\n}\n')


def gameplay_inventory_text(manifest):
    return 'set(gameplay_payload_names\n' + ''.join(f'    "{name}"\n' for name in sorted(manifest["files"])) + ')\n'


def _open_regular(path, limit, what):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except OSError as error:
        raise ValueError(f"{what} cannot be opened safely: {error}") from error
    try:
        status = os.fstat(fd)
        if not stat.S_ISREG(status.st_mode) or not 0 < status.st_size <= limit:
            raise ValueError(f"{what} must be a bounded regular file")
        return fd
    except Exception:
        os.close(fd)
        raise


def _read_bounded(fd, limit):
    chunks, total = [], 0
    while True:
        block = os.read(fd, 65_536)
        if not block:
            return b"".join(chunks)
        total += len(block)
        if total > limit:
            raise ValueError("Bounded input exceeded its limit")
        chunks.append(block)


def _sha256(value):
    return hashlib.sha256(value).hexdigest()


def _identity_matches(path, expected):
    return file_identity(Path(path)) == {"bytes": expected["bytes"], "sha256": expected["sha256"]}


def _verify_group(group, expected_names):
    if set(group) != set(expected_names):
        raise ValueError("Material validator target graph differs from the expected object/archive closure")
    for name, expected in group.items():
        if not _identity_matches(expected["path"], expected):
            raise ValueError("Material validator dependency differs: " + name)


def load_validator_binding(path, state, trusted_sha256):
    if not isinstance(trusted_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", trusted_sha256):
        raise ValueError("Gameplay staging requires an external approved validator binding SHA-256")
    binding_fd = _open_regular(path, 65_536, "Material validator provenance")
    try:
        raw = _read_bounded(binding_fd, 65_536)
    finally:
        os.close(binding_fd)
    actual_sha256 = _sha256(raw)
    if actual_sha256 != trusted_sha256:
        raise ValueError("Material validator provenance differs from the externally approved binding SHA-256")
    try:
        record = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Malformed material validator provenance") from error
    if set(record) != {"schema", "target", "source", "source_files", "binary", "compiler", "build", "binding"}:
        raise ValueError("Unexpected material validator provenance schema")
    if record["schema"] != 1 or record["target"] != VALIDATOR_TARGET:
        raise ValueError("Unsupported material validator provenance")
    if record["source"] != source_binding(state):
        raise ValueError("Material validator provenance is bound to a different source state")
    unbound = {key: value for key, value in record.items() if key != "binding"}
    if record["binding"] != TOKEN_PREFIX + canonical_digest(unbound):
        raise ValueError("Material validator provenance token mismatch")
    if set(record["source_files"]) != {"tests/native/material_table_validator.cpp"}:
        raise ValueError("Material validator source-file closure differs")
    for name, expected in record["source_files"].items():
        path = expected.get("path")
        if not path or not _identity_matches(path, expected):
            raise ValueError("Material validator source file differs: " + name)
    build = record["build"]
    if set(build) != {"cmake_cache", "flags", "link", "objects", "archives", "generator", "home"}:
        raise ValueError("Unexpected material validator build schema")
    _verify_group(build["objects"], EXPECTED_OBJECTS)
    _verify_group(build["archives"], EXPECTED_ARCHIVES)
    cache = Path(build["cmake_cache"]["path"])
    if not _identity_matches(cache, build["cmake_cache"]):
        raise ValueError("Material validator CMake cache differs from its bound identity")
    values = cache_values(cache)
    if (values.get("CMAKE_GENERATOR") != "Unix Makefiles" or build["generator"] != values["CMAKE_GENERATOR"] or
            Path(build["home"]).resolve() != REPO_ROOT.resolve() or
            Path(values.get("CMAKE_HOME_DIRECTORY", "")).resolve() != REPO_ROOT.resolve()):
        raise ValueError("Material validator provenance is bound to a different build configuration")
    build_dir = cache.resolve().parent
    binary = build_dir / VALIDATOR_TARGET
    if Path(record["binary"]["path"]).resolve() != binary.resolve():
        raise ValueError("Material validator binary is not the bound host target")
    if not _identity_matches(binary, record["binary"]):
        raise ValueError("Material validator binary differs from its bound identity")
    compiler = Path(values.get("CMAKE_CXX_COMPILER", ""))
    if compiler.resolve() != Path(record["compiler"]["path"]).resolve() or not _identity_matches(compiler, record["compiler"]):
        raise ValueError("Material validator compiler differs from its bound identity")
    for kind in ("flags", "link"):
        if not _identity_matches(build[kind]["path"], build[kind]):
            raise ValueError("Material validator build input differs: " + kind)
    return binary, record


def _sealed_binary(record):
    if not hasattr(os, "memfd_create") or not hasattr(fcntl, "F_ADD_SEALS"):
        raise RuntimeError("Linux memfd sealing is required for bounded validator execution; no PATH fallback")
    source_fd = _open_regular(record["binary"]["path"], 64 * 1024 * 1024, "Material validator binary")
    memfd = os.memfd_create("celeste-material-validator", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        digest, total = hashlib.sha256(), 0
        while True:
            block = os.read(source_fd, 65_536)
            if not block:
                break
            total += len(block)
            if total > record["binary"]["bytes"]:
                raise ValueError("Material validator binary grew past its bound size")
            digest.update(block)
            written = 0
            while written < len(block):
                written += os.write(memfd, block[written:])
        if total != record["binary"]["bytes"] or digest.hexdigest() != record["binary"]["sha256"]:
            raise ValueError("Material validator binary differs from its bound identity")
        os.lseek(memfd, 0, os.SEEK_SET)
        seals = fcntl.F_SEAL_SEAL | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE
        fcntl.fcntl(memfd, fcntl.F_ADD_SEALS, seals)
        return memfd
    except Exception:
        os.close(memfd)
        raise
    finally:
        os.close(source_fd)


def _exited(process):
    try:
        return os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None
    except ChildProcessError:
        return True


def _cleanup_group(process):
    failures = []
    try:
        pgid = os.getpgid(process.pid)
    except ProcessLookupError:
        pgid = None
    except Exception as error:
        pgid = None
        failures.append(f"getpgid: {error}")
    if pgid is not None:
        if pgid != process.pid:
            failures.append(f"unexpected process group {pgid} for pid {process.pid}")
        else:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except Exception as error:
                failures.append(f"killpg: {error}")
    try:
        process.wait(timeout=2)
    except Exception as error:
        failures.append(f"wait: {error}")
        try:
            process.kill()
            process.wait(timeout=2)
        except Exception as second:
            failures.append(f"kill: {second}")
    return failures


def _run_validator(binary_fd, text, timeout):
    argv = [f"/proc/self/fd/{binary_fd}"]
    process = None
    selector = None
    streams = []
    failure = None
    original = None
    out, err = bytearray(), bytearray()
    try:
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   pass_fds=(binary_fd,), start_new_session=True, close_fds=True)
        streams = [process.stdin, process.stdout, process.stderr]
        for stream in streams:
            if stream is None:
                raise RuntimeError("Material validator process lacks its expected pipe")
            os.set_blocking(stream.fileno(), False)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
        payload = memoryview(text)
        written_steps = 0
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure = ValueError(f"Material validator timed out after {timeout}s")
                break
            events = selector.select(remaining)
            if not events and _exited(process) and not selector.get_map():
                break
            for key, _ in events:
                stream = key.fileobj
                if key.data == "stdin":
                    try:
                        written = os.write(stream.fileno(), payload[written_steps:written_steps + 65_536])
                    except BlockingIOError:
                        continue
                    except BrokenPipeError:
                        written = 0
                    written_steps += written
                    if written_steps == len(payload) or written == 0:
                        selector.unregister(stream)
                        try:
                            stream.close()
                        except OSError:
                            pass
                else:
                    try:
                        block = os.read(stream.fileno(), 65_536)
                    except BlockingIOError:
                        continue
                    if not block:
                        selector.unregister(stream)
                        continue
                    target = out if key.data == "stdout" else err
                    target.extend(block)
                    limit = VALIDATOR_STDOUT_LIMIT if key.data == "stdout" else VALIDATOR_STDERR_LIMIT
                    if len(target) > limit:
                        failure = ValueError(f"Material validator {key.data} exceeds its bounded contract")
                        break
            if failure:
                break
            if _exited(process) and not selector.get_map():
                break
        if failure is None and not _exited(process):
            failure = ValueError(f"Material validator timed out after {timeout}s")
    except Exception as error:
        original = error
    finally:
        cleanup = []
        if process is not None:
            try:
                cleanup.extend(_cleanup_group(process))
            except Exception as error:
                cleanup.append(f"cleanup: {error}")
        if selector is not None:
            try:
                selector.close()
            except Exception as error:
                cleanup.append(f"selector close: {error}")
        for stream in streams:
            if stream is None:
                continue
            try:
                stream.close()
            except Exception as error:
                cleanup.append(f"close: {error}")
        if process is None:
            if isinstance(original, OSError):
                raise RuntimeError("Cannot execute sealed material validator: " + str(original)) from original
            if original is not None:
                raise original
            raise RuntimeError("Material validator did not start")
        if cleanup:
            cause = failure or original
            message = "Material validator cleanup failed: " + "; ".join(cleanup)
            if cause is not None:
                raise RuntimeError(str(cause) + "; " + message) from cause
            raise RuntimeError(message)
        if original is not None:
            raise original
    if failure is not None:
        raise failure
    result = subprocess.CompletedProcess(argv, process.returncode, bytes(out), bytes(err))
    return result


def verify_material_table(text, binding_path, state, trusted_binding_sha256, timeout=VALIDATOR_TIMEOUT):
    if len(text) > 2 * 1024 * 1024:
        raise ValueError("Material table exceeds the parser text bound")
    binary, record = load_validator_binding(binding_path, state, trusted_binding_sha256)
    lines = text.decode("ascii").splitlines()
    if len(lines) < 3:
        raise ValueError("Gameplay material table lacks canonical header/page rows")
    pages = integer(lines[1], 1, 64)
    if len(lines) < 3 + pages:
        raise ValueError("Gameplay material table lacks its binding count row")
    bindings = integer(lines[2 + pages], 0, 4096)
    binary_fd = _sealed_binary(record)
    try:
        result = _run_validator(binary_fd, text, timeout)
    finally:
        os.close(binary_fd)
    if result.returncode:
        detail = (result.stdout[:VALIDATOR_STDOUT_LIMIT] + b"\n" + result.stderr[:VALIDATOR_STDERR_LIMIT]).decode(
            "utf-8", errors="replace").strip()
        raise ValueError("Material table rejected by canonical parser: " + (detail or "exit " + str(result.returncode)))
    if len(result.stdout) > VALIDATOR_STDOUT_LIMIT or len(result.stderr) > VALIDATOR_STDERR_LIMIT:
        raise ValueError("Material validator output exceeds its bounded contract")
    if result.stderr:
        raise ValueError("Material validator wrote stderr on success: " + result.stderr.decode("utf-8", errors="replace").strip())
    matched = re.fullmatch(rb"CSMT1 pages=(0|[1-9][0-9]*) bindings=(0|[1-9][0-9]*)\n", result.stdout)
    if not matched:
        raise ValueError("Material validator stdout is not the canonical result line")
    if (int(matched.group(1)), int(matched.group(2))) != (pages, bindings):
        raise ValueError("Material validator counts disagree with the material table header")
    return record


def stage(output, profile_path, profile_sha256, material_validator_binding, trusted_validator_binding_sha256,
          expected_source_state=None, validator_timeout=VALIDATOR_TIMEOUT):
    before = validate_source_state(expected_source_state, REPO_ROOT)
    if before["changes"]:
        raise ValueError("Gameplay production staging requires exact committed-clean source/config, including with expected-source-state")
    output = output.resolve()
    common = Path(subprocess.check_output(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=REPO_ROOT, text=True).strip()).parent
    if output.exists() or not any(output.is_relative_to(root / ".audit") for root in (REPO_ROOT, common)):
        raise ValueError("Gameplay output must be fresh under the source or canonical checkout .audit")
    profile, payload, inputs = verified_profile(profile_path, profile_sha256)
    validator = verify_material_table(payload["materials.txt"], material_validator_binding, before,
                                     trusted_validator_binding_sha256, validator_timeout)
    manifest = {"revision": before["base_head"], "tracked_changes": bool(before["changes"]),
                "render_style": "bounded_gameplay_production", "gameplay_production": profile["mode"],
                "guest_replay": None, "guest_automatic": None, "player": None,
                "validator": {"binding_sha256": trusted_validator_binding_sha256, "token": validator["binding"],
                              "binary_sha256": validator["binary"]["sha256"]},
                "files": {name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "fnv1a32": checksum(data)}
                          for name, data in payload.items()}, "prepared_inputs": inputs,
                "integrity_claim": "SHA256 pinned at staging; executable FNV runtime corruption check, not authentication"}
    manifest["binding"] = staging_binding(manifest, before)
    verify_file_identities(inputs)
    validate_source_state(before, REPO_ROOT)
    directory = output / "assets/native-room"
    directory.mkdir(parents=True, exist_ok=False)
    for name, data in payload.items():
        write_new(directory / name, data)
    write_new(directory / "provenance.json", (json.dumps(manifest, indent=2) + "\n").encode())
    for name, text in (("asset_pins.hpp", asset_pins_text(manifest)), ("gameplay_pins.hpp", gameplay_pins_text(manifest)),
                       ("gameplay_files.cmake", gameplay_inventory_text(manifest))):
        write_new(output / name, text.encode())
    verify_file_identities(inputs)
    validate_source_state(before, REPO_ROOT)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--profile-sha256", required=True)
    parser.add_argument("--material-validator-binding", type=Path, required=True,
                        help="Build-generated provenance binding the validator binary to this exact source/build")
    parser.add_argument("--trusted-validator-binding-sha256", required=True,
                        help="Parent/review-supplied literal approval pin for the validator binding artifact")
    parser.add_argument("--expected-source-state", type=Path)
    args = parser.parse_args()
    print(json.dumps(stage(args.output, args.profile, args.profile_sha256, args.material_validator_binding,
                           args.trusted_validator_binding_sha256,
                           json.loads(args.expected_source_state.read_text()) if args.expected_source_state else None), indent=2))
