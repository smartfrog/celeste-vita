import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import compare_grid_traces as grid
import compare_loader_traces as loader


class GridValidationTests(unittest.TestCase):
    def setUp(self):
        private = ROOT / ".audit/native-static-tilemap/validator-tests"
        private.mkdir(parents=True, exist_ok=True)
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory(dir=private)))
        self.fixture = self.directory / "test.fixtures"
        self.fixture.write_text("case sample\nactor 0 0 1 1 0 0 1 1 0\ngrid 1 0 0 0 0 8 8 1 1 1 1\nQ 0 0\nQ 8 0\n")
        self.rows = [f"sample\t{step}\tquery\t0\t" + "\t".join(["00000000"] * 4 + ["-1", "-1"] + ["00000000"] * 6) for step in (1, 2)]

    def test_valid_grid_trace(self):
        self.assertEqual(grid.compare(self.rows, self.rows, self.fixture), 2)

    def test_identical_invalid_grid_trace_parameterized(self):
        variants = [[], self.rows[:-1], [self.rows[0], *self.rows], self.rows[::-1], [*self.rows, self.rows[0]],
                    [self.rows[0].replace("sample", "foreign"), self.rows[1]],
                    [self.rows[0].replace("00000000", "7fc00000", 1), self.rows[1]],
                    [self.rows[0] + "\t0", self.rows[1]]]
        for rows in variants:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                grid.compare(rows, rows, self.fixture)

    def test_invalid_grid_fixtures_parameterized(self):
        original = self.fixture.read_text()
        for text in (original.replace("1 1 1 1\nQ", "2 1 1 1\nQ"), original.replace("8 8 1 1", "0 8 1 1"),
                     original.replace("Q 0 0", "Q nan 0"), original + "case sample\n", original.replace("Q 0 0", "unknown")):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.fixture.write_text(text)
                grid.fixture_operations(self.fixture)

    def test_grid_first_divergence(self):
        changed = self.rows.copy(); changed[1] = changed[1].replace("00000000", "00000001", 1)
        with self.assertRaisesRegex(ValueError, "Row 2.*x:"):
            grid.compare(self.rows, changed, self.fixture)

    def loader_rows(self):
        self.fixture.write_text(json.dumps({"cases": [{"case": "synthetic", "levels": [{"name": "lvl_test", "x": 0, "y": 0, "width": 8, "height": 8, "solids": "1", "bg": ""}], "filler": []}]}))
        return ["\t".join((*fields, "0" * int(fields[4]))) for fields in loader.fixture_rows(self.fixture)]

    def test_valid_loader_trace(self):
        rows = self.loader_rows()
        self.assertEqual(loader.compare(rows, rows, self.fixture), len(rows))

    def test_identical_invalid_loader_trace_parameterized(self):
        rows = self.loader_rows()
        variants = [[], rows[:-1], [rows[0], *rows], rows[::-1], [*rows, rows[0]],
                    [rows[0].replace("synthetic", "foreign"), *rows[1:]],
                    [rows[0] + "0", *rows[1:]], [rows[0][:-1] + "2", *rows[1:]],
                    [rows[0].replace("\t0\t", "\t00\t", 1), *rows[1:]]]
        for changed in variants:
            with self.subTest(rows=changed), self.assertRaises(ValueError):
                loader.compare(changed, changed, self.fixture)

    def test_loader_first_cell_divergence(self):
        rows = self.loader_rows(); changed = rows.copy(); changed[0] = changed[0][:-1] + "1"
        with self.assertRaisesRegex(ValueError, "Row 1.*cells"):
            loader.compare(rows, changed, self.fixture)
