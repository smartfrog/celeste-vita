import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from native_room_revision import canonical_digest, file_identity
from prepare_full_bake_transition_profile import (
    KIND, DRIVER_ID, MASK_ID, REFERENCES, validate_profile, validate_terrain_metadata,
    verify_pinned, verify_references, verify_source, validate_collision_grid, check_terrain,
)
from run_room_transition_probe import execution_namespace
from compare_room_transition_contract import validate


class FullBakeTransitionProfileTests(unittest.TestCase):
    def profile(self):
        record = {"schema": 1, "kind": KIND, "terrain": {
            "driver": DRIVER_ID, "mask": MASK_ID,
            "origin": [-64, -3272], "dimensions": [541, 440]},
            "inputs": {}, "generated": {}, "compiled_sources": [], "compiled_artifacts": {}}
        record["binding"] = canonical_digest(record)
        return record

    def test_full_bake_profile_has_a_distinct_versioned_identity(self):
        validate_profile(self.profile())

    def test_old_profile_keeps_its_original_output_namespace(self):
        self.assertEqual(execution_namespace({}), ROOT / ".audit/native-room-transition/source-contract-01")

    def test_unknown_profile_cannot_select_an_output_namespace(self):
        with self.assertRaisesRegex(ValueError, "profile kind"):
            execution_namespace({"kind": "unrecognized"})

    def test_full_bake_namespace_requires_a_verified_profile_path(self):
        with self.assertRaisesRegex(ValueError, "profile path"):
            execution_namespace(self.profile())

    def test_old_two_room_profile_cannot_be_used_as_full_bake(self):
        with self.assertRaisesRegex(ValueError, "profile kind"):
            validate_profile({"schema": 1, "status": "experiment-not-transition-acceptance"})

    def test_provenance_corruption_is_rejected(self):
        record = self.profile()
        record["inputs"]["unbound"] = {"bytes": 0, "sha256": "0" * 64}
        with self.assertRaisesRegex(ValueError, "binding"):
            validate_profile(record)

    def test_wrong_metadata_bounds_are_rejected_even_with_a_new_binding(self):
        record = self.profile()
        record["terrain"]["origin"] = [-64, -248]
        del record["binding"]
        record["binding"] = canonical_digest(record)
        with self.assertRaisesRegex(ValueError, "terrain"):
            validate_profile(record)

    def test_old_mask_identity_is_rejected_even_with_a_new_binding(self):
        record = self.profile()
        record["terrain"]["mask"] = {"bytes": 5480, "sha256": "0" * 64}
        del record["binding"]
        record["binding"] = canonical_digest(record)
        with self.assertRaisesRegex(ValueError, "terrain"):
            validate_profile(record)

    def test_two_room_driver_cannot_claim_full_terrain(self):
        with self.assertRaisesRegex(ValueError, "38 rooms and 22 fillers"):
            validate_terrain_metadata({"levels": [{}, {}], "filler": []},
                                      (-64, -3272, 541, 440, ""), {})

    def test_changed_driver_bytes_are_rejected(self):
        with self.scratch() as scratch:
            path = Path(scratch) / "driver.json"
            path.write_text("{}")
            with self.assertRaisesRegex(ValueError, "driver"):
                verify_pinned(path, DRIVER_ID, "driver")

    def test_changed_mask_bytes_are_rejected(self):
        with self.scratch() as scratch:
            path = Path(scratch) / "global.mask"
            path.write_text("not the shipped mask")
            with self.assertRaisesRegex(ValueError, "mask"):
                verify_pinned(path, MASK_ID, "mask")

    def test_changed_reference_assembly_is_rejected(self):
        with self.scratch() as scratch:
            assembly = Path(scratch) / "Celeste.exe"
            assembly.write_bytes(b"wrong assembly")
            result = Path(scratch) / "result.json"
            result.write_text(json.dumps({"inputs": {"Celeste.exe": {
                "path": str(assembly), **file_identity(assembly)}}}))
            with self.assertRaisesRegex(ValueError, "reference assembly"):
                verify_references(result)

    def test_reference_assembly_bytes_must_match_the_claimed_pin(self):
        with self.scratch() as scratch:
            assembly = Path(scratch) / "Celeste.exe"
            assembly.write_bytes(b"wrong assembly")
            result = Path(scratch) / "result.json"
            result.write_text(json.dumps({"inputs": {"Celeste.exe": {
                "path": str(assembly), **REFERENCES["Celeste.exe"]}}}))
            with self.assertRaisesRegex(ValueError, "reference assembly"):
                verify_references(result)

    def test_changed_reviewed_source_binding_is_rejected(self):
        with self.scratch() as scratch:
            receipt = Path(scratch) / "immutable-source-recheck.json"
            receipt.write_text("{}")
            with self.assertRaisesRegex(ValueError, "reviewed SOURCE binding"):
                verify_source(Path(scratch), receipt)

    def test_source_collision_cell_mismatch_is_rejected(self):
        observation = {"event": "full-bake-terrain", "origin": [0, 0],
                       "dimensions": [2, 2], "cells": "1110", "seed": 553}
        with self.assertRaisesRegex(ValueError, "collision grid"):
            validate_collision_grid(observation, (0, 0, 2, 2, "1010"))

    def test_exact_source_collision_grid_is_accepted(self):
        observation = {"event": "full-bake-terrain", "origin": [0, 0],
                       "dimensions": [2, 2], "cells": "1010", "seed": 553}
        validate_collision_grid(observation, (0, 0, 2, 2, "1010"))

    def scratch(self):
        directory = ROOT / ".audit/native-room-transition-vita/full-bake-contract-01/unit-scratch"
        directory.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=directory)


class SharedRunnerExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        profile = os.environ.get("CELESTE_FULL_BAKE_PROFILE")
        if profile is None:
            raise unittest.SkipTest("Explicit private full-bake profile required for real shared-runner execution")
        cls.profile = Path(profile).resolve()
        cls.content = Path(os.environ["CELESTE_FULL_BAKE_CONTENT"]).resolve()
        cls.phase = os.environ.get("CELESTE_FULL_BAKE_TEST_PHASE", "unit")
        if cls.phase not in ("red", "green", "unit"):
            raise ValueError("Unknown shared-runner test evidence phase")
        cls.record = json.loads((cls.profile / "transition-profile.json").read_text())
        cls.sdk = next(Path(path) for path in cls.record["inputs"] if Path(path).name == "dotnet")
        cls.evidence = ROOT / ".audit/native-room-transition-vita/full-bake-contract-01/corrective-02"
        (cls.evidence / "entry-scratch").mkdir(parents=True, exist_ok=True)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=self.evidence / "entry-scratch")
        self.addCleanup(self.temporary.cleanup)
        self.scratch = Path(self.temporary.name)

    def candidate(self, field, value):
        record = json.loads(json.dumps(self.record))
        record[field] = value
        if field != "binding":
            record["binding"] = canonical_digest({key: item for key, item in record.items() if key != "binding"})
        profile = self.scratch / "candidate"
        profile.mkdir()
        (profile / "transition-profile.json").write_text(json.dumps(record))
        for group in ("generated", "compiled_artifacts"):
            for name in record[group]:
                (profile / name).symlink_to(self.profile / name)
        return profile

    def execute(self, profile, scenario):
        output = self.scratch / "execution"
        command = [sys.executable, "-B", str(ROOT / "scripts/run_room_transition_probe.py"),
                   "--profile", str(profile), "--sdk", str(self.sdk), "--content", str(self.content),
                   "--controls", str(ROOT / "tests/native/room-transition.inputs.json"), "--output", str(output)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        trace = output / "trace.jsonl"
        receipt = {"command": command, "returncode": result.returncode, "stdout": result.stdout,
                   "stderr": result.stderr, "output_created": output.exists(),
                   "trace": file_identity(trace) if trace.is_file() else None}
        evidence = Path(tempfile.mkdtemp(prefix=self.phase + "-" + scenario + "-", dir=self.evidence))
        with (evidence / "receipt.json").open("x") as stream:
            stream.write(json.dumps(receipt, indent=2) + "\n")
        return result, output

    def assert_rejected(self, profile, scenario, error):
        result, output = self.execute(profile, scenario)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(error, result.stderr)
        self.assertFalse(output.exists(), "Shared runner created output before rejecting the profile")

    def test_zeroed_binding_is_rejected_before_output_or_oracle_launch(self):
        self.assert_rejected(self.candidate("binding", "0" * 64), "zero-binding", "binding")

    def test_repeated_invocations_retain_distinct_evidence(self):
        prefix = self.phase + "-repeat-zero-binding-"
        before = {path for path in self.evidence.iterdir() if path.is_dir() and path.name.startswith(prefix)}
        profile = self.candidate("binding", "0" * 64)
        self.assert_rejected(profile, "repeat-zero-binding", "binding")
        self.assert_rejected(profile, "repeat-zero-binding", "binding")
        after = {path for path in self.evidence.iterdir() if path.is_dir() and path.name.startswith(prefix)}
        self.assertEqual(len(after - before), 2)
        self.assertTrue(all((path / "receipt.json").is_file() for path in after - before))

    def test_wrong_schema_is_rejected_before_output_or_oracle_launch(self):
        self.assert_rejected(self.candidate("schema", 2), "wrong-schema", "profile kind/version")

    def test_wrong_terrain_is_rejected_before_output_or_oracle_launch(self):
        terrain = dict(self.record["terrain"], origin=[-64, -248])
        self.assert_rejected(self.candidate("terrain", terrain), "wrong-terrain", "terrain identity")

    def test_wrong_profile_path_is_rejected_before_output_or_oracle_launch(self):
        self.assert_rejected(self.profile / "missing", "wrong-path", "FileNotFoundError")

    def test_valid_full_bake_profile_executes_through_shared_runner(self):
        result, output = self.execute(self.profile, "valid")
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = [json.loads(line) for line in (output / "trace.jsonl").read_text().splitlines()]
        mask = next(Path(path) for path, identity in self.record["inputs"].items() if identity == MASK_ID)
        self.assertEqual(check_terrain(rows, mask)["cells_compared"], 238040)
        self.assertEqual(validate(rows)["frames"], 514)
