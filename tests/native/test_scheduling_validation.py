import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from compare_scheduling_traces import compare


def row(step, event, detail, **values):
    fields = dict(case="simple", step=str(step), event=event, detail=detail, state="-1", previous="-1",
                  changed="0", locked="0", active="1", finished="0", wait="00000000", depth="1",
                  ended="0", removals="0", raw="0", delta="00000000", raw_delta="00000000")
    fields.update(values)
    return "\t".join(fields.values())


class SchedulingValidationTests(unittest.TestCase):
    def setUp(self):
        directory = ROOT / ".audit/native-scheduling/validator-tests"
        directory.mkdir(parents=True, exist_ok=True)
        temporary = self.enterContext(tempfile.TemporaryDirectory(dir=directory))
        self.fixture = Path(temporary) / "test.fixtures"
        self.fixture.write_text("case simple C 1\nscript A n\nconstruct A\ntick 0 0 => move:A:0\n")
        self.rows = [row(1, "return", "construct"), row(2, "move", "A:0"), row(2, "return", "tick")]

    def reject(self, rows):
        with self.assertRaises(ValueError):
            compare(rows, rows, self.fixture)

    def test_valid_protocol(self):
        self.assertEqual(compare(self.rows, self.rows, self.fixture), 3)

    def test_invalid_fields_parameterized(self):
        invalid = {0: "foreign", 1: "0", 2: "unknown", 3: "wrong", 4: "2", 5: "-2", 6: "true",
                   7: "2", 8: "-1", 9: "yes", 10: "7f800000", 11: "-1", 12: "no", 13: "1.5",
                   14: "3", 15: "nan", 16: "0000000Z"}
        for index, value in invalid.items():
            with self.subTest(field=index):
                rows = self.rows.copy()
                fields = rows[0].split("\t")
                fields[index] = value
                rows[0] = "\t".join(fields)
                self.reject(rows)

    def test_missing_operation(self):
        self.reject(self.rows[1:])

    def test_duplicated_operation(self):
        self.reject([self.rows[0], *self.rows])

    def test_missing_required_move(self):
        self.reject([self.rows[0], self.rows[-1]])

    def test_foreign_iterator(self):
        self.reject([self.rows[0], row(2, "move", "foreign:0"), self.rows[-1]])

    def test_out_of_range_script_step(self):
        self.reject([self.rows[0], row(2, "move", "A:8"), self.rows[-1]])

    def test_unexpected_callback(self):
        self.reject([self.rows[0], row(2, "begin", "0"), *self.rows[1:]])

    def test_truncated_trace(self):
        self.reject(self.rows[:-1])

    def test_unexpected_exception(self):
        self.reject([self.rows[0], self.rows[1], row(2, "throw", "tick")])

    def test_first_divergent_field(self):
        native = [*self.rows[:-1], row(2, "return", "tick", wait="3f000000")]
        with self.assertRaisesRegex(ValueError, "Row 3.*wait"):
            compare(self.rows, native, self.fixture)

    def test_legitimate_repeated_reentrant_callbacks(self):
        self.fixture.write_text("case simple M 3\nscript A n\ncallbacks 2 - script:A record -\n"
                                "set 2 => begin:2 factory:2 begin:2 factory:2\n")
        rows = [row(1, event, "2", state="2", changed="1") for event in ("begin", "factory", "begin", "factory")]
        rows.append(row(1, "return", "set", state="2", changed="1"))
        self.assertEqual(compare(rows, rows, self.fixture), 5)

    def test_invalid_fixture_expectation_is_rejected(self):
        self.fixture.write_text("case simple C 1\nscript A n\nconstruct A => move:unknown:0\n")
        self.reject([row(1, "move", "unknown:0"), row(1, "return", "construct")])

    def test_fixture_cannot_authorize_multiple_moves_per_tick(self):
        self.fixture.write_text("case simple C 1\nscript A n\ntick 0 0 => move:A:0 move:A:1\n")
        self.reject([row(1, "move", "A:0"), row(1, "move", "A:1"), row(1, "return", "tick")])

    def test_fixture_cannot_authorize_update_after_move(self):
        self.fixture.write_text("case simple M 3\nscript A n\ncallbacks 0 return:0 - - -\n"
                                "tick 0 0 => move:A:0 update:0\n")
        self.reject([row(1, "move", "A:0", state="0"), row(1, "update", "0", state="0"), row(1, "return", "tick", state="0")])

    def test_fixture_cannot_authorize_callback_for_wrong_role(self):
        self.fixture.write_text("case simple M 3\ncallbacks 0 - - return:0 -\nset 0 => begin:0\n")
        self.reject([row(1, "begin", "0", state="0"), row(1, "return", "set", state="0")])
