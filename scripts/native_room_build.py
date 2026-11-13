"""Bind the compiled resident image and SDK SELF chain to exact source, assets and build inputs."""

import argparse
import json
from pathlib import Path
import shlex
import struct
import subprocess
import tempfile

from native_room_revision import (REPO_ROOT, canonical_digest, file_identity, source_binding,
                                  staging_binding, validate_source_state, verify_file_identities, cache_values)
from stage_native_room import asset_pins_text, checksum
from native_room_automatic import verify_automatic_intent
from native_room_dash_probe import verify_dash_probe_intent
from stage_native_gameplay import gameplay_pins_text, gameplay_inventory_text

TARGETS = ("celeste_native_kernel", "celeste_room_diagnostic", "celeste_command_preflight",
           "celeste_command_submission", "celeste_gameplay_bridge", "celeste_native_room")


def target_directory(build, target):
    return build / ("src/vita" if target == "celeste_native_room" else "") / "CMakeFiles" / (target + ".dir")


def staging_inputs(staging, state):
    directory = staging / "assets/native-room"
    manifest_path = directory / "provenance.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("binding") != staging_binding(manifest, state):
        raise ValueError("Staging binding does not match the complete expected source state and provenance")
    if (staging / "asset_pins.hpp").read_text() != asset_pins_text(manifest):
        raise ValueError("Generated asset pins differ from their bound staging provenance")
    if {p.name for p in directory.iterdir()} != set(manifest["files"]) | {"provenance.json"}:
        raise ValueError("Unexpected staged payload inventory")
    inputs = {str(manifest_path.resolve()): file_identity(manifest_path),
              str((staging / "asset_pins.hpp").resolve()): file_identity(staging / "asset_pins.hpp")}
    if manifest.get("gameplay_production"):
        for name, expected in (("gameplay_pins.hpp", gameplay_pins_text(manifest)),
                               ("gameplay_files.cmake", gameplay_inventory_text(manifest))):
            path = staging / name
            if path.read_text() != expected:
                raise ValueError("Gameplay generated inventory/pins differ from staging provenance: " + name)
            inputs[str(path.resolve())] = file_identity(path)
    for name, metadata in manifest["files"].items():
        path = directory / name
        identity = file_identity(path)
        if identity != {key: metadata[key] for key in ("bytes", "sha256")} or checksum(path.read_bytes()) != metadata["fnv1a32"]:
            raise ValueError("Staged payload differs from its pins: " + name)
        inputs[str(path.resolve())] = identity
    verify_file_identities(manifest["prepared_inputs"])
    inputs.update(manifest["prepared_inputs"])
    return manifest, inputs


def sdk_command(path, tool):
    commands = []
    for line in path.read_text().splitlines():
        if line.startswith("\t") and "&&" in line:
            command = shlex.split(line.split("&&", 1)[1])
            if command and Path(command[0]).name == tool:
                commands.append(command)
    if len(commands) != 1:
        raise ValueError("Expected exactly one generated SDK command: " + str(path))
    return commands[0]


def build_capture_policy(cache, defines):
    modes = {}
    for name in ("ANIMATED_PLAYER", "GUEST_REPLAY", "CAPTURE_AFTER_WALL_JUMP", "CAPTURE_AFTER_CLIMB", "DASH_PROBE"):
        option = "CELESTE_ROOM_" + name
        enabled = cache.get(option, "OFF") == "ON"
        if ("-D" + option in defines) != enabled:
            raise ValueError("Native capture compile definition differs from its cache pin: " + option)
        modes[name] = enabled
    if modes["CAPTURE_AFTER_WALL_JUMP"] and modes["CAPTURE_AFTER_CLIMB"]:
        raise ValueError("Native capture overrides are mutually exclusive")
    if modes["DASH_PROBE"]:
        if not modes["ANIMATED_PLAYER"] or modes["GUEST_REPLAY"] or modes["CAPTURE_AFTER_WALL_JUMP"] or modes["CAPTURE_AFTER_CLIMB"]:
            raise ValueError("Dash probe requires the animated automatic lifecycle and its own capture policy")
        return "dash_trails"
    if modes["CAPTURE_AFTER_WALL_JUMP"]:
        return "wall_jump"
    if modes["CAPTURE_AFTER_CLIMB"]:
        return "climb"
    return "initial_respawn" if modes["ANIMATED_PLAYER"] and not modes["GUEST_REPLAY"] else "spawn"


def build_context(build, staging, state, expected_mode):
    manifest, inputs = staging_inputs(staging, state)
    build, staging = build.resolve(), staging.resolve()
    cache_path = build / "CMakeCache.txt"
    cache = cache_values(cache_path)
    automatic = cache.get("CELESTE_ROOM_GUEST_AUTOMATIC", "OFF") == "ON"
    probe = cache.get("CELESTE_ROOM_DASH_PROBE", "OFF") == "ON"
    verify_automatic_intent(manifest, automatic, REPO_ROOT)
    verify_dash_probe_intent(manifest, probe, REPO_ROOT)
    if automatic and (probe or cache.get("CELESTE_ROOM_GUEST_REPLAY", "OFF") == "ON" or cache.get("CELESTE_ROOM_ANIMATED_PLAYER") != "ON"):
        raise ValueError("Guest automatic build mode requires animated Player and excludes legacy replay")
    flags = (target_directory(build, "celeste_native_room") / "flags.make").read_text()
    defines = shlex.split(" ".join(line.split("=", 1)[1] for line in flags.splitlines() if line.startswith("CXX_DEFINES =")))
    if ("-DCELESTE_ROOM_GUEST_AUTOMATIC" in defines) != automatic:
        raise ValueError("Guest automatic compile definition differs from build mode")
    capture_policy = build_capture_policy(cache, defines)
    gameplay = cache.get("CELESTE_ROOM_GAMEPLAY_PRODUCTION", "OFF") == "ON"
    if (("-DCELESTE_ROOM_GAMEPLAY_PRODUCTION" in defines) != gameplay or
            manifest.get("gameplay_production") != ("automatic-transition" if gameplay else None)):
        raise ValueError("Gameplay production cache/compile definition/staging intent disagree")
    if gameplay:
        if state["changes"]:
            raise ValueError("Gameplay production build requires exact committed-clean source/config, including with expected-source-state")
        if automatic or probe or cache.get("CELESTE_ROOM_ANIMATED_PLAYER") != "ON" or capture_policy != "initial_respawn" or cache.get("CELESTE_ROOM_GUEST_REPLAY", "OFF") == "ON":
            raise ValueError("Gameplay production only supports the bounded automatic-transition profile")
        capture_policy = "bounded_gameplay_production"
    if cache["CMAKE_GENERATOR"] != "Unix Makefiles" or Path(cache["CMAKE_HOME_DIRECTORY"]).resolve() != REPO_ROOT.resolve():
        raise ValueError("Exact native binding requires this source root and Unix Makefiles")
    if Path(cache["CELESTE_ROOM_STAGING"]).resolve() != staging:
        raise ValueError("Build uses a different staging directory")
    expected_file = cache.get("CELESTE_EXPECTED_SOURCE_STATE", "")
    if bool(expected_file) != expected_mode:
        raise ValueError("Build and verifier expected-source-state opt-in differ")
    if expected_file and json.loads(Path(expected_file).read_text()) != state:
        raise ValueError("Build expected-source-state file differs from the complete code identity")

    def pin(path):
        path = path.resolve()
        inputs[str(path)] = file_identity(path)

    pin(cache_path)
    if expected_file:
        pin(Path(expected_file))
    toolchain = Path(cache["CMAKE_TOOLCHAIN_FILE"])
    sdk = toolchain.resolve().parents[1]
    for path in (toolchain, sdk / "share/vita.cmake", Path(cache["CMAKE_CXX_COMPILER"]),
                 Path(cache["CMAKE_LINKER"]), Path(cache["CELESTE_VITAGL_LIBRARY"])):
        pin(path)
    for key in ("CMAKE_AR", "CMAKE_RANLIB"):
        if key in cache:
            pin(Path(cache[key]))
    for target in TARGETS:
        folder = target_directory(build, target)
        for name in ("flags.make", "link.txt"):
            pin(folder / name)
        flags = " ".join(line.split("=", 1)[1] for line in (folder / "flags.make").read_text().splitlines() if line.startswith(("CXX_INCLUDES =", "CXX_FLAGS =")))
        arguments = shlex.split(flags)
        for index, argument in enumerate(arguments):
            include = arguments[index+1] if argument == "-I" else argument[2:] if argument.startswith("-I") else None
            if include:
                for header in Path(include).rglob("*"):
                    if header.is_file() and header.suffix in (".h", ".hpp", ".inl"):
                        pin(header)
    image = build / "src/vita"
    elf_make = image / "CMakeFiles/celeste_native_room-velf.dir/build.make"
    self_make = image / "CMakeFiles/eboot.bin-self.dir/build.make"
    elf = sdk_command(elf_make, "vita-elf-create")
    self_command = sdk_command(self_make, "vita-make-fself")
    if (elf != [str(sdk / "bin/vita-elf-create"), str(image / "celeste_native_room"), str(image / "celeste_native_room.velf")] or
            self_command != [str(sdk / "bin/vita-make-fself"), "-c", "-s", str(image / "celeste_native_room.velf"), str(image / "eboot.bin.out")]):
        raise ValueError("Unsupported SDK ELF/SELF conversion flags or paths")
    for path in (elf_make, self_make, Path(elf[0]), Path(self_command[0])):
        pin(path)
    link = shlex.split((image / "CMakeFiles/celeste_native_room.dir/link.txt").read_text())
    search_flags = [argument for argument in link[1:] if argument.startswith(("-mcpu=", "-mfpu=", "-mfloat-abi=", "--sysroot=", "-L", "-B")) or argument in ("-mthumb", "-marm")]
    for argument in link[1:]:
        if argument.startswith("-l"):
            library = argument[3:] if argument.startswith("-l:") else "lib" + argument[2:] + ".a"
            resolved = subprocess.check_output([cache["CMAKE_CXX_COMPILER"], *search_flags, "-print-file-name=" + library], text=True).strip()
            path = Path(resolved)
            if not path.is_absolute():
                raise ValueError("Cannot pin linked SDK archive: " + library)
            pin(path)
        elif argument.endswith(".a"):
            path = (image / argument).resolve()
            if not path.is_relative_to(build):
                pin(path)
    context = {"schema": 1, "source": source_binding(state), "staging": manifest["binding"], "capture_policy": capture_policy, "inputs": inputs}
    return {"context": context, "token": "CELESTE_NATIVE_BINDING_V1:" + canonical_digest(context)}


def binding_source(token):
    return ('extern "C" {\n'
            '__attribute__((used, section(".rodata.celeste_binding")))\n'
            f'extern const char celeste_native_build_binding[] = "{token}";\n'
            '}\n')


def prepare(build, staging, expected_source_state=None):
    before = validate_source_state(expected_source_state, REPO_ROOT)
    record = build_context(build, staging, before, expected_source_state is not None)
    image = build / "src/vita"
    receipt = image / "native-build-binding.json"
    if receipt.exists() and json.loads(receipt.read_text()) != record:
        raise ValueError("Changed source/assets/build inputs require a fresh build directory")
    if not receipt.exists():
        artifacts = [build / "libceleste_native_kernel.a", build / "libceleste_room_diagnostic.a",
                     build / "libceleste_command_preflight.a", build / "libceleste_command_submission.a", build / "libceleste_gameplay_bridge.a",
                     image / "celeste_native_room", image / "celeste_native_room.velf", image / "eboot.bin"]
        for target in TARGETS:
            folder = target_directory(build, target)
            artifacts.extend(path for path in folder.rglob("*") if path.suffix in (".o", ".obj"))
        if any(path.exists() for path in artifacts):
            raise ValueError("Unbound existing artifacts require a fresh build directory")
    for name, text in (("native-build-binding.cpp", binding_source(record["token"])),
                       ("native-build-binding.json", json.dumps(record, indent=2) + "\n")):
        path = image / name
        if not path.exists() or path.read_text() != text:
            path.write_text(text)
    verify_file_identities(record["context"]["inputs"])
    validate_source_state(before, REPO_ROOT)
    return record


def resident_binding(image, token):
    if len(image) < 52 or image[:7] != b"\x7fELF\x01\x01\x01" or struct.unpack_from("<H", image, 18)[0] != 40:
        raise ValueError("Expected ELF32 little-endian ARM executable")
    offset = struct.unpack_from("<I", image, 28)[0]
    size, count = struct.unpack_from("<HH", image, 42)
    if size != 32 or not count or offset + count * size > len(image):
        raise ValueError("Invalid bounded ELF program headers")
    for index in range(count):
        kind, start, _, _, length, _, _, _ = struct.unpack_from("<8I", image, offset + index * size)
        if start + length > len(image):
            raise ValueError("Truncated ELF load segment")
        if kind == 1 and token.encode() + b"\0" in image[start:start+length]:
            return
    raise ValueError("ELF lacks its exact resident build binding")


def verify_build(build, staging, expected_source_state=None):
    before = validate_source_state(expected_source_state, REPO_ROOT)
    record = build_context(build, staging, before, expected_source_state is not None)
    image = build / "src/vita"
    if json.loads((image / "native-build-binding.json").read_text()) != record:
        raise ValueError("Generated build binding record differs from current expected inputs")
    if (image / "native-build-binding.cpp").read_text() != binding_source(record["token"]):
        raise ValueError("Generated build binding source changed")
    artifacts = {str((image / name).resolve()): file_identity(image / name) for name in
                 ("celeste_native_room", "celeste_native_room.velf", "eboot.bin", "native-build-binding.cpp", "native-build-binding.json")}
    resident_binding((image / "celeste_native_room").read_bytes(), record["token"])
    sdk = Path(cache_values(build / "CMakeCache.txt")["CMAKE_TOOLCHAIN_FILE"]).resolve().parents[1]
    def run_sdk(command):
        try:
            subprocess.run(command, check=True, capture_output=True)
        except subprocess.CalledProcessError as error:
            output = (error.stdout or b"") + (error.stderr or b"")
            raise RuntimeError("Pinned SDK conversion failed: " + output.decode(errors="replace")) from error

    with tempfile.TemporaryDirectory(prefix="self-verification-", dir=build) as directory:
        velf, self_path = Path(directory) / "verified.velf", Path(directory) / "verified.self"
        run_sdk([str(sdk / "bin/vita-elf-create"), str(image / "celeste_native_room"), str(velf)])
        if velf.read_bytes() != (image / "celeste_native_room.velf").read_bytes():
            raise ValueError("Build VELF differs from the pinned SDK conversion of this ELF")
        run_sdk([str(sdk / "bin/vita-make-fself"), "-c", "-s", str(velf), str(self_path)])
        if self_path.read_bytes() != (image / "eboot.bin").read_bytes():
            raise ValueError("Build SELF differs from the pinned SDK conversion of this ELF/VELF")
    verify_file_identities(record["context"]["inputs"])
    verify_file_identities(artifacts)
    validate_source_state(before, REPO_ROOT)
    return {"token": record["token"], "source": record["context"]["source"], "capture_policy": record["context"]["capture_policy"], "inputs": record["context"]["inputs"],
            "artifacts": artifacts, "self_matches_rebuilt_chain": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--expected-source-state", type=Path)
    args = parser.parse_args()
    prepare(args.build, args.staging, json.loads(args.expected_source_state.read_text()) if args.expected_source_state else None)
