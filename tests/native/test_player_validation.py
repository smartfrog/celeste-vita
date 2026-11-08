import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from compare_player_traces import compare, fixture_operations, FIELDS, FLOAT_FIELDS, BOOL_FIELDS


def rows_for(fixture):
    rows = []
    for snapshot in fixture_operations(fixture):
        values = {field: "0" for field in FIELDS}
        for index in FLOAT_FIELDS:
            values[FIELDS[index]] = "00000000"
        values.update(case=snapshot.case, frame=str(snapshot.frame), phase=snapshot.phase, facing="1", hurtbox="normal",
                      dashes="1", state="0", previous_state="-1", hit=snapshot.hit)
        for field, value in zip(FIELDS[3:12], snapshot.sample):
            values[field] = value
        if snapshot.hit != "-1":
            values["direction_x" if snapshot.phase.endswith("_h") else "direction_y"] = "3f800000"
        rows.append("\t".join(values[field] for field in FIELDS))
    return rows


class PlayerValidationTests(unittest.TestCase):
    def setUp(self):
        directory = ROOT / ".audit/native-player-normal/validator-tests"
        directory.mkdir(parents=True, exist_ok=True)
        temporary = self.enterContext(tempfile.TemporaryDirectory(dir=directory))
        self.fixture = Path(temporary) / "test.fixtures"
        self.fixture.write_text("case simple 0 0 0 0 -100 100\nsolid 1 0 0 8 8 1\ntick 0 0 0 0 0 0 0 0 0 => h:1 v:1\ntick 0.1 1 0 1 1 0 0 0 0\n")
        self.rows = rows_for(self.fixture)

    def reject(self, rows):
        with self.assertRaises(ValueError):
            compare(rows, rows, self.fixture)

    def changed(self, index, field, value):
        rows = self.rows.copy()
        f = rows[index].split("\t")
        f[FIELDS.index(field)] = value
        rows[index] = "\t".join(f)
        return rows

    def test_valid_repeated_platform_collision_identity(self):
        self.assertEqual(compare(self.rows, self.rows, self.fixture), len(self.rows))

    def test_invalid_fields_parameterized(self):
        invalid = {"case": "foreign", "frame": "01", "phase": "unknown", "facing": "0", "move_x": "2", "wall_dir": "-2",
                   "hurtbox": "other", "dashes": "2", "state": "1", "previous_state": "0", "hit": "2"}
        invalid |= {FIELDS[i]: "true" for i in BOOL_FIELDS}
        invalid |= {FIELDS[i]: "7fc00000" for i in FLOAT_FIELDS}
        for field, value in invalid.items():
            with self.subTest(field=field):
                self.reject(self.changed(0, field, value))

    def test_nonfinite_and_noncanonical_float_grammar_parameterized(self):
        for value in ("7f800000", "ff800000", "FFFFFFFF", "0000000Z", "0", "-0", "1.0"):
            with self.subTest(value=value):
                self.reject(self.changed(0, "speed_y", value))

    def test_missing_frame(self):
        self.reject(self.rows[:-10])

    def test_missing_phase(self):
        self.reject(self.rows[:4] + self.rows[5:])

    def test_duplicate_phase(self):
        self.reject(self.rows[:4] + [self.rows[3]] + self.rows[4:])

    def test_reordered_phases(self):
        self.reject([self.rows[1], self.rows[0], *self.rows[2:]])

    def test_identical_foreign_extra_row(self):
        self.reject([*self.rows, self.rows[0]])

    def test_empty_trace(self):
        self.reject([])

    def test_wrong_field_count_parameterized(self):
        for row in (self.rows[0] + "\t0", self.rows[0].rsplit("\t", 1)[0]):
            with self.subTest(row=row):
                self.reject([row, *self.rows[1:]])

    def test_sample_and_delta_coverage_parameterized(self):
        for field, value in (("delta", "3f800000"), ("held", "1"), ("input_x", "1"), ("disabled", "1")):
            with self.subTest(field=field):
                self.reject(self.changed(0, field, value))

    def test_invalid_callback_direction(self):
        index = next(i for i, row in enumerate(self.rows) if "\tcollision_h\t" in row)
        self.reject(self.changed(index, "direction_y", "3f800000"))

    def test_noncallback_payload(self):
        self.reject(self.changed(0, "target_x", "3f800000"))

    def test_first_divergent_field_without_epsilon(self):
        native = self.changed(4, "speed_y", "00000001")
        with self.assertRaisesRegex(ValueError, "Row 5.*speed_y"):
            compare(self.rows, native, self.fixture)

    def test_native_grammar_validated_before_equality(self):
        native = self.changed(4, "speed_y", "not_bits")
        with self.assertRaisesRegex(ValueError, "native Row 5.*Invalid finite float32"):
            compare(self.rows, native, self.fixture)

    def test_invalid_fixture_grammar_parameterized(self):
        prefix = "case simple 0 0 0 0 -100 100\n"
        invalid = ("tick 0 0 0 0 0 0 0 0 0\n", prefix, prefix + "unknown\n", prefix + "tick nan 0 0 0 0 0 0 0 0\n",
                   prefix + "tick 0 2 0 0 0 0 0 0 0\n", prefix + "tick 0 0 0 2 0 0 0 0 0\n",
                   prefix + "tick 0 0 0 0 0 0 0 0 0 => h:2\n", prefix + "tick 0 0 0 0 0 0 0 0 0 =>\n",
                   prefix + "tick 0 0 0 0 0 0 0 1 0\n", prefix + "solid 1 0 0 -8 8 1\n",
                   prefix + "solid 1 0 0 8 8 1\nsolid 1 0 0 8 8 1\n",
                   prefix + "tick 0 0 0 0 0 0 0 0 0\n" + prefix,
                   prefix + "tick 0 0 0 0 0 0 0 0 0\nsolid 1 0 0 8 8 1\n")
        for text in invalid:
            with self.subTest(fixture=text):
                self.fixture.write_text(text)
                self.reject(self.rows)

    def test_arbitrary_fixture_with_rejections_not_count_pinned(self):
        self.fixture.write_text("case other 0 0 0 0 -10 10\ntick 0 0 0 0 0 0 0 0 1 => !input\ntick 0.1 0 0 1 1 0 0 0 0 => !normal\n")
        rows = rows_for(self.fixture)
        self.assertEqual(compare(rows, rows, self.fixture), 5)

    def test_legitimate_same_axis_repeated_callbacks(self):
        self.fixture.write_text("case repeated 0 0 0 0 -10 10\nsolid 1 0 0 8 8 1\ntick 0 0 0 0 0 0 0 0 0 => h:1 h:1\n")
        rows = rows_for(self.fixture)
        self.assertEqual(compare(rows, rows, self.fixture), 14)
