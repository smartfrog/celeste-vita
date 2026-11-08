import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from prepare_static_tilemap import build_layers, build_mask


class VisualLayerTests(unittest.TestCase):
    def test_material_characters_survive(self):
        driver = {"levels": [dict(name="synthetic", x=0, y=0, width=8, height=8, solids="3", bg="1")], "filler": []}
        x, y, foreground, background, bounds = build_layers(driver)
        self.assertEqual((foreground[-x // 8, -y // 8], background[-x // 8, -y // 8]), ("3", "1"))

    def test_level_bounds_are_global_cells(self):
        driver = {"levels": [dict(name="synthetic", x=0, y=0, width=8, height=184, solids="1", bg="1")], "filler": []}
        self.assertEqual(build_layers(driver)[4], [(8, 8, 1, 23)])

    def test_binary_mask_collapses_materials_only_at_boundary(self):
        driver = {"levels": [dict(name="synthetic", x=0, y=0, width=16, height=8, solids="34", bg="10")], "filler": []}
        x, y, foreground, _, _ = build_layers(driver)
        mask = build_mask(driver)
        self.assertEqual(mask, (x, y, foreground.columns, foreground.rows, "".join("0" if c == "0" else "1" for c in foreground.data)))


if __name__ == "__main__":
    unittest.main()
