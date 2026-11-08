import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from compare_hazard_traces import compare, fixture_operations, FIELDS, FLOATS, BOOLS, DEFAULT_FIXTURES


def rows_for(fixture):
    rows = []
    for s in fixture_operations(fixture):
        v = {field: "0" for field in FIELDS}
        for i in FLOATS:
            v[FIELDS[i]] = "00000000"
        v.update(case=s.case, step=str(s.step), operation=s.operation, result=s.result, delta=s.delta, collider="normal",
                 dead=str(int(s.dead)), depth="-1000000" if s.dead else "0", locked=str(int(s.dead)), collidable=str(1-int(s.dead)),
                 removed=str(int(s.dead)), death_x=s.direction[0], death_y=s.direction[1],
                 events="corpse_created,corpse_added,player_removed" if s.dead else "-", checked=s.checked, overlaps=s.overlaps,
                 phases=s.phases, dashes="1", stamina="42dc0000", state="0", previous_state="-1", sample=s.sample)
        rows.append("\t".join(v[field] for field in FIELDS))
    return rows


class HazardValidationTests(unittest.TestCase):
    def setUp(self):
        directory = ROOT / ".audit/native-room-hazards/validator-tests"
        directory.mkdir(parents=True, exist_ok=True)
        temporary = self.enterContext(tempfile.TemporaryDirectory(dir=directory))
        self.fixture = Path(temporary) / "test.fixtures"
        self.fixture.write_text("case sample 0 0 0 0 -100 100\nspike 1 4 -8 16 left 1\ntick 0 0 0 0 0 0 0 0 0 => dead:1 1\ndie 0 -1 => ignored\ntick 0 0 0 0 0 0 0 0 0 => rejected -\n")
        self.rows = rows_for(self.fixture)

    def changed(self, index, field, value):
        rows = self.rows.copy()
        fields = rows[index].split("\t")
        fields[FIELDS.index(field)] = value
        rows[index] = "\t".join(fields)
        return rows

    def reject(self, rows):
        with self.assertRaises(ValueError):
            compare(rows, rows, self.fixture)

    def test_valid_death_guard_lifetime_coverage(self):
        self.assertEqual(compare(self.rows, self.rows, self.fixture), 3)

    def test_default_fixture_coverage(self):
        rows = rows_for(DEFAULT_FIXTURES)
        self.assertEqual(compare(rows, rows), 25)

    def test_malformed_fields_parameterized(self):
        invalid = {FIELDS[i]: "true" for i in BOOLS} | {FIELDS[i]: "7fc00000" for i in FLOATS}
        invalid |= {"case": "foreign", "step": "01", "operation": "other", "result": "frame", "collider": "hurt_normal",
                    "depth": "0", "events": "player_removed,corpse_added,corpse_created", "checked": "2", "overlaps": "-",
                    "phases": "complete", "dashes": "2", "state": "18", "previous_state": "0", "death_x": "00000000", "sample": "foreign"}
        for field, value in invalid.items():
            with self.subTest(field=field):
                self.reject(self.changed(0, field, value))

    def test_malformed_float_grammar_parameterized(self):
        for value in ("7f800000", "ff800000", "FFFFFFFF", "0000000Z", "0", "-0", "1.0"):
            with self.subTest(value=value):
                self.reject(self.changed(0, "x", value))

    def test_missing_row(self):
        self.reject(self.rows[:-1])

    def test_duplicate_row(self):
        self.reject([self.rows[0], *self.rows])

    def test_reordered_rows(self):
        self.reject([self.rows[1], self.rows[0], self.rows[2]])

    def test_foreign_row(self):
        self.reject(self.changed(0, "case", "foreign"))

    def test_identical_wrong_field_count(self):
        self.reject([self.rows[0] + "\t0", *self.rows[1:]])

    def test_identical_missing_death_event(self):
        self.reject(self.changed(0, "events", "corpse_added,player_removed"))

    def test_identical_extra_postdeath_phase(self):
        self.reject(self.changed(0, "phases", self.rows[0].split("\t")[26] + ",complete"))

    def test_first_divergence_is_exact_float_bit(self):
        with self.assertRaisesRegex(ValueError, "Row 1.*remainder_x"):
            compare(self.rows, self.changed(0, "remainder_x", "00000001"), self.fixture)

    def test_native_grammar_precedes_equality(self):
        with self.assertRaisesRegex(ValueError, "native row 1"):
            compare(self.rows, self.changed(0, "x", "bad"), self.fixture)

    def test_invalid_fixture_parameterized(self):
        prefix = "case sample 0 0 0 0 -100 100\n"
        tick = "tick 0 0 0 0 0 0 0 0 0 => alive -\n"
        invalid = (prefix, tick, prefix + "unknown\n", prefix + "spike 1 0 0 8 down 1\n" + tick,
                   prefix + "spike 1 0 0 0 up 1\n" + tick,
                   prefix + "spike 1 0 0 8 up 1\nspike 1 0 0 8 left 1\n" + tick,
                   prefix + "tick 0 0 0 0 0 0 0 0 0 => dead:2 2\n",
                   prefix + "spike 1 0 0 8 up 1\ntick 0 0 0 0 0 0 0 0 0 => alive 1,1\n",
                   prefix + tick + "spike 1 0 0 8 up 1\n", prefix + "die 0 -1 => ignored\n",
                   prefix + "tick 0 0 0 0 0 0 0 0 0 => rejected -\n", prefix + tick + prefix)
        for text in invalid:
            with self.subTest(text=text):
                self.fixture.write_text(text)
                self.reject(self.rows)
