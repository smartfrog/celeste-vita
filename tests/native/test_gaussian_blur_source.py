import json
import os
from pathlib import Path
import struct
import sys
import unittest
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))


def bits(value):
    return struct.unpack("<i", struct.pack("<f", value))[0]


class GaussianProfileTests(unittest.TestCase):
    def test_separate_profile_kind_accepts_only_its_bound_claim(self):
        from prepare_gaussian_blur_source import KIND, CLAIM, validate_profile
        from native_room_revision import canonical_digest
        record = {"schema": 1, "kind": KIND, "claim": CLAIM}
        record["binding"] = canonical_digest(record)
        validate_profile(record)

    def test_old_rendergraph_kind_cannot_claim_gaussian_execution(self):
        from prepare_gaussian_blur_source import validate_profile
        with self.assertRaisesRegex(ValueError, "kind/version"):
            validate_profile({"schema": 1, "kind": "native-room-transition-rendergraph-source-slice-v1"})

    def test_boolean_is_not_a_profile_version(self):
        from prepare_gaussian_blur_source import KIND, validate_profile
        with self.assertRaisesRegex(ValueError, "kind/version"):
            validate_profile({"schema": True, "kind": KIND})

    def test_rebinding_does_not_expand_scope(self):
        from prepare_gaussian_blur_source import KIND, validate_profile
        from native_room_revision import canonical_digest
        record = {"schema": 1, "kind": KIND, "claim": "full Lighting.BeforeRender"}
        record["binding"] = canonical_digest(record)
        with self.assertRaisesRegex(ValueError, "scope"):
            validate_profile(record)

    def test_bad_binding_is_rejected_before_output(self):
        from prepare_gaussian_blur_source import AUDIT, KIND, CLAIM, run
        AUDIT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=AUDIT) as directory:
            profile = Path(directory) / "profile"
            profile.mkdir()
            (profile / "transition-profile.json").write_text(json.dumps({"schema": 1, "kind": KIND, "claim": CLAIM, "binding": "0" * 64}))
            output = Path(directory) / "execution"
            with self.assertRaisesRegex(ValueError, "binding"):
                run(profile, output)
            self.assertFalse(output.exists())

    def test_missing_artifact_identities_are_rejected_before_execution(self):
        from prepare_gaussian_blur_source import AUDIT, KIND, CLAIM, run
        from native_room_revision import canonical_digest
        AUDIT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=AUDIT) as directory:
            profile = Path(directory) / "profile"
            profile.mkdir()
            record = {"schema": 1, "kind": KIND, "claim": CLAIM, "profile_directory": str(profile)}
            record["binding"] = canonical_digest(record)
            (profile / "transition-profile.json").write_text(json.dumps(record))
            output = Path(directory) / "execution"
            with self.assertRaisesRegex(ValueError, "artifact"):
                run(profile, output)
            self.assertFalse(output.exists())


class GaussianEffectTests(unittest.TestCase):
    def test_verified_gaussian_has_three_original_pixel_programs(self):
        from rendergraph_effect_contract import gaussian_effect
        effect = gaussian_effect()
        self.assertEqual(set(effect["techniques"]), {"GaussianBlur3", "GaussianBlur5", "GaussianBlur9"})
        self.assertEqual((effect["parameters"]["fade"]["type"], effect["parameters"]["fade"]["class"],
                          effect["parameters"]["fade"]["columns"]), (3, 0, 1))
        self.assertEqual(effect["parameters"]["pixel"]["columns"], 2)
        for passes in effect["techniques"].values():
            self.assertEqual(len(passes), 1)
            self.assertEqual([p["stage"] for p in passes[0]["programs"]], ["pixel"])
            self.assertEqual(passes[0]["programs"][0]["constants"]["textSampler"]["register"], 0)

    def test_unverified_gaussian_resource_is_rejected_before_parsing(self):
        from rendergraph_effect_contract import parse_effect
        with self.assertRaisesRegex(ValueError, "resource identity"):
            parse_effect("GaussianBlur", b"unverified")


class ExecutedGaussianTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from prepare_gaussian_blur_source import run
        profile = os.environ.get("GAUSSIAN_BLUR_PROFILE")
        output = os.environ.get("GAUSSIAN_BLUR_OUTPUT")
        if not profile or not output:
            raise unittest.SkipTest("Set GAUSSIAN_BLUR_PROFILE and fresh GAUSSIAN_BLUR_OUTPUT")
        run(Path(profile).resolve(), Path(output).resolve())
        cls.rows = [json.loads(line) for line in (Path(output) / "trace.jsonl").read_text().splitlines()]

    def operation(self, name, owner=None):
        return [r["data"] for r in self.rows if r["operation"] == name and (owner is None or r["owner"] == owner)]

    def test_default_original_call_executes_two_nine_sample_passes_and_returns_output(self):
        flush = self.operation("batch-flush", "original GaussianBlur.Blur default")
        self.assertEqual(len(flush), 2)
        self.assertEqual([f["effect"]["technique"] for f in flush], ["GaussianBlur9"] * 2)
        result = self.operation("blur-return", "original GaussianBlur.Blur default")[0]
        self.assertEqual(result["returned"], flush[1]["context"]["target"])
        self.assertEqual(flush[1]["texture"], flush[0]["context"]["target"])

    def test_samples_clear_and_nondefault_parameters_are_observed_at_each_flush(self):
        for sample in (3, 5, 9):
            for clear in (True, False):
                with self.subTest(sample=sample, clear=clear):
                    owner = f"original GaussianBlur.Blur samples={sample} clear={str(clear).lower()}"
                    flush = self.operation("batch-flush", owner)
                    self.assertEqual(len(flush), 2)
                    self.assertEqual(len(self.operation("clear", owner)), 2 if clear else 0)
                    for index, f in enumerate(flush):
                        self.assertEqual(f["effect"]["technique"], f"GaussianBlur{sample}")
                        self.assertEqual(f["effect"]["parameters"]["fade"]["value"], [bits(0.375)])
                        self.assertEqual(f["effect"]["parameters"]["pixel"]["value"],
                                         [bits(1.75 / 320), 0] if index == 0 else [0, bits(1.75 / 180)])
                        self.assertEqual(f["rgba"], 0xffffffff)
                        self.assertEqual(f["destinationRectangle"], [0, 0, 320, 180])

    def test_resolved_default_depth_and_all_other_states_are_captured(self):
        for f in self.operation("batch-flush"):
            self.assertTrue(f["states"]["depthStencil"]["DepthBufferEnable"])
            self.assertTrue(f["states"]["depthStencil"]["DepthBufferWriteEnable"])
            self.assertEqual(f["states"]["depthStencil"]["DepthBufferFunction"], "LessEqual")
            self.assertEqual(f["states"]["sampler"]["Filter"], "Point")
            self.assertEqual(f["states"]["rasterizer"]["CullMode"], "None")
            self.assertEqual(f["states"]["blend"]["ColorSourceBlend"], "One")
            self.assertEqual(f["states"]["blend"]["ColorDestinationBlend"], "InverseSourceAlpha")
            self.assertIn("observer-owned", f["boundary"])

    def test_apply_and_flush_snapshots_match_with_input_and_target_context(self):
        applies = self.operation("effect-apply")
        flushes = self.operation("batch-flush")
        self.assertEqual(len(applies), len(flushes))
        for apply, flush in zip(applies, flushes):
            self.assertEqual(apply["effect"], flush["effect"])
            self.assertEqual(apply["states"], flush["states"])
            self.assertEqual(apply["textureSlot0"], flush["texture"])
            self.assertEqual(apply["context"], flush["context"])
            self.assertEqual(flush["context"]["viewport"], flush["destinationRectangle"])
            self.assertEqual(flush["context"]["scissor"], flush["destinationRectangle"])

    def test_asymmetric_original_targets_use_temp_width_then_output_height(self):
        flush = self.operation("batch-flush", "original GaussianBlur.Blur asymmetric dimensions")
        self.assertEqual([f["dimensions"] for f in flush], [[320, 180], [1024, 1024]])
        self.assertEqual([f["destinationRectangle"] for f in flush], [[0, 0, 1024, 1024], [0, 0, 384, 244]])
        reciprocal = struct.unpack("<f", struct.pack("<f", 1 / 244))[0]
        self.assertEqual([f["effect"]["parameters"]["pixel"]["value"] for f in flush],
                         [[bits(2.25 / 1024), 0], [0, bits(reciprocal * 2.25)]])

    def test_pass_order_keeps_clear_enqueue_apply_and_flush_before_next_target(self):
        rows = [r for r in self.rows if r.get("owner") == "original GaussianBlur.Blur default"]
        self.assertEqual([r["operation"] for r in rows],
                         ["set-render-target", "clear", "batch-begin", "batch-enqueue", "effect-apply", "batch-flush", "batch-end"] * 2 + ["blur-return"])
        self.assertTrue(all(r["data"]["rgba"] == 0 for r in rows if r["operation"] == "clear"))

    def test_allocations_are_unique_and_every_reference_is_alive_until_original_unload(self):
        live = {}
        ids = set()

        def references(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in ("target", "texture", "textureSlot0", "returned") and item not in (None, "declared-backbuffer"):
                        self.assertIn(item, live)
                        if key == "texture" and "dimensions" in value:
                            self.assertEqual(value["dimensions"], live[item])
                    else:
                        references(item)
            elif isinstance(value, list):
                for item in value:
                    references(item)

        for row in self.rows:
            data = row.get("data", {})
            if row["operation"] == "create-render-target":
                self.assertNotIn(data["Id"], ids)
                ids.add(data["Id"])
                live[data["Id"]] = [data["Width"], data["Height"]]
            elif row["operation"] == "dispose-render-target":
                self.assertIn(data["Id"], live)
                del live[data["Id"]]
            else:
                references(data)
        self.assertEqual(live, {})
        self.assertGreater(len(ids), 12)

    def test_unsupported_paths_are_explicit_and_do_not_mutate_at_rejected_operation(self):
        summary = self.operation("gaussian-summary")[0]
        for name in ("horizontal default shader", "vertical default shader", "unknown shader", "unknown technique", "unknown parameter", "wrong parameter type", "target alias", "unknown target format", "unsupported batch operation"):
            self.assertIn(name + " rejected before trace mutation", summary["verifiedChecks"])

    def test_nonfinite_original_parameter_bits_are_retained(self):
        flush = self.operation("batch-flush", "original GaussianBlur.Blur nonfinite")
        self.assertEqual(len(flush), 2)
        self.assertEqual(flush[0]["effect"]["parameters"]["fade"]["value"], [-4194303])
        self.assertEqual(flush[0]["effect"]["parameters"]["pixel"]["value"][0], 2139095040)

    def test_exported_null_effect_branch_has_no_api_rows(self):
        self.assertEqual([row for row in self.rows if row.get("owner") == "original GaussianBlur.Blur null effect branch"], [])

    def test_exported_final_target_unbind_is_observer_fixture_owned(self):
        unbinds = [row for row in self.rows if row["operation"] == "set-render-target"
                   and row["data"]["target"] == "declared-backbuffer"]
        self.assertEqual(len(unbinds), 1)
        self.assertEqual(unbinds[0]["owner"], "observer fixture final cleanup")

    def test_exported_unsupported_direction_cleanup_is_not_an_original_api_call(self):
        for direction in ("horizontal", "vertical"):
            with self.subTest(direction=direction):
                prefix = [row for row in self.rows if row.get("owner") == f"original GaussianBlur.Blur {direction} unsupported prefix"]
                self.assertEqual(prefix[-1]["operation"], "batch-begin")
        cleanup = self.operation("batch-end", "observer fixture unsupported direction cleanup")
        self.assertEqual(len(cleanup), 2)
        self.assertEqual([row["commands"] for row in cleanup], [0, 0])

    def test_exported_original_unload_excludes_foreign_fixture_lifetime(self):
        original = [row for row in self.rows if row.get("owner") == "original GameplayBuffers.Unload Gaussian fixture"]
        self.assertEqual([row["operation"] for row in original], ["dispose-render-target", "virtual-target-remove"] * 12)
        fixture = [row for row in self.rows if row.get("owner") == "observer fixture foreign target lifetime"]
        self.assertEqual([row["operation"] for row in fixture], ["create-render-target", "dispose-render-target"])


if __name__ == "__main__":
    unittest.main()
