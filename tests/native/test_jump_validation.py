from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from compare_dash_traces import FIELDS, FLOATS, fixture_operations
from compare_jump_traces import compare
from fixture_protocol import float_bits


class JumpCoverageTests(unittest.TestCase):
    def test_identical_nonjumping_traces_cannot_claim_jump_family(self):
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as folder:
            fixture = Path(folder) / "jumps.fixtures"
            fixture.write_text("case wall_right_neutral 0 -100 0 0 -10000 10000\ntick 0 0 0 0 0 0 0 0 0 0 0 0 0 0\n")
            rows = []
            for case, frame, phase, hit, raw in fixture_operations(fixture):
                row = {field: "00000000" if field in FLOATS else "0" for field in FIELDS}
                row.update(case=case, frame=frame, phase=phase, hit=hit, raw=raw, checked="-", overlaps="-", stamina=float_bits("110"))
                rows.append("\t".join(row[field] for field in FIELDS))
            with self.assertRaises(ValueError):
                compare(rows, rows, fixture)
