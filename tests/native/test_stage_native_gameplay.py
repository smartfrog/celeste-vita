import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from bind_native_material_validator import TARGET, build_record
from native_room_revision import canonical_digest, file_identity
from stage_native_gameplay import (METADATA, gameplay_inventory_text, gameplay_pins_text, stage,
                                   verified_profile, verify_material_table)

STATE = {"schema": 1, "base_head": "a" * 40, "changes": [], "paths": {}, "sha256": "b" * 64,
         "count": 0, "bytes": 0}


def resign(record):
    record = {key: value for key, value in record.items() if key != "binding"}
    record["binding"] = "CELESTE_MATERIAL_VALIDATOR_V1:" + canonical_digest(record)
    return record


class GameplayStageTests(unittest.TestCase):
    def profile(self, root):
        files = {}
        for name, magic in METADATA.items():
            data = (magic + "\nfixture\n").encode()
            if name == "materials.txt":
                data = b"CSMT1\n1\n7 1 1\n0\n"
            path = root / name
            path.write_bytes(data)
            files[name] = {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        page = root / "pixel"
        page.write_bytes(b"rgba")
        files["page7.rgba"] = {"path": str(page), "bytes": 4, "sha256": hashlib.sha256(b"rgba").hexdigest()}
        profile = {"schema": 1, "mode": "automatic-transition", "files": files}
        path = root / "profile.json"
        path.write_text(json.dumps(profile))
        return path

    def material_profile(self, root, materials, page=b"rgba"):
        profile = self.profile(root)
        (root / "materials.txt").write_bytes(materials)
        (root / "pixel").write_bytes(page)
        data = json.loads(profile.read_text())
        for name, payload in (("materials.txt", materials), ("page7.rgba", page)):
            data["files"][name].update(bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
        profile.write_text(json.dumps(data))
        return profile

    def fake_build(self, root, script=None, binary=None):
        build = root / "build"
        folder = build / "CMakeFiles" / (TARGET + ".dir")
        source = root / "tests/native/material_table_validator.cpp"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"synthetic validator source")
        object_file = folder / "tests/native/material_table_validator.cpp.o"
        object_file.parent.mkdir(parents=True)
        object_file.write_bytes(b"synthetic validator object")
        (build / "libceleste_command_preflight.a").write_bytes(b"synthetic preflight archive")
        (build / "libceleste_native_kernel.a").write_bytes(b"synthetic kernel archive")
        compiler = Path(shutil.which("c++")).resolve()
        (build / "CMakeCache.txt").write_text(
            f"CMAKE_HOME_DIRECTORY:STRING={root}\nCMAKE_CXX_COMPILER:FILEPATH={compiler}\n"
            "CMAKE_GENERATOR:STRING=Unix Makefiles\n")
        (folder / "flags.make").write_text("CXX_FLAGS = -O2\n")
        (folder / "link.txt").write_text(
            f"{compiler} tests/native/material_table_validator.cpp.o -o {TARGET} "
            "libceleste_command_preflight.a libceleste_native_kernel.a\n")
        target = build / TARGET
        if binary is not None:
            shutil.copy2(binary, target)
        else:
            target.write_text(script if script is not None else "#!/bin/sh\nprintf 'CSMT1 pages=1 bindings=0\\n'\n")
        target.chmod(0o755)
        return build

    def binding(self, root, build, state=STATE):
        with patch("bind_native_material_validator.REPO_ROOT", root):
            record = build_record(build, TARGET, state)
        path = root / "validator-binding.json"
        path.write_text(json.dumps(record))
        return path

    def fake_binding(self, root, script=None, state=STATE):
        return self.binding(root, self.fake_build(root, script), state)

    @staticmethod
    def trusted(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def real_binding(self, root, state=STATE):
        validator = Path(os.environ["CELESTE_MATERIAL_VALIDATOR"]).resolve()
        return self.binding(root, self.fake_build(root, binary=validator), state)

    def verify_fake(self, root, binding, text, timeout=10, trusted=None):
        with patch("stage_native_gameplay.REPO_ROOT", root):
            return verify_material_table(text, binding, STATE, trusted or self.trusted(binding), timeout)

    def stage_synthetic(self, profile, binding, timeout=10):
        root = profile.parent
        output = root / ".audit/stage"
        with patch("stage_native_gameplay.REPO_ROOT", root), \
             patch("bind_native_material_validator.REPO_ROOT", root), \
             patch("stage_native_gameplay.validate_source_state", return_value=STATE), \
             patch("stage_native_gameplay.subprocess.check_output", return_value=str(root / ".git")):
            return output, stage(output, profile, hashlib.sha256(profile.read_bytes()).hexdigest(),
                                 binding, self.trusted(binding), STATE, timeout)

    def test_validates_complete_synthetic_inventory_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = self.profile(Path(directory))
            result, payload, inputs = verified_profile(profile, hashlib.sha256(profile.read_bytes()).hexdigest())
            self.assertEqual(set(payload), set(METADATA) | {"page7.rgba"})
            self.assertEqual(len(inputs), len(payload) + 1)
            self.assertEqual(result["mode"], "automatic-transition")

    def test_changed_pixel_rejects_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = self.profile(root)
            (root / "pixel").write_bytes(b"evil")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                verified_profile(profile, hashlib.sha256(profile.read_bytes()).hexdigest())

    def test_missing_file_rejects_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = self.profile(root)
            (root / "pixel").unlink()
            with self.assertRaises(FileNotFoundError):
                verified_profile(profile, hashlib.sha256(profile.read_bytes()).hexdigest())

    def test_unsupported_profile_rejects_before_file_io(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.write_text(json.dumps({"schema": 1, "mode": "guess", "files": {}}))
            with self.assertRaisesRegex(ValueError, "automatic-transition"):
                verified_profile(path, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_noncanonical_material_page_row_rejected_parameterized(self):
        for row in ("007 1 1", "+7 1 1", "-0 1 1", "7 01 1", "7 1 +1", "2147483648 1 1"):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                profile = self.profile(root)
                data = ("CSMT1\n1\n" + row + "\n0\n").encode()
                (root / "materials.txt").write_bytes(data)
                profile_data = json.loads(profile.read_text())
                pin = profile_data["files"]["materials.txt"]
                pin.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
                profile.write_text(json.dumps(profile_data))
                with self.assertRaises(ValueError, msg=row):
                    verified_profile(profile, hashlib.sha256(profile.read_bytes()).hexdigest())

    def test_fake_zero_exit_executable_without_binding_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / "validator"
            fake.write_text("#!/bin/sh\nexit 0\n")
            fake.chmod(0o755)
            with self.assertRaises(ValueError):
                verify_material_table(b"not a material table", fake, STATE, "0" * 64)

    def test_fake_binary_outside_bound_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = self.fake_binding(root)
            record = json.loads(binding.read_text())
            other = root / "attacker-validator"
            other.write_text("#!/bin/sh\nprintf 'CSMT1 pages=1 bindings=0\\n'\n")
            other.chmod(0o755)
            record["binary"] = {"path": str(other), **file_identity(other)}
            binding.write_text(json.dumps(resign(record)))
            with self.assertRaisesRegex(ValueError, "bound host target"):
                self.verify_fake(root, binding, b"CSMT1\n1\n7 1 1\n0\n")

    def test_wrong_hash_wrong_build_and_stale_source_are_rejected_parameterized(self):
        for kind in range(3):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                binding = self.fake_binding(root)
                record = json.loads(binding.read_text())
                if kind == 0:
                    build = root / "build"
                    (build / TARGET).write_text("#!/bin/sh\nexit 0\n")
                elif kind == 1:
                    (root / "build/CMakeCache.txt").write_text("CMAKE_HOME_DIRECTORY:STRING=/elsewhere\n")
                else:
                    record["source"] = dict(record["source"], base_head="c" * 40)
                    binding.write_text(json.dumps(resign(record)))
                with self.assertRaises(ValueError):
                    self.verify_fake(root, binding, b"CSMT1\n1\n7 1 1\n0\n")

    def test_zero_exit_bad_stdout_is_rejected_parameterized(self):
        for script in ("#!/bin/sh\nexit 0\n",
                       "#!/bin/sh\nprintf 'garbage\\n'\n",
                       "#!/bin/sh\nprintf 'CSMT1 pages=1 bindings=0\\nextra\\n'\n",
                       "#!/bin/sh\nprintf 'CSMT1 pages=2 bindings=0\\n'\n",
                       "#!/bin/sh\nprintf 'CSMT1 pages=01 bindings=0\\n'\n",
                       "#!/bin/sh\nprintf 'CSMT1 pages=1 bindings=0\\n' >&2\n"):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                binding = self.fake_binding(root, script)
                with self.assertRaises(ValueError, msg=script):
                    self.verify_fake(root, binding, b"CSMT1\n1\n7 1 1\n0\n")

    def test_validator_timeout_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = self.fake_binding(root, "#!/bin/sh\nsleep 5\n")
            with self.assertRaisesRegex(ValueError, "timed out"):
                self.verify_fake(root, binding, b"CSMT1\n1\n7 1 1\n0\n", timeout=0.2)

    def test_nonzero_validator_rejects_with_bounded_context(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = self.fake_binding(root, "#!/bin/sh\necho 'bad table' >&2\nexit 3\n")
            with self.assertRaisesRegex(ValueError, "bad table"):
                self.verify_fake(root, binding, b"CSMT1\n1\n7 1 1\n0\n")


    def test_self_consistent_fake_binding_with_different_external_approval_rejects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = self.fake_binding(root)
            with self.assertRaisesRegex(ValueError, "externally approved"):
                self.verify_fake(root, binding, b"CSMT1\n1\n7 1 1\n0\n", trusted="f" * 64)

    @unittest.skipUnless(os.environ.get("CELESTE_MATERIAL_VALIDATOR"), "requires the exact-source material validator")
    def test_fake_self_consistent_binding_with_real_external_approval_rejects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = self.real_binding(root)
            approved = self.trusted(real)
            fake = self.fake_binding(root / "fake")
            with self.assertRaisesRegex(ValueError, "externally approved"):
                self.verify_fake(root / "fake", fake, b"CSMT1\n1\n7 1 1\n0\n", trusted=approved)

    def test_empty_or_wrong_target_graph_is_rejected_parameterized(self):
        for group, value in (("objects", {}), ("archives", {}),
                             ("objects", {"wrong.o": {"path": "/tmp/wrong", "bytes": 1, "sha256": "0" * 64}}),
                             ("archives", {"libevil.a": {"path": "/tmp/libevil.a", "bytes": 1, "sha256": "0" * 64}})):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                binding = self.fake_binding(root)
                record = json.loads(binding.read_text())
                record["build"][group] = value
                binding.write_text(json.dumps(resign(record)))
                with self.assertRaisesRegex(ValueError, "target graph|dependency"):
                    self.verify_fake(root, binding, b"CSMT1\n1\n7 1 1\n0\n")

    def test_same_path_binary_swap_after_binding_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = self.fake_binding(root)
            (root / "build" / TARGET).write_text("#!/bin/sh\nexit 0\n")
            (root / "build" / TARGET).chmod(0o755)
            with self.assertRaisesRegex(ValueError, "binary differs"):
                self.verify_fake(root, binding, b"CSMT1\n1\n7 1 1\n0\n")



    def test_nonzero_exit_still_terminates_redirected_descendant(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pids = root / "nonzero-pids"
            script = f"""#!/bin/sh
echo 'bad table' >&2
sleep 30 >/dev/null 2>&1 &
echo $! > {pids}
exit 7
"""
            binding = self.fake_binding(root, script)
            with self.assertRaisesRegex(ValueError, "bad table"):
                self.verify_fake(root, binding, b"CSMT1\n1\n7 1 1\n0\n")
            import time
            values = [int(line) for line in pids.read_text().splitlines()]
            self.assertEqual(len(values), 1)
            alive = True
            for _ in range(40):
                if not Path("/proc", str(values[0])).exists():
                    alive = False
                    break
                time.sleep(0.05)
            if alive:
                import os
                import signal
                try:
                    os.kill(values[0], signal.SIGKILL)
                except ProcessLookupError:
                    pass
            self.assertFalse(alive, "nonzero validator exit must still terminate its process group")


    def _captured_run_error(self, root, binding, patcher):
        import stage_native_gameplay as stage_module
        captured = {}
        real_popen = stage_module.subprocess.Popen
        def capture(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            captured["pid"] = process.pid
            return process
        with patch.object(stage_module.subprocess, "Popen", side_effect=capture), patcher:
            with self.assertRaises(Exception) as caught:
                self.verify_fake(root, binding, b"CSMT1\n1\n7 1 1\n0\n")
        pid = captured["pid"]
        import time
        alive = True
        for _ in range(40):
            if not Path("/proc", str(pid)).exists():
                alive = False
                break
            time.sleep(0.05)
        if alive:
            import os
            import signal
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except Exception:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        self.assertFalse(alive, "partially initialized validator must be killed and reaped")
        return caught.exception

    def test_set_blocking_failure_cleans_started_validator(self):
        import stage_native_gameplay as stage_module
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = self.fake_binding(root, "#!/bin/sh\nsleep 30\n")
            patcher = patch.object(stage_module.os, "set_blocking",
                side_effect=RuntimeError("monkey set_blocking failure"))
            error = self._captured_run_error(root, binding, patcher)
            self.assertIn("monkey set_blocking failure", str(error))

    def test_selector_creation_failure_cleans_started_validator(self):
        import stage_native_gameplay as stage_module
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = self.fake_binding(root, "#!/bin/sh\nsleep 30\n")
            patcher = patch.object(stage_module.selectors, "DefaultSelector",
                side_effect=RuntimeError("selector creation failure"))
            error = self._captured_run_error(root, binding, patcher)
            self.assertIn("selector creation failure", str(error))

    def test_selector_registration_failure_cleans_started_validator(self):
        import stage_native_gameplay as stage_module
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = self.fake_binding(root, "#!/bin/sh\nsleep 30\n")
            real = stage_module.selectors.DefaultSelector
            class Broken(real):
                def register(self, *args, **kwargs):
                    raise RuntimeError("selector registration failure")
            patcher = patch.object(stage_module.selectors, "DefaultSelector", Broken)
            error = self._captured_run_error(root, binding, patcher)
            self.assertIn("selector registration failure", str(error))

    def test_popen_never_started_has_no_cleanup_call(self):
        import stage_native_gameplay as stage_module
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = self.fake_binding(root)
            calls = []
            with patch.object(stage_module.subprocess, "Popen", side_effect=OSError("no exec")), \
                 patch.object(stage_module, "_cleanup_group", side_effect=lambda process: calls.append(process) or []):
                with self.assertRaisesRegex(RuntimeError, "Cannot execute sealed material validator"):
                    self.verify_fake(root, binding, b"CSMT1\n1\n7 1 1\n0\n")
            self.assertEqual(calls, [])

    def test_normal_exit_terminates_redirected_grandchild(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pids = root / "normal-exit-pids"
            script = f"""#!/bin/sh
printf 'CSMT1 pages=1 bindings=0\\n'
sleep 30 >/dev/null 2>&1 &
echo $! > {pids}
exit 0
"""
            binding = self.fake_binding(root, script)
            self.verify_fake(root, binding, b"CSMT1\n1\n7 1 1\n0\n")
            import time
            values = []
            for _ in range(40):
                if pids.exists():
                    values = [int(line) for line in pids.read_text().splitlines()]
                    if values:
                        break
                time.sleep(0.05)
            self.assertEqual(len(values), 1)
            import time
            alive = True
            for _ in range(40):
                if not Path("/proc", str(values[0])).exists():
                    alive = False
                    break
                time.sleep(0.05)
            if alive:
                import os
                import signal
                try:
                    os.kill(values[0], signal.SIGKILL)
                except ProcessLookupError:
                    pass
            self.assertFalse(alive, "normal parent exit must still terminate the owned process group")

    def test_timeout_kills_and_reaps_normal_grandchild(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pids = root / "timeout-pids"
            script = f"""#!/bin/sh
echo $$ > {pids}
sleep 30 &
echo $! >> {pids}
sleep 30
"""
            binding = self.fake_binding(root, script)
            with self.assertRaisesRegex(ValueError, "timed out"):
                self.verify_fake(root, binding, b"CSMT1\n1\n7 1 1\n0\n", timeout=0.3)
            values = [int(line) for line in pids.read_text().splitlines()]
            self.assertEqual(len(values), 2)
            import time
            for _ in range(40):
                if not any(Path("/proc", str(pid)).exists() for pid in values):
                    break
                time.sleep(0.05)
            self.assertFalse(any(Path("/proc", str(pid)).exists() for pid in values),
                             "validator process group must be gone")

    def test_huge_stdout_and_stderr_are_bounded_and_killed_parameterized(self):
        for stream in ("stdout", "stderr"):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                if stream == "stdout":
                    script = "#!/bin/sh\nhead -c 100000 /dev/zero | tr '\\0' x\nsleep 5\n"
                else:
                    script = "#!/bin/sh\nhead -c 100000 /dev/zero | tr '\\0' x >&2\nsleep 5\n"
                binding = self.fake_binding(root, script)
                with self.assertRaisesRegex(ValueError, stream + " exceeds"):
                    self.verify_fake(root, binding, b"CSMT1\n1\n7 1 1\n0\n", timeout=2)

    @unittest.skipUnless(os.environ.get("CELESTE_MATERIAL_VALIDATOR"), "requires the exact-source material validator")
    def test_real_validator_bound_to_existing_host_build_accepts_full_binding(self):
        validator = Path(os.environ["CELESTE_MATERIAL_VALIDATOR"]).resolve()
        record = build_record(validator.parent, TARGET, STATE)
        with tempfile.TemporaryDirectory() as directory:
            binding = Path(directory) / "binding.json"
            binding.write_text(json.dumps(record))
            verify_material_table(b"CSMT1\n1\n7 1 1\n0\n", binding, STATE, self.trusted(binding))

    @unittest.skipUnless(os.environ.get("CELESTE_MATERIAL_VALIDATOR"), "requires the exact-source material validator")
    def test_real_validator_accepts_full_stage_and_emits_complete_output(self):
        materials = (b"CSMT1\n1\n7 1 1\n1\n64 64 7 0 0 1 1 0 1\n"
                     b"Synthetic 0 0 1 1 0 0 1 1 synthetic/frame\nsynthetic/alias\n")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".audit").mkdir()
            profile = self.material_profile(root, materials)
            binding = self.real_binding(root)
            output, manifest = self.stage_synthetic(profile, binding)
            self.assertTrue((output / "assets/native-room/materials.txt").is_file())
            self.assertEqual(manifest["files"]["materials.txt"]["sha256"], hashlib.sha256(materials).hexdigest())

    @unittest.skipUnless(os.environ.get("CELESTE_MATERIAL_VALIDATOR"), "requires the exact-source material validator")
    def test_real_validator_rejects_invalid_binding_before_output(self):
        materials = (b"CSMT1\n1\n7 1 1\n1\n64 64 7 31 0 1 1 0 1\n"
                     b"Synthetic 0 0 1 1 0 0 1 1 synthetic/frame\nsynthetic/alias\n")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".audit").mkdir()
            profile = self.material_profile(root, materials)
            with self.assertRaisesRegex(ValueError, "canonical parser"):
                self.stage_synthetic(profile, self.real_binding(root))
            self.assertFalse((root / ".audit/stage").exists())

    @unittest.skipUnless(os.environ.get("CELESTE_MATERIAL_VALIDATOR"), "requires the exact-source material validator")
    def test_real_validator_rejects_invalid_material_metadata_before_output(self):
        materials = (b"CSMT1\n1\n7 1 1\n1\n64 64 7 0 0 1 1 0 0\n"
                     b"Synthetic 1 1 0 1 0 0 1 1 synthetic/frame\n")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".audit").mkdir()
            profile = self.material_profile(root, materials)
            with self.assertRaisesRegex(ValueError, "canonical parser"):
                self.stage_synthetic(profile, self.real_binding(root))
            self.assertFalse((root / ".audit/stage").exists())

    def test_actual_stage_rejects_wip_before_output_or_profile_io(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "not-created"
            with patch("stage_native_gameplay.validate_source_state", return_value={"changes": [" M app.cpp"]}):
                with self.assertRaisesRegex(ValueError, "committed-clean"):
                    stage(output, Path("missing-profile"), "0" * 64, "unused", "0" * 64,
                      {"explicit": "not a clean-state bypass"})
            self.assertFalse(output.exists())

    @unittest.skipUnless(os.environ.get("CELESTE_MATERIAL_VALIDATOR"), "requires the exact-source material validator")
    def test_actual_stage_writes_complete_pins_and_inventory_from_synthetic_inputs(self):
        from stage_native_room import checksum
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".audit").mkdir()
            profile = self.profile(root)
            output, manifest = self.stage_synthetic(profile, self.real_binding(root))
            self.assertEqual(manifest["gameplay_production"], "automatic-transition")
            self.assertEqual(set(manifest["files"]), set(METADATA) | {"page7.rgba"})
            self.assertEqual((output / "gameplay_pins.hpp").read_text(), gameplay_pins_text(manifest))
            self.assertEqual((output / "gameplay_files.cmake").read_text(), gameplay_inventory_text(manifest))
            for name, metadata in manifest["files"].items():
                data = (output / "assets/native-room" / name).read_bytes()
                self.assertEqual(len(data), metadata["bytes"])
                self.assertEqual(checksum(data), metadata["fnv1a32"])
