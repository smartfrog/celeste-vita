from pathlib import Path
import copy
import hashlib
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from native_room_build import build_capture_policy
from prepare_dash_trail_oracle import replace_guard, replace_once
from compare_dash_trails import compare


class DashTrailContractTests(unittest.TestCase):
    def test_original_member_promotion_rejects_missing_guard(self):
        with self.assertRaisesRegex(ValueError, "Missing original"):
            replace_guard("", "public void Update()\n{ return; }")

    def test_original_member_promotion_rejects_ambiguous_guard(self):
        member = 'public void Update() { throw new DeathOracle.UnsupportedClosure("Excluded source member: x/Fixture.cs:Update"); }'
        with self.assertRaisesRegex(ValueError, "Missing original"):
            replace_guard(member + member, "public void Update()\n{ return; }")

    def test_profile_replacement_requires_unique_input(self):
        with self.assertRaises(ValueError):
            replace_once("xx", "x", "y")

    def test_dash_probe_has_distinct_resident_capture_binding(self):
        cache = {"CELESTE_ROOM_ANIMATED_PLAYER": "ON", "CELESTE_ROOM_DASH_PROBE": "ON"}
        self.assertEqual(build_capture_policy(cache, ["-DCELESTE_ROOM_ANIMATED_PLAYER", "-DCELESTE_ROOM_DASH_PROBE"]), "dash_trails")

    def test_dash_probe_compile_flag_drift_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "compile definition"):
            build_capture_policy({"CELESTE_ROOM_ANIMATED_PLAYER": "ON"}, ["-DCELESTE_ROOM_ANIMATED_PLAYER", "-DCELESTE_ROOM_DASH_PROBE"])

    def test_dash_probe_capture_override_is_rejected(self):
        cache = {"CELESTE_ROOM_ANIMATED_PLAYER": "ON", "CELESTE_ROOM_DASH_PROBE": "ON", "CELESTE_ROOM_CAPTURE_AFTER_CLIMB": "ON"}
        with self.assertRaisesRegex(ValueError, "own capture policy"):
            build_capture_policy(cache, ["-D" + key for key in cache])


class RepeatTrailValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        evidence = Path(__file__).resolve().parents[2] / ".audit/native-dash-visual-feedback/parity-frozen-release"
        files = {
            "source": (evidence / "repeat.source.jsonl", "be9b5b12364dbdbe16fbb57cef9c72c8733a984020f0b4de7199310624275726"),
            "native": (evidence / "repeat.native.jsonl", "c5ccc2ed00676c0f891f2fd27faba27377841776c7720cc1eb857e59441fa423"),
            "bank": (Path("/tmp/opencode/celeste-vita-death-source-up/.audit/native-player-death-respawn/native-assets-02/bank.json"),
                     "9b5083cf20e8332cafc196372b0ac9d502e964c67c7e3f15b988c1db46507301"),
        }
        if any(not path.is_file() for path, _ in files.values()):
            raise unittest.SkipTest("Pinned private repeat recordings are unavailable")
        for name, (path, digest) in files.items():
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError("Immutable repeat evidence changed: " + str(path))
            setattr(cls, name, json.loads(data) if name == "bank" else [json.loads(line) for line in data.splitlines()])

    def compare_repeat(self, native, bank=None):
        return compare(self.source, native, self.bank if bank is None else bank, "repeat")

    def capture_draw(self, native, tick, index):
        return native[tick]["captures"][0]["draws"][index]

    def test_inherited_ninety_raw_differences_remain_visible(self):
        result = self.compare_repeat(self.native)
        self.assertEqual(len(result["capture_geometry_differences"]), 90)
        self.assertEqual(len(result["inherited_hair_geometry"]), 90)

    def test_repeat_transparent_body_is_rejected_parameterized(self):
        for tick in (45, 134):
            with self.subTest(tick=tick):
                changed = copy.deepcopy(self.native)
                self.capture_draw(changed, tick, -1)["color"][3] = 0
                with self.assertRaises(ValueError):
                    self.compare_repeat(changed)

    def test_repeat_displaced_body_vertex_is_rejected_parameterized(self):
        for tick in (45, 134):
            with self.subTest(tick=tick):
                changed = copy.deepcopy(self.native)
                self.capture_draw(changed, tick, -1)["vertices"][0][0] += 16
                with self.assertRaises(ValueError):
                    self.compare_repeat(changed)

    def test_repeat_nongeometry_changes_are_rejected_parameterized(self):
        frames = {frame["name"]: frame for frame in self.bank["frames"]}
        for index in (4, -1):
            for field in ("texture", "scale", "rotation", "color", "origin"):
                with self.subTest(draw=index, field=field):
                    changed = copy.deepcopy(self.native)
                    draw = self.capture_draw(changed, 134, index)
                    bank = self.bank
                    if field == "texture":
                        bank = copy.deepcopy(self.bank)
                        replacement = {**frames[draw[field]], "name": "test/mutated_texture"}
                        bank["frames"].append(replacement)
                        draw[field] = replacement["name"]
                    elif field == "rotation":
                        draw[field] += 0.5
                    elif field == "color":
                        draw[field][0] ^= 1
                    else:
                        draw[field][0] += 1
                    with self.assertRaises(ValueError):
                        self.compare_repeat(changed, bank)

    def test_changed_inherited_hair_value_pair_is_rejected_parameterized(self):
        for tick in (134, 139, 145):
            for field in ("position", "vertices"):
                with self.subTest(tick=tick, field=field):
                    changed = copy.deepcopy(self.native)
                    draw = self.capture_draw(changed, tick, 4)
                    if field == "position":
                        draw[field][0] += 1
                    else:
                        draw[field][0][0] += 16
                    with self.assertRaises(ValueError):
                        self.compare_repeat(changed)

    def test_unrelated_hair_geometry_is_rejected_parameterized(self):
        for tick, index in ((45, 4), (134, 0)):
            with self.subTest(tick=tick, draw=index):
                changed = copy.deepcopy(self.native)
                self.capture_draw(changed, tick, index)["position"][0] += 1
                with self.assertRaises(ValueError):
                    self.compare_repeat(changed)

    def test_removing_an_inherited_difference_is_rejected(self):
        changed = copy.deepcopy(self.native)
        source_draws = [row["row"] for row in self.source if row.get("event") == "recording" and row["tick"] == 134
                        and row["row"]["operation"] == "draw" and not row["row"]["target"]]
        self.capture_draw(changed, 134, 4)["position"] = source_draws[4]["position"]
        with self.assertRaises(ValueError):
            self.compare_repeat(changed)


if __name__ == "__main__":
    unittest.main()
