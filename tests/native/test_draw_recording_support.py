import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from prepare_draw_recording_support import (
    DEFAULT_DISCOVERY,
    DEFAULT_PINS,
    DISCOVERY_PINS,
    FRAMEWORK_PINS,
    REQUIRED_CHECKS,
    SHEET_SPANS,
    SUPPORT,
    compose,
    prepare,
)
from prepare_decals_oracle import (
    DISCOVERY_PINS as DECALS_DISCOVERY_PINS,
    FRAMEWORK_PINS as DECALS_FRAMEWORK_PINS,
)
from native_oracle_sdk import sdk_path


def _scratch_parent():
    parent = ROOT / ".audit/native-room-transition-vita/update-draw-contract-01"
    parent.mkdir(parents=True, exist_ok=True)
    return str(parent)


class DrawRecordingSupportPinTests(unittest.TestCase):
    def test_framework_pins_reuse_the_pinned_decompile_sources(self):
        self.assertEqual(FRAMEWORK_PINS, DECALS_FRAMEWORK_PINS)
        self.assertEqual(FRAMEWORK_PINS["System.Random.cs"][:16], "4d50e548631225ad")
        self.assertEqual(FRAMEWORK_PINS["Microsoft.Xna.Framework.Graphics.SpriteBatch.cs"][:16], "00446c9efcf427a0")

    def test_discovery_pins_bind_the_monocle_atlas_surface(self):
        self.assertEqual(DISCOVERY_PINS, {name: DECALS_DISCOVERY_PINS[name] for name in DISCOVERY_PINS})
        self.assertEqual(DISCOVERY_PINS["Monocle.MTexture.cs"][:16], "45847f23970911b0")
        self.assertEqual(DISCOVERY_PINS["Monocle.Atlas.cs"][:16], "95deee77a169baa0")

    def test_support_is_exactly_the_recorder_runner_and_geometry(self):
        self.assertEqual(SUPPORT, (
            "tests/native/oracle/transition/DrawRecording.cs",
            "tests/native/oracle/transition/DrawRecordingRunner.cs",
            "tests/native/oracle/presentation/Geometry.cs",
        ))

    def test_extraction_spans_reuse_the_established_pinned_ranges(self):
        self.assertEqual(SHEET_SPANS["Monocle.Atlas.cs"], [(24, 40)])
        self.assertEqual(SHEET_SPANS["Monocle.MTexture.cs"], [(7, 660)])
        self.assertEqual(SHEET_SPANS["Microsoft.Xna.Framework.Graphics.SpriteBatch.cs"], [(128, 130), (335, 361), (744, 784)])

    def test_strict_draw_checks_are_required_for_a_verified_recorder(self):
        self.assertEqual(REQUIRED_CHECKS, (
            "sheet-identity-and-real-dimensions",
            "unknown-sheet-fails-loud",
            "conflicting-sheet-registration-fails",
            "scalar-vector-draw-fidelity",
            "real-dimensions-drive-uv",
            "ordered-batch-state-recording",
            "draw-requires-open-batch",
            "non-deferred-sort-rejected-state-unchanged",
            "effect-submission-rejected-state-unchanged",
            "invalid-sort-enum-rejected",
            "no-draw-omitted",
        ))

    def test_compose_refuses_a_changed_pinned_source(self):
        with tempfile.TemporaryDirectory(dir=_scratch_parent()) as scratch:
            output = Path(scratch) / "support"
            changed = Path(scratch) / "changed"
            changed.mkdir()
            for name in FRAMEWORK_PINS:
                shutil.copyfile(DEFAULT_PINS / name, changed / name)
            (changed / "System.Random.cs").write_text("// tampered\n")
            with self.assertRaisesRegex(ValueError, "Pinned source identity changed"):
                compose(DEFAULT_DISCOVERY, changed, output)

    def test_compose_refuses_existing_output(self):
        with tempfile.TemporaryDirectory(dir=_scratch_parent()) as scratch:
            output = Path(scratch) / "support"
            output.mkdir()
            with self.assertRaisesRegex(ValueError, "fresh"):
                compose(DEFAULT_DISCOVERY, DEFAULT_PINS, output)


class DrawRecordingSupportExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from prepare_draw_recording_support import default_sdk
        cls.sdk = default_sdk()
        if not (DEFAULT_DISCOVERY / "Monocle.MTexture.cs").exists() or not (DEFAULT_PINS / "System.Random.cs").exists():
            raise unittest.SkipTest("Pinned private decompile sources are unavailable")
        cls.scratch = tempfile.mkdtemp(prefix="recorder-support-test-", dir=_scratch_parent())
        cls.output = Path(cls.scratch) / "support"
        result = prepare(DEFAULT_DISCOVERY, DEFAULT_PINS, cls.output, cls.sdk)
        cls.result = result

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "scratch"):
            shutil.rmtree(cls.scratch, ignore_errors=True)

    def test_recorder_self_check_passes_every_strict_draw_check(self):
        self.assertEqual(self.result["status"], "draw-recording-support-verified")
        self.assertEqual(self.result["checks_passed"], len(REQUIRED_CHECKS))
        self.assertEqual(self.result["failures"], [])

    def test_scalar_draw_records_identical_stream_and_geometry_to_vector(self):
        check = self._check("scalar-vector-draw-fidelity")
        self.assertTrue(check["identical_records"])
        self.assertTrue(check["identical_geometry_bits"])
        self.assertEqual(check["scale"], [2.0, 2.0])

    def test_atlas_metadata_retains_sheet_identity_and_real_dimensions(self):
        check = self._check("sheet-identity-and-real-dimensions")
        self.assertEqual(check["texture_name"], "Gameplay0")
        self.assertEqual(check["sheet_dimensions"], [4096, 4096])
        self.assertNotEqual(check["texture_name"], check["subtexture"])

    def test_real_sheet_dimensions_drive_recorded_uv_not_a_constant(self):
        check = self._check("real-dimensions-drive-uv")
        self.assertNotEqual(check["uv_4096"], check["uv_2048"])
        self.assertEqual(check["uv_4096"], [16 / 4096, 16 / 4096])
        self.assertEqual(check["uv_2048"], [16 / 2048, 16 / 2048])

    def test_batch_state_recording_is_ordered_with_matrices(self):
        check = self._check("ordered-batch-state-recording")
        self.assertEqual(check["operations"], ["begin", "begin"])
        self.assertEqual(check["sort_modes"], ["Deferred", "Deferred"])
        self.assertEqual(len(check["matrices"]), 2)
        self.assertEqual(check["draw_ranges"], [[0, 2], [2, 3]])
        self.assertEqual(check["unmatched_end_rejected"], True)

    def test_draw_outside_open_batch_fails_loud(self):
        check = self._check("draw-requires-open-batch")
        self.assertTrue(check["draw_before_begin_rejected"])
        self.assertTrue(check["draw_after_end_rejected"])
        self.assertTrue(check["nested_begin_rejected"])

    def test_unknown_sheet_metadata_fails_loud(self):
        check = self._check("unknown-sheet-fails-loud")
        self.assertEqual(check["sheet"], "Unknown0")
        self.assertIn("Unregistered atlas sheet", check["error"])

    def test_non_deferred_sort_is_rejected_without_touching_state(self):
        check = self._check("non-deferred-sort-rejected-state-unchanged")
        self.assertIn("Excluded SpriteBatch sort mode: Texture", check["error"])
        self.assertEqual(check["states_after_rejection"], 0)
        self.assertEqual(check["states_after_valid_submission"], 1)
        self.assertEqual(check["valid_submission_draw_range"], [0, 1])

    def test_non_null_effect_submission_is_rejected_without_touching_state(self):
        check = self._check("effect-submission-rejected-state-unchanged")
        self.assertIn("Excluded SpriteBatch effect submission", check["error"])
        self.assertEqual(check["states_unchanged"], 1)
        self.assertEqual(check["draw_range_after_rejection"], [0, 1])

    def test_invalid_sort_enum_is_rejected(self):
        check = self._check("invalid-sort-enum-rejected")
        self.assertIn("Unknown SpriteSortMode: 99", check["error"])

    def test_scope_delimits_unsupported_owner_and_scissor_evidence(self):
        scope = self.result["oracle"]["scope"]
        self.assertEqual(scope["owner_attribution"], "unsupported-not-observed; per-draw owner is not recorded by this recorder")
        self.assertEqual(scope["scissor_state"], "unsupported-not-observed; recorded Clip is the atlas source rectangle, not a GPU scissor rect")
        self.assertEqual(scope["camera_source"], "recorded matrix is the exact effective transform passed to Begin, never a CPU camera or Level.Zoom assumption")
        self.assertTrue(scope["sorting"].startswith("deferred-submission-order-only"))
        self.assertTrue(scope["parity"].startswith("not full source parity"))

    def test_every_recorded_draw_has_matching_original_geometry(self):
        check = self._check("no-draw-omitted")
        self.assertEqual(check["recorded_calls"], check["geometry_calls"])

    def test_output_stays_inside_the_assigned_private_draw_namespace(self):
        self.assertTrue(str(self.output).startswith(
            str(ROOT / ".audit/native-room-transition-vita/update-draw-contract-01")))

    def _check(self, name):
        for check in self.result["oracle"]["checks"]:
            if check["name"] == name:
                return check
        raise AssertionError("Missing recorder self-check: " + name)


if __name__ == "__main__":
    unittest.main()
