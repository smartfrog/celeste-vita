import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from compare_player_presentation import compare_outputs, coverage, projection_input, mutate_output


FIXTURE = "case sample 0 0 0 0 -100 100\ntick 0 0 0 0 0 0 0 0 0 0 0 0 0 0\n"


def projection(phase="render"):
    fields = ["P", "sample", "1", phase, *(["00000000"] * 5), "1", "0", "0", "0", "0", "0", "0", "0", "1", "0", "0", "0",
              "00000000", "00000000", "00", "0000", "00"]
    return "\t".join(fields) + "\n"


def visuals():
    return "\n".join("\t".join([kind, "sample", "1", "render"] + ["0"] * count)
                     for kind, count in (("R", 36), ("D", 13), ("V", 8))) + "\n"


class PresentationOracleBoundaryTests(unittest.TestCase):
    def test_visual_outputs_are_never_reference_inputs(self):
        common = projection()
        self.assertEqual(projection_input(common + visuals(), FIXTURE), common)

    def test_native_visual_output_mutations_do_not_change_common_input(self):
        common = projection()
        for kind in ("R", "D", "V"):
            with self.subTest(record=kind):
                records = visuals().splitlines()
                index = next(i for i, row in enumerate(records) if row.startswith(kind + "\t"))
                fields = records[index].split("\t")
                fields[4] = "tampered"
                records[index] = "\t".join(fields)
                mutant = "\n".join(records) + "\n"
                self.assertEqual(projection_input(common + mutant, FIXTURE), common)
                with self.assertRaisesRegex(ValueError, "mismatch"):
                    compare_outputs(mutant, visuals())

    def test_extra_animation_state_column_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "whitelist"):
            projection_input(projection().rstrip() + "\tanimation=idle\n", FIXTURE)

    def test_undeclared_projection_tick_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "declared"):
            projection_input(projection().replace("sample\t1", "sample\t2"), FIXTURE)

    def test_reordered_source_phases_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "phase"):
            projection_input(projection("select") + projection(), FIXTURE)

    def test_projected_raw_input_must_match_fixture(self):
        with self.assertRaisesRegex(ValueError, "raw input"):
            projection_input(projection(), FIXTURE.replace("tick 0 0 0", "tick 0 1 0"))

    def test_required_fixture_ticks_cannot_be_omitted(self):
        with self.assertRaisesRegex(ValueError, "omitted"):
            projection_input(projection(), FIXTURE + FIXTURE.splitlines()[1] + "\n", require_all=True)

    def test_empty_equal_visual_outputs_cannot_pass(self):
        with self.assertRaisesRegex(ValueError, "Empty"):
            compare_outputs("", "")

    def test_incomplete_independent_family_coverage_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "coverage"):
            coverage(visuals())

    def test_wrong_idle_random_ordinal_cannot_pass(self):
        mutant = mutate_output(visuals(), "R", 37, "999999", case="sample")
        self.assertEqual(projection_input(projection() + mutant, FIXTURE), projection())
        with self.assertRaisesRegex(ValueError, "mismatch"):
            compare_outputs(mutant, visuals())


if __name__ == "__main__":
    unittest.main()
