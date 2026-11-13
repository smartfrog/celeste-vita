"""Bind the host material-table validator to exact source, binary and build inputs."""

import argparse
import json
from pathlib import Path

from native_room_revision import (REPO_ROOT, cache_values, canonical_digest, file_identity,
                                  source_binding, validate_source_state, verify_file_identities)

TARGET = "native_material_table_validator"
TOKEN_PREFIX = "CELESTE_MATERIAL_VALIDATOR_V1:"
EXPECTED_OBJECTS = ("tests/native/material_table_validator.cpp.o",)
EXPECTED_ARCHIVES = ("libceleste_command_preflight.a", "libceleste_native_kernel.a")


def build_record(build, target, state):
    build = build.resolve()
    cache = build / "CMakeCache.txt"
    values = cache_values(cache)
    if values.get("CMAKE_GENERATOR") != "Unix Makefiles" or Path(values["CMAKE_HOME_DIRECTORY"]).resolve() != REPO_ROOT.resolve():
        raise ValueError("Validator binding requires this exact source root and Unix Makefiles")
    folder = build / "CMakeFiles" / (target + ".dir")
    binary = build / target
    compiler = Path(values["CMAKE_CXX_COMPILER"])
    inputs = {"cmake_cache": cache, "flags": folder / "flags.make", "link": folder / "link.txt",
              "binary": binary, "compiler": compiler}
    objects = sorted(folder.rglob("*.o"))
    object_names = sorted(path.relative_to(folder).as_posix() for path in objects)
    archives = sorted({build / token for token in (folder / "link.txt").read_text().split()
                       if token.endswith(".a") and (build / token).is_file()})
    archive_names = sorted(path.name for path in archives)
    source_file = REPO_ROOT / "tests/native/material_table_validator.cpp"
    if object_names != list(EXPECTED_OBJECTS) or archive_names != list(EXPECTED_ARCHIVES):
        raise ValueError("Validator target graph differs from the expected single object and two project archives")
    for path in (*inputs.values(), *objects, *archives, source_file):
        if not path.is_file():
            raise ValueError("Missing validator build input: " + str(path))
    record = {
        "schema": 1,
        "target": target,
        "source": source_binding(state),
        "source_files": {"tests/native/material_table_validator.cpp": {"path": str(source_file.resolve()), **file_identity(source_file)}},
        "binary": {"path": str(binary.resolve()), **file_identity(binary)},
        "compiler": {"path": str(compiler.resolve()), **file_identity(compiler)},
        "build": {
            "cmake_cache": {"path": str(cache.resolve()), **file_identity(cache)},
            "flags": {"path": str((folder / "flags.make").resolve()), **file_identity(folder / "flags.make")},
            "link": {"path": str((folder / "link.txt").resolve()), **file_identity(folder / "link.txt")},
            "objects": {str(path.relative_to(folder).as_posix()): {**file_identity(path), "path": str(path.resolve())} for path in objects},
            "archives": {path.name: {**file_identity(path), "path": str(path.resolve())} for path in archives},
            "generator": values["CMAKE_GENERATOR"],
            "home": str(Path(values["CMAKE_HOME_DIRECTORY"]).resolve()),
        },
    }
    record["binding"] = TOKEN_PREFIX + canonical_digest(record)
    return record


def prepare(build, target, output, expected_source_state=None):
    before = validate_source_state(expected_source_state, REPO_ROOT)
    if before["changes"]:
        raise ValueError("Validator binding requires exact committed-clean source/config, including with expected-source-state")
    record = build_record(build, target, before)
    output = Path(output)
    text = json.dumps(record, indent=2) + "\n"
    if not output.exists() or output.read_text() != text:
        output.write_text(text)
    verify_file_identities({meta["path"]: {"bytes": meta["bytes"], "sha256": meta["sha256"]}
                            for meta in record["source_files"].values()})
    for group in ("objects", "archives"):
        verify_file_identities({meta["path"]: {"bytes": meta["bytes"], "sha256": meta["sha256"]}
                                for meta in record["build"][group].values()})
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--target", default=TARGET)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-source-state", type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.build, args.target, args.output,
                             json.loads(args.expected_source_state.read_text()) if args.expected_source_state else None), indent=2))
