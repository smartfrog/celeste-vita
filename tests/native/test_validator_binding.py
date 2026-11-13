import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import bind_native_material_validator as validator_binding
import native_room_build


STATE = {"schema": 1, "base_head": "a" * 40, "changes": [], "paths": {},
         "sha256": "b" * 64, "count": 0, "bytes": 0}


class ValidatorBindingTests(unittest.TestCase):
    def test_validator_is_host_only_and_existing_vita_target_list_is_unchanged(self):
        self.assertEqual(native_room_build.TARGETS,
                         ("celeste_native_kernel", "celeste_room_diagnostic", "celeste_command_preflight",
                          "celeste_command_submission", "celeste_gameplay_bridge", "celeste_native_room"))
        self.assertNotIn(validator_binding.TARGET, native_room_build.TARGETS)
        self.assertIn("native_material_validator_binding",
                      (ROOT / "CMakeLists.txt").read_text())

    def test_wip_source_rejects_before_binding_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "binding.json"
            with patch.object(validator_binding, "validate_source_state",
                              return_value={"changes": [" M app.cpp"]}):
                with self.assertRaisesRegex(ValueError, "committed-clean"):
                    validator_binding.prepare(Path(directory), validator_binding.TARGET, output, {"explicit": "x"})
            self.assertFalse(output.exists())

    def test_prepare_writes_provenance_bound_to_exact_synthetic_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build = root / "build"
            folder = build / "CMakeFiles" / (validator_binding.TARGET + ".dir")
            folder.mkdir(parents=True)
            source = root / "tests/native/material_table_validator.cpp"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"fixture source")
            object_file = folder / "tests/native/material_table_validator.cpp.o"
            object_file.parent.mkdir(parents=True)
            object_file.write_bytes(b"fixture object")
            (build / "libceleste_command_preflight.a").write_bytes(b"fixture preflight")
            (build / "libceleste_native_kernel.a").write_bytes(b"fixture kernel")
            compiler = Path("/usr/bin/x86_64-linux-gnu-g++-15")
            (build / "CMakeCache.txt").write_text(
                f"CMAKE_HOME_DIRECTORY:STRING={root}\nCMAKE_CXX_COMPILER:FILEPATH={compiler}\n"
                "CMAKE_GENERATOR:STRING=Unix Makefiles\n")
            (folder / "flags.make").write_text("CXX_FLAGS = -O2\n")
            (folder / "link.txt").write_text(
                f"{compiler} tests/native/material_table_validator.cpp.o -o {validator_binding.TARGET} "
                "libceleste_command_preflight.a libceleste_native_kernel.a\n")
            binary = build / validator_binding.TARGET
            binary.write_bytes(b"fixture validator")
            state = STATE
            output = root / "binding.json"
            with patch.object(validator_binding, "REPO_ROOT", root), \
                 patch.object(validator_binding, "validate_source_state", return_value=state):
                record = validator_binding.prepare(build, validator_binding.TARGET, output, state)
            self.assertEqual(json.loads(output.read_text()), record)
            self.assertEqual(record["source"], {"schema": 1, "base_head": "a" * 40,
                                                "state_sha256": validator_binding.canonical_digest(state),
                                                "files_sha256": "b" * 64, "count": 0, "bytes": 0})

    def test_build_record_rejects_empty_graph(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build = root / "build"
            folder = build / "CMakeFiles" / (validator_binding.TARGET + ".dir")
            folder.mkdir(parents=True)
            compiler = Path("/usr/bin/x86_64-linux-gnu-g++-15")
            (build / "CMakeCache.txt").write_text(
                f"CMAKE_HOME_DIRECTORY:STRING={root}\nCMAKE_CXX_COMPILER:FILEPATH={compiler}\n"
                "CMAKE_GENERATOR:STRING=Unix Makefiles\n")
            (folder / "flags.make").write_text("CXX_FLAGS = -O2\n")
            (folder / "link.txt").write_text(f"{compiler} main.o -o {validator_binding.TARGET}\n")
            (build / validator_binding.TARGET).write_bytes(b"fixture validator")
            with patch.object(validator_binding, "REPO_ROOT", root):
                with self.assertRaisesRegex(ValueError, "target graph"):
                    validator_binding.build_record(build, validator_binding.TARGET, STATE)

    def test_binding_token_resigns_all_bound_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build = root / "build"
            folder = build / "CMakeFiles" / (validator_binding.TARGET + ".dir")
            folder.mkdir(parents=True)
            source = root / "tests/native/material_table_validator.cpp"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"fixture source")
            object_file = folder / "tests/native/material_table_validator.cpp.o"
            object_file.parent.mkdir(parents=True)
            object_file.write_bytes(b"fixture object")
            (build / "libceleste_command_preflight.a").write_bytes(b"fixture preflight")
            (build / "libceleste_native_kernel.a").write_bytes(b"fixture kernel")
            compiler = Path("/usr/bin/x86_64-linux-gnu-g++-15")
            (build / "CMakeCache.txt").write_text(
                f"CMAKE_HOME_DIRECTORY:STRING={root}\nCMAKE_CXX_COMPILER:FILEPATH={compiler}\n"
                "CMAKE_GENERATOR:STRING=Unix Makefiles\n")
            (folder / "flags.make").write_text("CXX_FLAGS = -O2\n")
            (folder / "link.txt").write_text(
                f"{compiler} tests/native/material_table_validator.cpp.o -o {validator_binding.TARGET} "
                "libceleste_command_preflight.a libceleste_native_kernel.a\n")
            binary = build / validator_binding.TARGET
            binary.write_bytes(b"fixture validator")
            state = STATE
            with patch.object(validator_binding, "REPO_ROOT", root):
                record = validator_binding.build_record(build, validator_binding.TARGET, state)
            self.assertEqual(record["binding"], validator_binding.TOKEN_PREFIX +
                             validator_binding.canonical_digest({k: v for k, v in record.items() if k != "binding"}))
            record["binary"]["sha256"] = hashlib.sha256(b"other").hexdigest()
            self.assertNotEqual(record["binding"], validator_binding.TOKEN_PREFIX +
                                validator_binding.canonical_digest({k: v for k, v in record.items() if k != "binding"}))
