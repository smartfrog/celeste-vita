import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from compare_input_traces import compare


def row(step, phase, operation, **values):
    fields = dict(case="simple", step=str(step), phase=phase, operation=operation,
                  buffer_time="00000000", first="00000000", multi="00000000",
                  buffer_counter="00000000", repeat_counter="00000000", can_repeat="0",
                  consumed="0", repeating="0", held="1", raw_pressed="1", raw_released="0",
                  disabled="0", debug="0", check="1", pressed="1", released="0", delta="00000000")
    fields.update(values)
    return "\t".join(fields.values())


class InputValidationTests(unittest.TestCase):
    def setUp(self):
        directory = ROOT / ".audit/native-buffered-input/validator-tests"
        directory.mkdir(parents=True, exist_ok=True)
        temporary = self.enterContext(tempfile.TemporaryDirectory(dir=directory))
        self.fixture = Path(temporary) / "test.fixtures"
        self.fixture.write_text("case simple 0\nsample 1 1 0 0 0\ntick 0\nconsume_buffer\nconsume_buffer\nquery\n")
        operations = ["sample", "tick", "consume_buffer", "consume_buffer", "query"]
        self.rows = [row(step, phase, operation) for step, operation in enumerate(operations, 1) for phase in ("before", "after")]
        self.rows[0] = row(1, "before", "sample", held="0", raw_pressed="0", check="0", pressed="0")

    def reject(self, rows):
        with self.assertRaises(ValueError):
            compare(rows, rows, self.fixture)

    def test_valid_protocol_with_legitimate_repeated_operations(self):
        self.assertEqual(compare(self.rows, self.rows, self.fixture), 10)

    def test_invalid_fields_parameterized(self):
        invalid = {0: "foreign", 1: "01", 2: "during", 3: "unknown",
                   4: "7f800000", 5: "nan", 6: "0000000Z", 7: "7fc00000", 8: "FFFFFFFF",
                   20: "-0"} | {i: "true" for i in range(9, 20)}
        for index, value in invalid.items():
            with self.subTest(field=index):
                rows = self.rows.copy()
                fields = rows[0].split("\t")
                fields[index] = value
                rows[0] = "\t".join(fields)
                self.reject(rows)

    def test_missing_operation(self):
        self.reject(self.rows[:4] + self.rows[6:])

    def test_duplicate_operation(self):
        self.reject(self.rows[:4] + self.rows[2:4] + self.rows[4:])

    def test_reordered_rows(self):
        self.reject([self.rows[1], self.rows[0], *self.rows[2:]])

    def test_missing_before_snapshot(self):
        self.reject(self.rows[1:])

    def test_truncated_final_snapshot(self):
        self.reject(self.rows[:-1])

    def test_foreign_extra_row(self):
        self.reject([*self.rows, row(6, "after", "query", case="foreign")])

    def test_empty_trace(self):
        self.reject([])

    def test_wrong_field_count_parameterized(self):
        for text in ("\t".join(self.rows[0].split("\t")[:-1]), self.rows[0] + "\t0"):
            with self.subTest(text=text):
                self.reject([text, *self.rows[1:]])

    def test_external_fixture_values_must_match_parameterized(self):
        for field, value in (("held", "1"), ("buffer_time", "3f800000"), ("first", "3f800000"),
                             ("multi", "3f800000"), ("delta", "3f800000")):
            with self.subTest(field=field):
                values = {"held": "0", "raw_pressed": "0", field: value}
                self.reject([row(1, "before", "sample", **values), *self.rows[1:]])

    def test_first_divergent_field(self):
        native = self.rows.copy()
        native[3] = row(2, "after", "tick", buffer_counter="3f000000")
        with self.assertRaisesRegex(ValueError, "Row 4.*buffer_counter"):
            compare(self.rows, native, self.fixture)

    def test_native_grammar_checked_before_equality(self):
        native = self.rows.copy()
        native[3] = row(2, "after", "tick", buffer_counter="not_bits")
        with self.assertRaisesRegex(ValueError, "native Row 4.*Invalid finite float32"):
            compare(self.rows, native, self.fixture)

    def test_invalid_fixture_grammar_parameterized(self):
        for text in ("query\n", "case simple 0\nunknown\n", "case simple 0\nsample 2 0 0 0 0\n",
                     "case simple 0\ntick nan\n", "case simple 0\nrepeat 1 2\n",
                     "case simple 0\nquery => anything\n", "case simple 0\nquery\ncase simple 0\nquery\n",
                     "case simple 0\nrepeat_pair 1\n", "case simple 0\n", "case 12bad 0\nquery\n"):
            with self.subTest(fixture=text):
                self.fixture.write_text(text)
                self.reject(self.rows)

    def test_arbitrary_valid_fixture_not_count_pinned(self):
        self.fixture.write_text("case simple -0.25\nrepeat_pair 0.5 -0.1\nquery\n")
        rows = [row(1, "before", "repeat_pair", buffer_time="be800000", held="0", raw_pressed="0")]
        rows += [row(step, phase, operation, buffer_time="be800000", first="3f000000", multi="bdcccccd", held="0", raw_pressed="0")
                 for step, phase, operation in ((1, "after", "repeat_pair"), (2, "before", "query"), (2, "after", "query"))]
        self.assertEqual(compare(rows, rows, self.fixture), 4)
