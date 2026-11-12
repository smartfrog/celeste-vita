import copy
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from prepare_terrain_catalog import AUDIT, PINS, encode_catalog, prepare, verify_inputs


class TerrainCatalogTests(unittest.TestCase):
    def setUp(self):
        self.cells = [{"layer": "BG", "x": 1, "y": 2, "character": "x", "rule": "synthetic",
                       "rng": 1, "variant": 0, "source": "synthetic/tile", "rectangle": [8, 16, 8, 8]}]
        self.atlas = {"synthetic/tile": ["syntheticSheet", 8, 16, 16, 16, 0, 0, 16, 16]}
        self.pins = ["a" * 64] * 4

    def encode(self):
        return encode_catalog(self.cells, self.atlas, {"syntheticSheet": [64, 64]}, self.pins,
                              origin=(-16, -16), dimensions=(8, 6))

    def test_sparse_catalog_contains_source_identity(self):
        self.assertIn(b"synthetic/tile 0 8 16 8 8 0 0 8 8 255 255 255 255 1\n", self.encode())

    def test_duplicate_cell_rejected(self):
        self.cells.append(copy.deepcopy(self.cells[0]))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.encode()

    def test_malformed_cells_parameterized(self):
        for key, value in (("layer", "X"), ("x", 8), ("y", -1), ("x", True),
                           ("rectangle", [8, 16, 7, 8]), ("rectangle", [60, 16, 8, 8]),
                           ("source", "unknown"), ("character", "0")):
            with self.subTest(key=key, value=value):
                original = self.cells[0][key]
                self.cells[0][key] = value
                with self.assertRaises(ValueError):
                    self.encode()
                self.cells[0][key] = original

    def test_nonzero_draw_offset_rejected(self):
        self.atlas["synthetic/tile"][5] = 1
        with self.assertRaises(ValueError):
            self.encode()

    def test_missing_sheet_rejected(self):
        self.atlas["synthetic/tile"][0] = "unknown"
        with self.assertRaises(ValueError):
            self.encode()

    def test_generator_pins_before_decoding(self):
        with self.assertRaisesRegex(ValueError, "pin"):
            verify_inputs({"commands": b"not JSON"})

    def test_each_input_pin_rejected_before_decoding_parameterized(self):
        good = b"not JSON"
        with patch.dict(PINS, {name: hashlib.sha256(good).hexdigest() for name in PINS}, clear=True):
            for name in PINS:
                with self.subTest(name=name):
                    inputs = {key: good for key in PINS}
                    inputs[name] += b"tampered"
                    with self.assertRaisesRegex(ValueError, "pin changed: " + name):
                        verify_inputs(inputs)

    def test_bad_inputs_create_no_output_or_directory(self):
        output = MagicMock()
        output.resolve.return_value = AUDIT / "synthetic-must-not-exist/catalog.txt"
        output.exists.return_value = False
        paths = {name: MagicMock() for name in PINS}
        for path in paths.values():
            path.read_bytes.return_value = b"tampered"
        with self.assertRaisesRegex(ValueError, "pin changed"):
            prepare(paths, output)
        output.parent.mkdir.assert_not_called()
        output.open.assert_not_called()

    def test_existing_output_is_never_overwritten(self):
        output = MagicMock()
        output.resolve.return_value = AUDIT / "synthetic/catalog.txt"
        output.exists.return_value = True
        with self.assertRaisesRegex(ValueError, "fresh"):
            prepare({}, output)
        output.open.assert_not_called()

    def test_public_output_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "private"):
            prepare({}, Path(__file__).parent / "synthetic-catalog.txt")


if __name__ == "__main__":
    unittest.main()
