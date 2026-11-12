"""CPU gameplay assembly boundaries; private route evidence is opt-in."""

import os
import copy
from pathlib import Path
import subprocess
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from compare_native_gameplay_draw import SourceBindings, compare_frame


def frames():
    geometry = [[0, 0, 0, 0, 0] for _ in range(4)]
    image = {"sheet": "Fixture", "dimensions": [64, 64], "sourceRectangle": [0, 0, 8, 8],
             "position": [0, 0], "origin": [0, 0], "scale": [1, 1], "rotation": 0,
             "color": [255, 255, 255, 255], "effects": "None", "clipping": "atlas source rectangle; GPU scissor not observed",
             "finiteGeometry": True, "verticesFloat32Bits": geometry}
    source_command = dict(image, index=0, owner={"entity": "source-bg", "type": "BackgroundTiles", "componentType": "TileGrid"})
    source = {"tick": 0, "commands": [source_command], "keys": {"source-bg": ("BackgroundTiles",)},
              "dispatch": [{"entity": "source-bg", "drawStart": 0, "drawEnd": 1}], "excluded": []}
    native_command = dict(image, index=0, ownerIdentity=42, dispatchIndex=0, piece=0, componentType="TileGrid")
    native = {"tick": 0, "commands": [native_command], "keys": {42: ("BackgroundTiles",)},
              "dispatch": [{"ownerIdentity": 42, "begin": 0, "end": 1, "emptyReason": None}], "excluded": [],
              "summary": {"commands": 1, "geometryWords": 20, "renderCalls": 1}}
    return copy.deepcopy(source), copy.deepcopy(native)


class GameplayGlobalComparisonTests(unittest.TestCase):
    def test_geometry_shape_is_measured(self):
        source, native = frames()
        result = compare_frame(source, native)
        self.assertEqual(result["words"], 20)

    def test_first_bit_mismatch_identifies_global_index_vertex_and_field(self):
        source, native = frames()
        native["commands"][0]["verticesFloat32Bits"][2][3] = -2147483648
        with self.assertRaisesRegex(ValueError, r"tick 0 global 0.*vertex 2 field 3"):
            compare_frame(source, native)

    def test_nonfinite_geometry_words_are_not_canonicalized(self):
        source, native = frames()
        source["commands"][0]["verticesFloat32Bits"][0][0] = -4194304
        native["commands"][0]["verticesFloat32Bits"][0][0] = 2143289344
        with self.assertRaisesRegex(ValueError, "vertex 0 field 0"):
            compare_frame(source, native)

    def test_component_attribution_cannot_be_silently_mapped(self):
        source, native = frames()
        native["commands"][0]["componentType"] = None
        with self.assertRaisesRegex(ValueError, "componentType"):
            compare_frame(source, native)

    def test_unused_command_outside_dispatch_range_rejects(self):
        source, native = frames()
        native["dispatch"][0]["end"] = 0
        with self.assertRaisesRegex(ValueError, "range"):
            compare_frame(source, native)

    def test_signed_zero_logical_float_is_not_canonicalized(self):
        source, native = frames()
        native["commands"][0]["position"][0] = -0.0
        with self.assertRaisesRegex(ValueError, "position float32"):
            compare_frame(source, native)

    def test_global_owner_order_is_not_reconstructed_by_family(self):
        source, native = frames()
        native["keys"][42] = ("SolidTiles",)
        with self.assertRaisesRegex(ValueError, "semantic owner"):
            compare_frame(source, native)

    def test_source_authored_binding_uses_position_not_source_or_native_order(self):
        authored = [{"attributes": {"name": "lvl_1", "x": 0, "y": 0, "width": 320, "height": 184},
                     "children": [{"name": "entities", "children": [
                         {"name": "player", "attributes": {"x": 0, "y": 0}},
                         {"name": "spikesUp", "attributes": {"id": 7, "x": 10, "y": 20, "width": 8}},
                         {"name": "spikesUp", "attributes": {"id": 8, "x": 30, "y": 40, "width": 8}}]}]}]
        bindings = SourceBindings(authored)
        roster = [{"entity": "second-source-object", "type": "Spikes", "position": [30, 40]},
                  {"entity": "first-source-object", "type": "Spikes", "position": [10, 20]}]
        result = bindings.bind({"room": "1", "transition": None}, roster)
        self.assertEqual(result, {"second-source-object": ("Spikes", "1", 8), "first-source-object": ("Spikes", "1", 7)})

    def test_unknown_source_family_is_not_skipped(self):
        with self.assertRaisesRegex(ValueError, "Unknown SOURCE gameplay owner family"):
            SourceBindings([]).bind({"room": "1", "transition": None}, [{"entity": "unknown", "type": "Unknown"}])


class GameplayCommandCliTests(unittest.TestCase):
    def test_missing_catalogs_reject_before_any_input_read_or_stdout(self):
        runner = os.environ.get("CELESTE_GAMEPLAY_RUNNER")
        if runner is None:
            self.skipTest("Requires an explicitly selected native runner")
        result = subprocess.run([str(Path(runner)), *(["missing"] * 6), "--gameplay-commands"],
                                text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("Gameplay commands require", result.stderr)


if __name__ == "__main__":
    unittest.main()
