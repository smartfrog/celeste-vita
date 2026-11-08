from pathlib import Path
import json
import hashlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from compare_dash_traces import fixture_operations, validate_trace
from check_native_oracle import verify_extraction


class DashValidationTests(unittest.TestCase):
    def fixture(self, text):
        temporary = tempfile.TemporaryDirectory(dir="/tmp/opencode")
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "dash.fixtures"
        path.write_text(text)
        return path

    def test_freeze_has_only_input_and_freeze_phases(self):
        path = self.fixture("case freeze 0 0 0 0 -100 100\ntick .06 0 0 0 0 0 0 0 0 0 0 0 0 0 => freeze\n")
        self.assertEqual([row[2] for row in fixture_operations(path)], ["input", "freeze"])

    def test_frozen_tick_cannot_claim_coroutine_update(self):
        path = self.fixture("case freeze 0 0 0 0 -100 100\ntick .06 0 0 0 0 0 0 0 0 0 0 0 0 0 => freeze dash\n")
        with self.assertRaises(ValueError):
            fixture_operations(path)

    def test_missing_phase_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_trace([], [("case", "1", "input", "-1", "00000000")], "test")

    def test_negative_delta_is_rejected(self):
        path = self.fixture("case invalid 0 0 0 0 -100 100\ntick -.01 0 0 0 0 0 0 0 0 0 0 0 0 0\n")
        with self.assertRaises(ValueError):
            fixture_operations(path)

    def test_repository_fixtures_declare_dash_and_collision_phases(self):
        phases = {row[2] for row in fixture_operations(Path(__file__).with_name("dash.fixtures"))}
        self.assertTrue({"input", "freeze", "dash_update", "collision_h", "collision_v", "removed", "rejected"} <= phases)


class ExtractionIdentityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir="/tmp/opencode")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = b"unchanged body\n"
        (self.root / "source.cs").write_bytes(self.source)
        (self.root / "Extracted.cs").write_bytes(self.source)
        digest = hashlib.sha256(self.source).hexdigest()
        manifest = {"extracted_sha256": digest, "extractions": [{"file": "source.cs", "source_path": "source.cs",
                    "source_sha256": digest, "lines_inclusive": [[1, 1]], "blocks_sha256": [digest]}]}
        (self.root / "source-manifest.json").write_text(json.dumps(manifest))

    def test_unchanged_block_identity(self):
        with patch("check_native_oracle.ROOT", self.root):
            self.assertEqual(verify_extraction(self.root)["blocks"], 1)

    def test_changed_generated_body_is_rejected(self):
        (self.root / "Extracted.cs").write_text("rewritten body\n")
        with patch("check_native_oracle.ROOT", self.root), self.assertRaises(ValueError):
            verify_extraction(self.root)

    def test_changed_source_is_rejected(self):
        (self.root / "source.cs").write_text("changed source\n")
        with patch("check_native_oracle.ROOT", self.root), self.assertRaises(ValueError):
            verify_extraction(self.root)
