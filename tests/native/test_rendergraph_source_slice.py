import json
import os
from collections import Counter
from pathlib import Path
import sys
import unittest
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))


class RendergraphProfileTests(unittest.TestCase):
    def test_lifecycle_has_a_separate_bound_kind(self):
        from prepare_rendergraph_source_slice import KIND, CLAIM, validate_profile
        from native_room_revision import canonical_digest
        record = {"schema": 1, "kind": KIND, "claim": CLAIM}
        record["binding"] = canonical_digest(record)
        validate_profile(record)

    def test_unknown_profile_is_rejected_before_output(self):
        from prepare_rendergraph_source_slice import validate_profile
        with self.assertRaisesRegex(ValueError, "kind/version"):
            validate_profile({"schema": 1, "kind": "native-room-transition-gameplay-draw-v1"})

    def test_rebinding_cannot_expand_the_claim(self):
        from prepare_rendergraph_source_slice import KIND, validate_profile
        from native_room_revision import canonical_digest
        record = {"schema": 1, "kind": KIND, "claim": "full Level closure"}
        record["binding"] = canonical_digest(record)
        with self.assertRaisesRegex(ValueError, "scope"):
            validate_profile(record)

    def test_boolean_schema_is_not_a_version(self):
        from prepare_rendergraph_source_slice import KIND, validate_profile
        with self.assertRaisesRegex(ValueError, "kind/version"):
            validate_profile({"schema": True, "kind": KIND})

    def test_bad_binding_is_rejected_before_output_creation(self):
        from prepare_rendergraph_source_slice import KIND, CLAIM, AUDIT, run
        AUDIT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=AUDIT) as scratch:
            profile = Path(scratch) / "profile"
            profile.mkdir()
            (profile / "transition-profile.json").write_text(json.dumps({"schema": 1, "kind": KIND, "claim": CLAIM, "binding": "0" * 64}))
            output = Path(scratch) / "execution"
            with self.assertRaisesRegex(ValueError, "binding"):
                run(profile, output)
            self.assertFalse(output.exists())

    def test_rebound_missing_generated_identities_are_rejected_before_output(self):
        from prepare_rendergraph_source_slice import KIND, CLAIM, AUDIT, run
        from native_room_revision import canonical_digest
        AUDIT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=AUDIT) as scratch:
            profile = Path(scratch) / "profile"
            profile.mkdir()
            record = {"schema": 1, "kind": KIND, "claim": CLAIM, "profile_directory": str(profile)}
            record["binding"] = canonical_digest(record)
            (profile / "transition-profile.json").write_text(json.dumps(record))
            output = Path(scratch) / "execution"
            with self.assertRaisesRegex(ValueError, "generated"):
                run(profile, output)
            self.assertFalse(output.exists())


class OriginalEffectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from rendergraph_effect_contract import original_effects, ARCHIVE
        if not ARCHIVE.exists():
            raise unittest.SkipTest("Pinned private effect archive unavailable")
        cls.effects = original_effects()

    def test_dither_pass_has_original_pixel_sampler_register(self):
        effect = self.effects["Dither"]
        shader = effect["techniques"]["InvertDither"][0]["programs"][0]
        self.assertEqual(shader["stage"], "pixel")
        self.assertEqual(shader["constants"]["textSampler"]["register"], 0)
        self.assertEqual(shader["constants"]["textSampler"]["register_set"], 3)
        self.assertEqual(effect["parameters"]["size"]["columns"], 2)

    def test_primitive_has_original_world_matrix_and_two_shader_stages(self):
        effect = self.effects["Primitive"]
        programs = effect["techniques"]["NormalTechnique"][0]["programs"]
        self.assertEqual({p["stage"] for p in programs}, {"vertex", "pixel"})
        world = next(p for p in programs if p["stage"] == "vertex")["constants"]["World"]
        self.assertEqual((world["register_set"], world["register"], world["register_count"]), (2, 0, 4))

    def test_unknown_resource_is_rejected_before_parsing(self):
        from rendergraph_effect_contract import parse_effect
        with self.assertRaisesRegex(ValueError, "resource identity"):
            parse_effect("Dither", b"unknown")

    def test_original_parameter_defaults_are_read_not_assumed(self):
        self.assertEqual(self.effects["Dither"]["parameters"]["size"]["default_float32_bits"], [0, 0])
        self.assertEqual(self.effects["Primitive"]["parameters"]["World"]["default_float32_bits"], [0] * 16)


class ExecutedOriginalSliceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from prepare_rendergraph_source_slice import AUDIT, run
        profile = os.environ.get("RENDERGRAPH_SLICE_PROFILE")
        if not profile:
            raise unittest.SkipTest("Set RENDERGRAPH_SLICE_PROFILE to a freshly prepared private profile")
        with tempfile.TemporaryDirectory(dir=AUDIT) as scratch:
            output = Path(scratch) / "execution"
            receipt = run(Path(profile).resolve(), output)
            if receipt["returncode"] != 0:
                raise AssertionError("Original slice failed")
            cls.rows = [json.loads(line) for line in (output / "trace.jsonl").read_text().splitlines()]

    def operation(self, name):
        return [row for row in self.rows if row["operation"] == name]

    def test_original_create_recreate_unload_has_exact_sizes_and_unique_lifetimes(self):
        adds = self.operation("virtual-target-add")
        self.assertEqual(len(adds), 24)
        expected = [(320, 180)] * 5 + [(1024, 1024), (384, 244), (384, 244), (512, 512), (160, 160), (320, 180), (320, 180)]
        self.assertEqual([(r["data"]["width"], r["data"]["height"]) for r in adds], expected * 2)
        self.assertEqual([r["data"]["name"] for r in adds], ["gameplay-buffer-" + str(i) for i in range(12)] * 2)
        self.assertEqual(len({r["data"]["target"] for r in adds}), 24)
        self.assertEqual(len(self.operation("virtual-target-remove")), 24)

    def test_all_device_allocations_and_disposals_have_unique_target_ids(self):
        creates = self.operation("create-render-target")
        disposals = self.operation("dispose-render-target")
        self.assertEqual(len(creates), 25)
        self.assertEqual(len(disposals), 25)
        allocated = [row["data"]["Id"] for row in creates]
        self.assertEqual(len(set(allocated)), 25)
        self.assertEqual(Counter(row["data"]["Id"] for row in disposals), Counter(allocated))

    def test_foreign_disposal_preserves_original_lifetime_and_all_live_references(self):
        creates = self.operation("create-render-target")
        original = creates[0]["data"]["Id"]
        foreign = next(row["data"]["Id"] for row in creates if (row["data"]["Width"], row["data"]["Height"]) == (1, 1))
        self.assertNotEqual(foreign, original)
        live = {}
        foreign_disposed = False

        def check_references(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in ("target", "texture", "textureSlot0") and item is not None and item != "declared-backbuffer":
                        self.assertIn(item, live)
                        if key == "texture" and "dimensions" in value:
                            self.assertEqual(value["dimensions"], live[item])
                    else:
                        check_references(item)
            elif isinstance(value, list):
                for item in value:
                    check_references(item)

        for row in self.rows:
            data = row.get("data", {})
            if row["operation"] == "create-render-target":
                self.assertNotIn(data["Id"], live)
                live[data["Id"]] = [data["Width"], data["Height"]]
            elif row["operation"] == "dispose-render-target":
                self.assertIn(data["Id"], live)
                del live[data["Id"]]
                if data["Id"] == foreign:
                    foreign_disposed = True
                    self.assertEqual(live[original], [320, 180])
            else:
                check_references(data)
        self.assertTrue(foreign_disposed)
        self.assertEqual(live, {})
        self.assertIn("foreign disposal preserves original target lifetime", self.operation("slice-summary")[0]["verifiedChecks"])
        self.assertIn("foreign target must fail before trace mutation", self.operation("slice-summary")[0]["verifiedChecks"])

    def test_target_switch_and_backbuffer_restore_record_viewport_and_scissor(self):
        contexts = [r["data"] for r in self.operation("set-render-target")]
        self.assertEqual([r["viewport"] for r in contexts], [[0, 0, 1024, 1024], [7, 9, 100, 80], [0, 0, 320, 180],
                                                              [0, 0, 320, 180], [0, 0, 320, 180], [0, 0, 320, 180]])
        self.assertEqual(contexts[1]["scissor"], [2, 3, 40, 50])
        self.assertEqual(contexts[3]["target"], "declared-backbuffer")

    def test_original_lighting_render_flush_has_bound_effect_and_resolved_state(self):
        row = next(r["data"] for r in self.operation("batch-flush") if r["owner"] == "original LightingRenderer.Render")
        self.assertEqual(row["texture"], "target-4")
        self.assertEqual(row["dimensions"], [320, 180])
        self.assertEqual(row["effect"]["identity"], "GFX.FxDither")
        self.assertEqual(row["effect"]["technique"], "InvertDither")
        self.assertEqual(row["effect"]["passIndex"], 0)
        self.assertEqual(row["effect"]["parameters"]["size"]["value"], [1134559232, 1127481344])
        self.assertEqual(row["states"]["blend"]["ColorBlendFunction"], "ReverseSubtract")
        self.assertEqual(row["states"]["blend"]["AlphaSourceBlend"], "Zero")
        self.assertEqual(row["states"]["sampler"]["Filter"], "Point")
        self.assertEqual(row["states"]["sampler"]["AddressU"], "Clamp")
        self.assertFalse(row["states"]["depthStencil"]["DepthBufferEnable"])
        self.assertEqual(row["states"]["rasterizer"]["CullMode"], "None")

    def test_original_indexed_helper_preserves_indices_and_projected_world(self):
        row = next(r["data"] for r in self.operation("indexed-primitives") if r["owner"] == "original GFX.DrawIndexedVertices fixture")
        self.assertEqual(row["indices"], [0, 1, 2])
        self.assertEqual(len(row["vertices"]), 3)
        self.assertEqual(row["effect"]["technique"], "NormalTechnique")
        self.assertEqual(row["effect"]["parameters"]["World"]["value"][12:16], [-1082130432, 1065353216, 0, 1065353216])

    def test_nonfinite_geometry_is_encoded_losslessly(self):
        row = next(r["data"] for r in self.operation("indexed-primitives") if r["owner"] == "observer rejection and snapshot checks")
        self.assertEqual(row["vertices"][0]["positionFloat32Bits"][0], -4194303)
        self.assertEqual(row["vertices"][1]["positionFloat32Bits"][1], 2139095040)

    def test_effect_is_snapshotted_at_flush_not_at_begin(self):
        row = next(r["data"] for r in self.operation("batch-flush") if r["owner"] == "observer rejection and snapshot checks")
        self.assertEqual(row["effect"]["parameters"]["size"]["value"], [1093664768, 1095761920])

    def test_effect_is_snapshotted_at_apply_not_at_later_primitive_submission(self):
        row = next(r["data"] for r in self.operation("indexed-primitives") if r["owner"] == "observer apply-time parameter snapshot")
        self.assertEqual(row["effect"]["parameters"]["World"]["value"], [1065353216, 0, 0, 0, 0, 1065353216, 0, 0, 0, 0, 1065353216, 0, 0, 0, 0, 1065353216])

    def test_excluded_operations_fail_before_mutating_the_stream(self):
        summary = self.operation("slice-summary")[0]
        rejections = [name for name in summary["verifiedChecks"] if name.endswith("must fail before trace mutation")]
        self.assertEqual(len(rejections), 12)
        self.assertEqual([row["sequence"] for row in self.rows[:-1]], list(range(len(self.rows) - 1)))


if __name__ == "__main__":
    unittest.main()
