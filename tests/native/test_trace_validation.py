import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from compare_native_traces import compare


def row(case, step, event="return", result="0", hit="-1", pusher="-1"):
    return "\t".join([case, str(step), event, result, *("00000000",) * 4,
                       hit, pusher, *("00000000",) * 6])


def baseline():
    rows = []
    for line in (ROOT / "tests/native/movement.fixtures").read_text().splitlines():
        fields = line.split()
        if not fields or fields[0].startswith("#"):
            continue
        if fields[0] == "case":
            case, step = fields[1], 0
        elif fields[0] in {"H", "V", "HX", "VX", "Q", "O"}:
            step += 1
            rows.append(row(case, step, "query" if fields[0] in {"Q", "O"} else "return"))
    return rows


class TraceValidationTests(unittest.TestCase):
    def assert_rejected(self, rows, message="."):
        with self.assertRaisesRegex(ValueError, message):
            compare(rows, rows)

    def test_fixture_complete_protocol_baseline_is_valid(self):
        rows = baseline()
        self.assertEqual(compare(rows, rows), len(rows))

    def test_identical_sixteen_invalid_fields_are_rejected(self):
        self.assert_rejected(["\t".join(["invalid"] * 16)], "Row 1")

    def test_identical_invalid_fields_parameterized(self):
        invalid = {0: "foreign", 1: "0", 2: "invalid", 3: "true", 4: "xyzxyzxy", 5: "0",
                   6: "7f800000", 7: "7fc00000", 8: "-2", 9: "1.0", 10: "3F800000",
                   11: "inf", 12: "nan", 13: "000000000", 14: "-0000000", 15: "invalid!"}
        for index, value in invalid.items():
            with self.subTest(field=index):
                rows = baseline()
                fields = rows[0].split("\t")
                fields[index] = value
                rows[0] = "\t".join(fields)
                self.assert_rejected(rows, "Row 1")

    def test_identical_duplicated_terminal_operation_is_rejected(self):
        rows = baseline()
        rows.insert(1, rows[0])
        self.assert_rejected(rows, "operation|terminal")

    def test_identical_missing_middle_operation_is_rejected(self):
        rows = baseline()
        del rows[3]
        self.assert_rejected(rows, "operation|terminal")

    def test_identical_truncated_trace_is_rejected(self):
        self.assert_rejected(baseline()[:-1], "Missing|missing")

    def test_identical_foreign_operation_is_rejected(self):
        rows = baseline()
        rows.insert(1, row("positive_half", 2))
        self.assert_rejected(rows, "operation")

    def test_missing_terminal_after_callback_is_rejected(self):
        rows = baseline()
        index = next(i for i, value in enumerate(rows) if value.startswith("callback_reentry_h\t"))
        rows[index] = row("callback_reentry_h", 1, "callback", "-", "1")
        self.assert_rejected(rows, "operation|terminal")

    def test_nested_callbacks_and_reentry_are_valid(self):
        rows = baseline()
        index = next(i for i, value in enumerate(rows) if value.startswith("callback_reentry_h\t"))
        rows[index:index + 1] = [row("callback_reentry_h", 1, "callback", "-", "1"),
                                row("callback_reentry_h", 1, "callback", "-", "2"),
                                row("callback_reentry_h", 1, "reentry", "1"),
                                row("callback_reentry_h", 1, result="1")]
        self.assertEqual(compare(rows, rows), len(rows))

    def test_reentry_without_outer_callback_is_rejected(self):
        rows = baseline()
        index = next(i for i, value in enumerate(rows) if value.startswith("callback_reentry_h\t"))
        rows.insert(index, row("callback_reentry_h", 1, "reentry"))
        self.assert_rejected(rows, "event|callback|reentry")

    def test_duplicate_nested_callback_is_rejected(self):
        rows = baseline()
        index = next(i for i, value in enumerate(rows) if value.startswith("callback_reentry_h\t"))
        rows[index:index + 1] = [row("callback_reentry_h", 1, "callback", "-", "1")] * 3 + [
            row("callback_reentry_h", 1, "reentry"), row("callback_reentry_h", 1, result="1")]
        self.assert_rejected(rows, "event|callback")

    def test_query_cannot_be_replaced_by_move_terminal(self):
        rows = baseline()
        index = next(i for i, value in enumerate(rows) if "\tquery\t" in value)
        rows[index] = rows[index].replace("\tquery\t", "\treturn\t")
        self.assert_rejected(rows, "terminal|event")

    def test_first_divergent_float_bit_is_reported(self):
        left, right = baseline(), baseline()
        fields = right[0].split("\t")
        fields[4] = "00000001"
        right[0] = "\t".join(fields)
        with self.assertRaisesRegex(ValueError, "positive_half step 1 return, x"):
            compare(left, right)

    def test_native_grammar_is_validated_before_comparison(self):
        left, right = baseline(), baseline()
        fields = right[0].split("\t")
        fields[1] = "0"
        right[0] = "\t".join(fields)
        with self.assertRaisesRegex(ValueError, "native Row 1: invalid step"):
            compare(left, right)

    def test_empty_trace_is_rejected(self):
        self.assert_rejected([], "empty")

    def test_different_future_fixture_coverage_is_derived(self):
        directory = ROOT / ".audit/native-validation-tests"
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory) as temporary:
            fixture = Path(temporary) / "future.fixtures"
            fixture.write_text("case future\nactor 0 0 1 1 0 0 1 1 0\nH 0.25 none -1\nV 0 none -1\n")
            rows = [row("future", 1), row("future", 2)]
            self.assertEqual(compare(rows, rows, fixtures=fixture), 2)
            with self.assertRaisesRegex(ValueError, "Missing|missing"):
                compare(rows[:1], rows[:1], fixtures=fixture)


if __name__ == "__main__":
    unittest.main()
