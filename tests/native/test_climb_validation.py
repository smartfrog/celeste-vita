from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from compare_climb_traces import compare, FIELDS, validate_coverage
from compare_dash_traces import fixture_operations


class ClimbCoverageTests(unittest.TestCase):
    def test_empty_equal_traces_cannot_claim_climb(self):
        with self.assertRaises(ValueError):
            compare([], [])

    def test_nonclimbing_equal_trace_cannot_claim_climb(self):
        row = ["0"] * len(FIELDS)
        row[:3] = ["entry_right", "1", "complete"]
        with self.assertRaisesRegex(ValueError, "state"):
            validate_coverage(["\t".join(row)], "synthetic")

    def test_repository_declares_nine_groups_with_freeze_and_collisions(self):
        operations = fixture_operations(Path(__file__).with_name("climb.fixtures"), point_queries=True)
        self.assertTrue({"input", "freeze", "dash_update", "collision_v"} <= {row[2] for row in operations})

    def test_opt_in_schema_retains_all_historical_dash_fields(self):
        from compare_dash_traces import FIELDS as old
        self.assertEqual(FIELDS[:len(old)], old)
