import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from compare_lifecycle_traces import compare, compare_render, equal


class LifecycleValidationTests(unittest.TestCase):
    def render_pair(self):
        fields = {"phase": "respawn14", "position": [19,144], "animation": "idle", "spriteScale": [1,1],
                  "spriteRotation": 0, "hairColor": [172,50,50,255], "hairNodes": [[19,133]]*4,
                  "introEase": 1, "deadOffset": [40,140], "effectPercent": None, "hasHair": True, "hairFacing": 1}
        source = {**fields, "tick": -1, "draws": [], "wipe": None, "wipeDraws": [], "rngAfter": 0,
                  "freezeAfterUpdate": 0, "updateStateAfter": {"entities": [{"state": 14, "wave": 0, "animationTimer": 0, "tweenTime": 0.6}],
                      "FrameCounter": 0, "TimeActive": 0, "RawTimeActive": 0}}
        native = {**copy.deepcopy(fields), "tick": -1, "state": 14, "draws": [], "wipe": None, "rngCalls": 0, "freeze": 0,
                  "frameCounter": 0, "timeActive": 0, "rawTimeActive": 0, "wave": 0, "animationTimer": 0, "tweenTime": 0.6}
        return source, native

    def test_identical_render_fields_pass(self):
        source, native = self.render_pair()
        compare_render(source, native, {}, {})

    def test_mutated_native_lifecycle_fields_are_rejected_parameterized(self):
        for key, value in (("phase", "live"), ("position", [19,145]), ("introEase", 0.9), ("tweenTime", 0.5),
                           ("rngCalls", 1), ("frameCounter", 1), ("freeze", 0.05), ("hairNodes", [[0,0]]*4),
                           ("animationTimer", 0.1), ("spriteScale", [1.5,0.5]), ("effectPercent", 0), ("state", 0)):
            with self.subTest(field=key):
                source, native = self.render_pair()
                native[key] = value
                with self.assertRaises(ValueError):
                    compare_render(source, native, {}, {})

    def test_missing_native_frame_cannot_pass(self):
        source, _ = self.render_pair()
        source["event"] = "contract-render"
        with self.assertRaisesRegex(ValueError, "source render ticks"):
            compare([source], [], {"frames": []}, {})

    def test_float32_adjacent_value_is_rejected(self):
        with self.assertRaises(ValueError):
            equal("effect", 0.5, 0.5000000596046448)

    def test_signed_zero_is_not_normalized(self):
        with self.assertRaises(ValueError):
            equal("zero", -0.0, 0.0)

    def test_nested_wipe_geometry_uses_float32_bits(self):
        with self.assertRaises(ValueError):
            equal("wipe", [{"position": [1.0000001192092896,0]}], [{"position": [1.0,0]}])


if __name__ == "__main__":
    unittest.main()
