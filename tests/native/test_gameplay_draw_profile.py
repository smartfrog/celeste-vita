import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from run_room_transition_probe import execution_namespace
from native_room_revision import canonical_digest


class GameplayDrawNamespaceTests(unittest.TestCase):
    def test_gameplay_draw_requires_a_verified_profile_before_selecting_namespace(self):
        with self.assertRaisesRegex(ValueError, "profile path is required"):
            execution_namespace({"kind": "native-room-transition-gameplay-draw-v1"})

    def test_removing_kind_cannot_downgrade_a_bound_profile_to_the_legacy_namespace(self):
        with self.assertRaisesRegex(ValueError, "profile kind is required"):
            execution_namespace({"binding": "0" * 64})


class GameplayDrawBindingTests(unittest.TestCase):
    def record(self):
        from prepare_gameplay_draw_profile import KIND, ROOMS_ID, DRIVER_ID
        record = {"schema": 1, "kind": KIND, "rooms": ROOMS_ID, "terrain_driver": DRIVER_ID,
                  "claim": "Original GameplayRenderer commands only; not full Level rendergraph, GPU, pixels or Vita"}
        record["binding"] = canonical_digest(record)
        return record

    def test_distinct_profile_kind_and_binding_are_accepted(self):
        from prepare_gameplay_draw_profile import validate_profile
        validate_profile(self.record())

    def test_cpu_profile_cannot_claim_gameplay_draw(self):
        from prepare_gameplay_draw_profile import validate_profile
        record = self.record()
        record["kind"] = "native-room-transition-full-bake-source-cpu-v1"
        with self.assertRaisesRegex(ValueError, "profile kind"):
            validate_profile(record)

    def test_boolean_schema_is_not_a_profile_version(self):
        from prepare_gameplay_draw_profile import validate_profile
        record = self.record()
        record["schema"] = True
        with self.assertRaisesRegex(ValueError, "kind/version"):
            validate_profile(record)

    def test_rebound_stripped_rooms_are_rejected(self):
        from prepare_gameplay_draw_profile import validate_profile
        record = self.record()
        record["rooms"] = {"bytes": 0, "sha256": "0" * 64}
        record["binding"] = canonical_digest({key: value for key, value in record.items() if key != "binding"})
        with self.assertRaisesRegex(ValueError, "authored rooms"):
            validate_profile(record)

    def test_unbound_input_change_is_rejected(self):
        from prepare_gameplay_draw_profile import validate_profile
        record = self.record()
        record["inputs"] = {"invented": {"bytes": 0, "sha256": "0" * 64}}
        with self.assertRaisesRegex(ValueError, "binding"):
            validate_profile(record)

    def test_rebound_full_level_claim_is_rejected(self):
        from prepare_gameplay_draw_profile import validate_profile
        record = self.record()
        record["claim"] = "full Level and GPU closure"
        record["binding"] = canonical_digest({key: value for key, value in record.items() if key != "binding"})
        with self.assertRaisesRegex(ValueError, "scope"):
            validate_profile(record)

    def test_invalid_binding_is_rejected_before_execution_output_creation(self):
        from prepare_gameplay_draw_profile import AUDIT
        from run_room_transition_probe import run
        AUDIT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=AUDIT) as scratch:
            profile = Path(scratch) / "profile"
            profile.mkdir()
            record = self.record()
            record["binding"] = "0" * 64
            (profile / "transition-profile.json").write_text(json.dumps(record))
            output = Path(scratch) / "execution"
            with self.assertRaisesRegex(ValueError, "binding"):
                run(profile, Path("/unused/sdk"), Path("/unused/content"), Path("/unused/controls"), output)
            self.assertFalse(output.exists())


class AuthoredRoomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from prepare_gameplay_draw_profile import authored_rooms, DEFAULT_ARCHIVE
        if not DEFAULT_ARCHIVE.exists():
            raise unittest.SkipTest("Pinned private map unavailable")
        cls.rooms, cls.contract = authored_rooms(DEFAULT_ARCHIVE)

    def test_both_authored_layers_are_retained_in_source_order(self):
        from prepare_gameplay_draw_profile import ROOMS_ID, room_contract
        self.assertEqual(room_contract(self.rooms), self.contract)
        self.assertEqual([room["attributes"]["name"] for room in self.rooms], ["lvl_1", "lvl_2"])
        self.assertEqual([(r["fg"], r["bg"], r["static"], r["banners"]) for r in self.contract],
                         [(4, 25, 22, 7), (5, 18, 19, 4)])
        from hashlib import sha256
        encoded = (json.dumps(self.rooms, sort_keys=True) + "\n").encode()
        self.assertEqual({"bytes": len(encoded), "sha256": sha256(encoded).hexdigest()}, ROOMS_ID)

    def test_authored_empty_object_layer_is_not_a_missing_layer(self):
        from prepare_gameplay_draw_profile import room_contract
        rooms = copy.deepcopy(self.rooms)
        rooms[0]["children"] = [layer for layer in rooms[0]["children"] if layer["name"] != "objtiles"]
        with self.assertRaisesRegex(ValueError, "authored room"):
            room_contract(rooms)

    def test_reordered_decal_is_rejected_even_when_counts_match(self):
        from prepare_gameplay_draw_profile import room_contract
        rooms = copy.deepcopy(self.rooms)
        layer = next(layer for layer in rooms[0]["children"] if layer["name"] == "bgdecals")
        layer["children"].reverse()
        with self.assertRaisesRegex(ValueError, "authored room"):
            room_contract(rooms)

    def test_nonempty_object_csv_is_rejected(self):
        from prepare_gameplay_draw_profile import room_contract
        rooms = copy.deepcopy(self.rooms)
        next(layer for layer in rooms[0]["children"] if layer["name"] == "objtiles")["attributes"]["innerText"] = "1"
        with self.assertRaisesRegex(ValueError, "authored room"):
            room_contract(rooms)


class DrawFrameValidationTests(unittest.TestCase):
    def frame(self):
        roster = {"cameraAlias": True, "cameraViewport": [320, 180], "live": [
            {"entity": "outgoing", "depth": 9000, "actualDepth": 8999.5, "Visible": True, "hudExcluded": False},
            {"entity": "hidden", "depth": 0, "actualDepth": 0, "Visible": False, "hudExcluded": False},
            {"entity": "hud", "depth": -1, "actualDepth": -1, "Visible": True, "hudExcluded": True}]}
        command = {"index": 0, "owner": {"entity": "outgoing", "depth": 9000, "actualDepth": 8999.5},
                   "sheet": "Gameplay0", "dimensions": [4096, 4096], "sourceRectangle": [0, 0, 8, 0],
                   "finiteGeometry": False, "verticesFloat32Bits": [[-4194304, -4194304, 0, 0, 0]] * 4,
                   "clipping": "atlas source rectangle; GPU scissor not observed"}
        dispatch = {"commands": 1, "entities": [{"entity": "outgoing", "drawStart": 0, "drawEnd": 1}],
                    "batches": [{"SortMode": "Deferred", "HasEffect": False, "DrawStart": 0, "DrawEnd": 1, "Matrix": [1] * 16}]}
        return roster, dispatch, [command]

    def test_original_visible_outgoing_entity_and_degenerate_draw_are_not_omitted(self):
        from compare_gameplay_draw_contract import validate_frame
        validate_frame(*self.frame())

    def test_missing_outgoing_dispatch_is_rejected(self):
        from compare_gameplay_draw_contract import validate_frame
        roster, dispatch, commands = self.frame()
        dispatch["entities"] = []
        with self.assertRaisesRegex(ValueError, "live SOURCE roster"):
            validate_frame(roster, dispatch, commands)

    def test_invented_owner_is_rejected(self):
        from compare_gameplay_draw_contract import validate_frame
        roster, dispatch, commands = self.frame()
        commands[0]["owner"]["entity"] = "invented"
        with self.assertRaisesRegex(ValueError, "owner"):
            validate_frame(roster, dispatch, commands)

    def test_effect_submission_cannot_claim_command_coverage(self):
        from compare_gameplay_draw_contract import validate_frame
        roster, dispatch, commands = self.frame()
        dispatch["batches"][0]["HasEffect"] = True
        with self.assertRaisesRegex(ValueError, "batch"):
            validate_frame(roster, dispatch, commands)

    def test_independent_camera_cannot_claim_original_renderer_alias(self):
        from compare_gameplay_draw_contract import validate_frame
        roster, dispatch, commands = self.frame()
        roster["cameraAlias"] = False
        with self.assertRaisesRegex(ValueError, "camera alias"):
            validate_frame(roster, dispatch, commands)

    def test_submission_order_is_not_reconstructed_from_depth(self):
        from compare_gameplay_draw_contract import validate_frame
        roster, dispatch, commands = self.frame()
        roster["live"].append({"entity": "next", "depth": 0, "actualDepth": 0, "Visible": True, "hudExcluded": False})
        dispatch["entities"].insert(0, {"entity": "next", "drawStart": 0, "drawEnd": 0})
        with self.assertRaisesRegex(ValueError, "live SOURCE roster"):
            validate_frame(roster, dispatch, commands)

    def test_non_deferred_batch_is_rejected(self):
        from compare_gameplay_draw_contract import validate_frame
        roster, dispatch, commands = self.frame()
        dispatch["batches"][0]["SortMode"] = "Texture"
        with self.assertRaisesRegex(ValueError, "batch"):
            validate_frame(roster, dispatch, commands)

    def test_fabricated_sheet_dimensions_are_rejected(self):
        from compare_gameplay_draw_contract import validate_frame
        roster, dispatch, commands = self.frame()
        commands[0]["dimensions"] = [2048, 2048]
        with self.assertRaisesRegex(ValueError, "original sheet headers"):
            validate_frame(roster, dispatch, commands, {"Gameplay0": [4096, 4096]})

    def test_nonfinite_geometry_cannot_be_claimed_finite(self):
        from compare_gameplay_draw_contract import validate_frame
        roster, dispatch, commands = self.frame()
        commands[0]["finiteGeometry"] = True
        with self.assertRaisesRegex(ValueError, "nonfinite geometry"):
            validate_frame(roster, dispatch, commands)


if __name__ == "__main__":
    unittest.main()
