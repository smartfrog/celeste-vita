from pathlib import Path
import json
import hashlib
import sys
import tempfile
import unittest
import io
import subprocess
from contextlib import redirect_stdout
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from compare_dash_traces import fixture_operations, validate_trace
from check_native_oracle import verify_extraction
import prepare_dash_oracle


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


class HelperPreparationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir="/tmp/opencode")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / ".audit/ilspy"
        self.private = self.root / ".audit/native-oracle"
        self.output = self.root / ".audit/native-dash/closure"
        self.calc = self.root / ".audit/native-wall-jumps/closure/Monocle.Calc.cs"
        self.receipt = self.calc.with_suffix(".preparation.json")
        names = ("Monocle.Engine", "Monocle.MInput", "Celeste.Celeste", "Monocle.Calc")
        self.bodies = {name: ("synthetic pinned " + name + "\n").encode() for name in names}
        self.hashes = {name+".cs": hashlib.sha256(body).hexdigest() for name,body in self.bodies.items()}
        executable = b"synthetic executable"
        self.input_hash = hashlib.sha256(executable).hexdigest()
        for path,data in ((self.private / "tools/dotnet-8.0.425/dotnet",b""),
                          (self.source / "tools/ilspycmd-9.1.0.7988/tools/net8.0/any/ilspycmd.dll",b""),
                          (self.source / "inputs/Celeste.exe",executable)):
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(data)
        self.output.mkdir(parents=True)
        for name in names[:-1]:
            (self.output / (name+".cs")).write_bytes(self.bodies[name])
            (self.output / (name+".stderr")).write_bytes(b"historical stderr\n")
        (self.output / "preparation.json").write_bytes(b'[{"type":"historical Dash receipt"}]\n')
        self.historical = self.snapshot()

    def snapshot(self):
        return {str(path.relative_to(self.root)):path.read_bytes() for path in self.root.rglob("*") if path.is_file()}

    def prepare(self, extracted=None, failure=None):
        def decompile(command, **kwargs):
            kwargs["stdout"].write(self.bodies["Monocle.Calc"] if extracted is None else extracted)
            if failure is not None:
                kwargs["stderr"].write(b"synthetic extraction failure\n")
                raise failure

        with patch.multiple(prepare_dash_oracle,ROOT=self.root,PRIVATE=self.private,INPUT_SHA=self.input_hash,SOURCE_HASHES=self.hashes), \
             patch.object(prepare_dash_oracle,"oracle_environment",return_value={"SYNTHETIC":"1"}), \
             patch.object(prepare_dash_oracle.subprocess,"run",side_effect=decompile) as run, \
             redirect_stdout(io.StringIO()):
            prepare_dash_oracle.main()
        return run

    def assert_historical_preserved(self):
        current = self.snapshot()
        for name,body in self.historical.items():
            self.assertEqual(current[name],body,name)

    def test_new_calc_helper_preserves_historical_dash_receipt(self):
        run = self.prepare()
        run.assert_called_once()
        self.assert_historical_preserved()
        receipt = json.loads(self.receipt.read_text())
        self.assertEqual(receipt["type"],"Monocle.Calc")
        self.assertEqual(receipt["source_sha256"],self.hashes["Monocle.Calc.cs"])
        self.assertEqual(receipt["input_sha256"],self.input_hash)
        self.assertEqual(receipt["command"],run.call_args.args[0])
        self.assertIn("--disable-updatecheck",receipt["command"])

    def test_cached_rerun_preserves_all_bytes_without_extraction(self):
        self.prepare()
        before = self.snapshot()
        self.prepare().assert_not_called()
        self.assertEqual(self.snapshot(),before)

    def test_changed_extracted_hash_fails_without_success_receipt(self):
        with self.assertRaisesRegex(ValueError,"Changed private source preserved"):
            self.prepare(extracted=b"changed helper\n")
        self.assert_historical_preserved()
        self.assertEqual(self.calc.read_bytes(),b"changed helper\n")
        self.assertFalse(self.receipt.exists())

    def test_changed_cached_hash_fails_without_rewriting_receipt(self):
        self.prepare()
        receipt = self.receipt.read_bytes()
        self.calc.write_bytes(b"changed cached helper\n")
        with self.assertRaisesRegex(ValueError,"Changed private source preserved"):
            self.prepare(failure=AssertionError("Cached source must not be re-extracted"))
        self.assert_historical_preserved()
        self.assertEqual(self.receipt.read_bytes(),receipt)

    def test_failed_extraction_propagates_without_success_receipt(self):
        failure = subprocess.CalledProcessError(7,["synthetic-ilspy"])
        with self.assertRaises(subprocess.CalledProcessError) as raised:
            self.prepare(failure=failure)
        self.assertIs(raised.exception,failure)
        self.assert_historical_preserved()
        self.assertEqual(self.calc.with_suffix(".stderr").read_bytes(),b"synthetic extraction failure\n")
        self.assertFalse(self.receipt.exists())
