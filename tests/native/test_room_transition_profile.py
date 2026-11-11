from pathlib import Path
import copy
import hashlib
import sys
import unittest
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from prepare_room_transition_oracle import mechanical_rooms, verify_inputs, promote
from compare_room_transition_contract import validate, compare, same
from run_room_transition_probe import validate_controls


class RoomTransitionProfileTests(unittest.TestCase):
    def room(self, name):
        return {"name": "level", "attributes": {"name": name}, "children": [
            {"name": "entities", "attributes": {}, "children": [{"name": "spring", "attributes": {}, "children": []}]},
            {"name": "fgdecals", "attributes": {}, "children": [{"name": "decal"}]},
        ]}

    def test_materialization_keeps_destination_mechanical_entities(self):
        rooms = [self.room("lvl_1"), self.room("lvl_2")]
        result, _ = mechanical_rooms(rooms)
        self.assertEqual(result[1]["children"][0], rooms[1]["children"][0])

    def test_materialization_does_not_mutate_read_only_map_input(self):
        rooms = [self.room("lvl_1"), self.room("lvl_2")]
        before = copy.deepcopy(rooms)
        mechanical_rooms(rooms)
        self.assertEqual(rooms, before)

    def test_materialization_rejects_missing_destination(self):
        with self.assertRaisesRegex(ValueError, "exactly"):
            mechanical_rooms([self.room("lvl_1")])

    def test_native_import_guard_must_be_bound_in_compile_inputs(self):
        with self.assertRaisesRegex(ValueError, "NativeImportGuard"):
            verify_inputs({})

    def test_guard_inventory_without_compilation_binding_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "NativeImportGuard"):
            verify_inputs({"/p/NativeImportGuard.cs": {}}, ["/p/Other.cs"])

    def test_position_tape_is_not_a_legal_input_fixture(self):
        with self.assertRaises(ValueError):
            validate_controls({"schema": 1, "seed": 1, "runs": [{"frames": 1, "keys": [], "position": [276, -24]}]})

    def test_fixed_fixture_contains_only_legal_open_loop_inputs(self):
        fixture = Path(__file__).with_name("room-transition.inputs.json")
        self.assertEqual(validate_controls(json.loads(fixture.read_text())), 514)

    def test_promotion_rejects_a_non_guarded_body(self):
        with self.assertRaisesRegex(ValueError, "Missing original guarded"):
            promote("public void Tick() {}", "public void Tick()\n{}", "Source.cs")

    def test_promotion_rejects_ambiguous_source_binding(self):
        guard = 'public void Tick() { throw new DeathOracle.UnsupportedClosure("Excluded source member: /p/Source.cs:Tick"); }'
        with self.assertRaisesRegex(ValueError, "Missing original guarded"):
            promote(guard + guard, "public void Tick()\n{}", "Source.cs")

    def test_expression_member_promotion_is_source_bound(self):
        guard = 'public int this[int index] => throw new DeathOracle.UnsupportedClosure("Excluded source accessor: /p/Source.cs:this");'
        original = 'public int this[int index] => values[index];'
        self.assertEqual(promote(guard, original, "Source.cs"), original)

    def test_constructor_promotion_preserves_original_base_initializer(self):
        guard = 'public Source(int width)\n\t\t: base(width)\n{ throw new DeathOracle.UnsupportedClosure("Excluded source member: /p/Source.cs:Source.ctor"); }'
        original = 'public Source(int width)\n\t\t: base(width)\n{ value = width; }'
        self.assertEqual(promote(guard, original, "Source.cs"), original)

    def test_auto_property_promotion_rejects_wrong_source(self):
        guard = 'public bool Winged { get{ throw new DeathOracle.UnsupportedClosure("Excluded source member: /p/Other.cs:Winged.get"); }private set{ throw new DeathOracle.UnsupportedClosure("Excluded source member: /p/Other.cs:Winged.set"); }}'
        with self.assertRaisesRegex(ValueError, "guarded"):
            promote(guard, 'public bool Winged { get; private set; }', "Source.cs")

    def test_auto_property_promotion_keeps_original_accessors(self):
        guard = 'public bool Winged { get{ throw new DeathOracle.UnsupportedClosure("Excluded source member: /p/Source.cs:Winged.get"); }private set{ throw new DeathOracle.UnsupportedClosure("Excluded source member: /p/Source.cs:Winged.set"); }}'
        original = 'public bool Winged { get; private set; }'
        self.assertEqual(promote(guard, original, "Source.cs"), original)


class NumericObservationComparisonTests(unittest.TestCase):
    def test_integer_counters_reject_nearby_float_values_parameterized(self):
        for expected, actual in ((57499770, 57499769.0), (57499770, 57499771.0),
                                 (16777216, 16777217.0), (2 ** 40, float(2 ** 40 + 1))):
            with self.subTest(expected=expected, actual=actual), self.assertRaises(ValueError):
                same(expected, actual, "counter")

    def test_integer_wire_form_rejects_equal_float(self):
        with self.assertRaises(ValueError):
            same(57499770, 57499770.0, "counter")

    def test_float_wire_form_rejects_equal_integer(self):
        with self.assertRaises(ValueError):
            same(1.0, 1, "observation")

    def test_boolean_numeric_type_coercion_is_rejected_parameterized(self):
        for expected, actual in ((True, 1), (False, 0), (1, True), (0, False),
                                 (True, 1.0), (False, 0.0), (1.0, True), (0.0, False)):
            with self.subTest(expected=expected, actual=actual), self.assertRaises(ValueError):
                same(expected, actual, "observation")

    def test_integer_counter_changes_remain_exact_parameterized(self):
        for expected in (0, 57499770, 2 ** 40, 2 ** 63 - 2):
            with self.subTest(expected=expected), self.assertRaises(ValueError):
                same(expected, expected + 1, "counter")

    def test_equal_large_integer_counters_are_accepted_parameterized(self):
        for value in (57499770, 2 ** 40, 2 ** 63 - 1):
            with self.subTest(value=value):
                same(value, value, "counter")

    def test_equivalent_float32_decimal_forms_are_accepted(self):
        same(0.1, 0.10000000149011612, "observation")

    def test_different_float32_bits_are_rejected_parameterized(self):
        for expected, actual in ((0.1, 0.10000001), (-0.0, 0.0)):
            with self.subTest(expected=expected, actual=actual), self.assertRaises(ValueError):
                same(expected, actual, "observation")


class SourceTransitionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[2] / ".audit/native-room-transition/source-contract-01"
        for attribute, name in (("rows", "frozen-source-02"), ("replay", "frozen-replay-02")):
            path = root / name / "trace.jsonl"
            if not path.exists():
                raise unittest.SkipTest("Private executed original-source transition pair is unavailable")
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != "10dd86fba9c9fc5232abb41653e1825bb1c505e81515088c1b5b1fdf9293d594":
                raise ValueError("Pinned executed original-source transition trace changed: " + name)
            setattr(cls, attribute, [json.loads(line) for line in data.splitlines()])

    def test_pinned_fresh_source_recordings_match_all_records(self):
        self.assertEqual(compare(self.rows, self.replay)["compared_records"], 7915)

    def test_reviewer_mixed_type_session_clock_corruption_is_rejected(self):
        changed = self.rows.copy()
        index = next(index for index, row in enumerate(changed)
                     if row.get("event") == "phase" and row["tick"] == 380 and row["phase"] == "after-frame")
        self.assertEqual(changed[index]["state"]["sessionTime"], 57499770)
        changed[index] = copy.deepcopy(changed[index])
        changed[index]["state"]["sessionTime"] = 57499769.0
        with self.assertRaises(ValueError):
            compare(self.rows, changed)

    def test_other_integral_and_boolean_observations_reject_wire_coercion_parameterized(self):
        index = next(index for index, row in enumerate(self.rows)
                     if row.get("event") == "phase" and row["tick"] == 380 and row["phase"] == "after-frame")
        for field in ("saveTime", "FrameCounter", "saveJumps", "state", "Dead", "sameTrackedPlayer"):
            with self.subTest(field=field):
                changed = self.rows.copy()
                changed[index] = copy.deepcopy(changed[index])
                value = changed[index]["state"][field]
                self.assertIn(type(value), (int, bool))
                changed[index]["state"][field] = int(value) if type(value) is bool else float(value)
                with self.assertRaises(ValueError):
                    compare(self.rows, changed)

    def test_original_source_route_reaches_landing_and_resumed_jump(self):
        summary = validate(self.rows)
        self.assertEqual(summary["frames"], 514)
        self.assertEqual(summary["request_tick"], 373)
        self.assertEqual(summary["commit_tick"], 374)
        self.assertEqual(summary["completion_tick"], 413)
        self.assertEqual(summary["landing_tick"], 448)
        self.assertEqual(summary["control_tick"], 468)

    def test_incomplete_coroutine_cannot_establish_transition_closure(self):
        with self.assertRaises(ValueError):
            validate([row for row in self.rows if row.get("tick", -1) < 400])

    def test_boundary_cannot_be_relabelled_as_completion(self):
        with self.assertRaises(ValueError):
            validate(self.rows + [{"event": "boundary", "status": "unsupported"}])

    def test_replay_contract_rejects_observable_mutations_parameterized(self):
        mutations = [
            (373, "before-eof", "Transitioning", True),
            (374, "before-eof", "player", "Player#recreated"),
            (374, "before-eof", "sprite", "Sprite#recreated"),
            (374, "before-eof", "hair", "Hair#recreated"),
            (380, "after-frame", "sessionTime", 0),
            (380, "after-frame", "roomDeaths", 7),
            (380, "after-frame", "sessionDeaths", 1),
            (380, "after-frame", "camera", [0, 0]),
            (380, "after-frame", "position", [276, -99]),
            (414, "after-frame", "nativeAttempts", 1),
        ]
        for tick, phase, field, value in mutations:
            with self.subTest(tick=tick, phase=phase, field=field):
                changed = self.rows.copy()
                index = next(index for index, row in enumerate(changed)
                             if row.get("event") == "phase" and row["tick"] == tick and row["phase"] == phase)
                changed[index] = copy.deepcopy(changed[index])
                changed[index]["state"][field] = value
                with self.assertRaises(ValueError):
                    compare(self.rows, changed)

    def test_outgoing_entity_leak_is_rejected(self):
        changed = self.rows.copy()
        source = next(row for row in self.rows if row.get("event") == "phase" and row["tick"] == 372)
        index = next(index for index, row in enumerate(changed)
                     if row.get("event") == "phase" and row["tick"] == 414)
        changed[index] = copy.deepcopy(changed[index])
        changed[index]["state"]["entities"].append(copy.deepcopy(next(entity for entity in source["state"]["entities"] if entity["type"] == "Spikes")))
        with self.assertRaises(ValueError):
            compare(self.rows, changed)

    def test_wrong_transition_tag_filter_is_rejected(self):
        changed = self.rows.copy()
        index = next(index for index, row in enumerate(changed)
                     if row.get("event") == "phase" and row["tick"] == 380)
        changed[index] = copy.deepcopy(changed[index])
        berry = next(entity for entity in changed[index]["state"]["entities"] if entity["type"] == "Strawberry")
        berry["strawberryWobble"] = 1
        with self.assertRaises(ValueError):
            compare(self.rows, changed)


if __name__ == "__main__":
    unittest.main()
