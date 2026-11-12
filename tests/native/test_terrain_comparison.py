import copy
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from compare_native_terrain_draw import compare, compare_layer


class TerrainComparisonTests(unittest.TestCase):
    def setUp(self):
        self.materials = [{"sheet": 0, "sourceRectangle": [8, 16, 8, 8], "color": [255] * 4,
                           "origin": [0, 0], "scale": [1, 1], "rotation": 0, "alpha": 1}]
        self.sheets = [{"name": "syntheticSheet", "dimensions": [64, 64]}]
        self.native = {"commands": [[0, -8, 0], [0, -8, 8]]}
        command = {"sheet": "syntheticSheet", "dimensions": [64, 64], "sourceRectangle": [8, 16, 8, 8],
                   "color": [255] * 4, "origin": [0, 0], "scale": [1, 1], "rotation": 0}
        self.source = [{**copy.deepcopy(command), "position": [-8, y]} for y in (0, 8)]

    def differences(self):
        return compare_layer(self.source, self.native, self.materials, self.sheets)

    def test_full_ordered_logical_commands(self):
        self.assertEqual(self.differences(), [])

    def test_command_mutations_parameterized(self):
        for commands in ([[0, -8, 0]], [[0, -8, 8], [0, -8, 0]], [[0, -8, 0], [0, -8, 0]],
                         [[0, -8, 0], [0, -7.999999523162842, 8]]):
            with self.subTest(commands=commands):
                self.native["commands"] = commands
                self.assertTrue(self.differences())

    def test_descriptor_mutations_parameterized(self):
        original = copy.deepcopy(self.materials[0])
        for key, value in (("sourceRectangle", [9, 16, 8, 8]), ("color", [255, 255, 254, 255]),
                           ("scale", [-1, 1]), ("origin", [1, 0])):
            with self.subTest(key=key):
                self.materials[0] = {**copy.deepcopy(original), key: value}
                self.assertTrue(self.differences())

    def test_sheet_mutation(self):
        self.sheets[0]["name"] = "wrong"
        self.assertTrue(self.differences())

    def test_nonfinite_native_position_rejected(self):
        self.native["commands"][0][1] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite"):
            self.differences()

    def test_unknown_material_rejected(self):
        self.native["commands"][0][0] = 2
        with self.assertRaisesRegex(ValueError, "material"):
            self.differences()


class TerrainRouteEvidenceTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("CELESTE_TERRAIN_DRAW_NATIVE_TRACE"), "Requires a fresh actual native terrain observer run")
    def test_all514_all_ordered_terrain_commands_match(self):
        from test_native_gameplay_draw_projection import SOURCE_TRACE
        result = compare(SOURCE_TRACE, Path(os.environ["CELESTE_TERRAIN_DRAW_NATIVE_TRACE"]))
        self.assertEqual(result["failures"], [])
        self.assertEqual(result["native_commands"], 605992)


if __name__ == "__main__":
    unittest.main()
