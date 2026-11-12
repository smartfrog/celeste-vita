import copy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from compare_native_player_draw import compare_block, logical_frames, player_blocks, same_value, verified_frames
from prepare_static_tilemap import INPUT_SHA, MAP_SHA


class PlayerDrawComparisonTests(unittest.TestCase):
    def setUp(self):
        self.frames = [{"name": "synthetic", "native": [0, 1, 1, 8, 7, 1, 0, 10, 10], "sheet": "syntheticSheet",
                        "dimensions": [64, 64], "sourceRectangle": [12, 20, 8, 7]}]
        command = {"index": 0, "frame": 0, "frameName": "synthetic", "nativeFrame": self.frames[0]["native"],
                   "owner": 17, "componentType": "PlayerHair", "position": [20, -4], "origin": [4, 5],
                   "scale": [-1, 1], "rotation": 0, "color": [0, 0, 0, 255],
                   **{key: self.frames[0][key] for key in ("sheet", "dimensions", "sourceRectangle")}}
        self.native = {"player": 17, "renderCalls": 1, "commands": [command, {**copy.deepcopy(command), "index": 1, "position": [22, -4]}]}
        self.source = {"commands": [{**copy.deepcopy(row), "owner": {"entity": "sourcePlayer", "componentType": "PlayerHair"}, "effects": "None"}
                                    for row in self.native["commands"]]}

    def compare(self):
        return compare_block(375, self.source, self.native, self.frames)

    def test_matching_logical_commands(self):
        self.assertEqual(self.compare(), 2)

    def test_missing_command_rejected(self):
        self.native["commands"].pop()
        with self.assertRaisesRegex(ValueError, "count"):
            self.compare()

    def test_duplicate_command_rejected(self):
        self.native["commands"].append(copy.deepcopy(self.native["commands"][0]))
        with self.assertRaisesRegex(ValueError, "count"):
            self.compare()

    def test_swapped_command_rejected(self):
        self.native["commands"].reverse()
        with self.assertRaisesRegex(ValueError, "order"):
            self.compare()

    def test_reindexed_swapped_command_rejected(self):
        self.native["commands"].reverse()
        for index, command in enumerate(self.native["commands"]):
            command["index"] = index
        with self.assertRaisesRegex(ValueError, "position"):
            self.compare()

    def test_owner_tampering_rejected(self):
        self.native["commands"][0]["owner"] = 18
        with self.assertRaisesRegex(ValueError, "owner"):
            self.compare()

    def test_alias_tampering_rejected(self):
        self.native["commands"][0]["frameName"] = "other"
        with self.assertRaisesRegex(ValueError, "alias"):
            self.compare()

    def test_trim_tampering_rejected(self):
        self.native["commands"][0]["nativeFrame"] = [0, 1, 1, 8, 7, 2, 0, 10, 10]
        with self.assertRaisesRegex(ValueError, "trim"):
            self.compare()

    def test_logical_rectangle_tampering_rejected(self):
        self.native["commands"][0]["sourceRectangle"] = [13, 20, 8, 7]
        with self.assertRaisesRegex(ValueError, "mapping"):
            self.compare()

    def test_component_tampering_rejected(self):
        self.native["commands"][0]["componentType"] = None
        with self.assertRaisesRegex(ValueError, "attribution"):
            self.compare()

    def test_second_render_rejected(self):
        self.native["renderCalls"] = 2
        with self.assertRaisesRegex(ValueError, "one real"):
            self.compare()

    def test_json_roundtrip_compares_float32_not_decimal_spelling(self):
        self.assertTrue(same_value(0.15757864713668823, 0.15757865))

    def test_single_float32_ulp_difference_rejected(self):
        self.assertFalse(same_value(1, 1.0000001192092896))

    def test_boolean_cannot_counterfeit_float(self):
        self.assertFalse(same_value(True, 1))

    def test_native_trim_must_match_independent_atlas(self):
        text = f"CSPP1\n{INPUT_SHA}\n{MAP_SHA}\n1\n00000000\n1\nsynthetic 0 1 1 8 7 2 0 10 10 0 0 0 1\n"
        with self.assertRaisesRegex(ValueError, "alias/trim"):
            logical_frames(text, {"synthetic": ["sheet", 12, 20, 8, 7, -1, 0, 10, 10]}, {"sheet": [64, 64]})


class ExtendedPlayerMetadataTests(unittest.TestCase):
    def setUp(self):
        self.metadata = Path("/private/player/player.txt")
        self.provenance = self.metadata.parent / "provenance.json"
        self.pins = {"bank_sha256": "b723a5d340eaa3f6d875b63720fad2f67f64ee7e86fbc1d51f09532df5bbf8ab",
                     "source_manifest_sha256": "2b1fdb382861414a5ece5a92a61c124f20d14ced4a9d62023f1381d1790543f7",
                     "sweat_animation_extension": True}

    def verify(self):
        import json
        with patch.object(Path, "read_text", return_value=json.dumps(self.pins)):
            return verified_frames(self.metadata, Path("atlas"), Path("sheets"), self.provenance)

    def test_extended_bank_cannot_replace_the_pinned_body_bank(self):
        self.pins["bank_sha256"] = "untrusted"
        with self.assertRaisesRegex(ValueError, "body bank"):
            self.verify()

    def test_extended_bank_cannot_replace_the_original_source_manifest(self):
        self.pins["source_manifest_sha256"] = "untrusted"
        with self.assertRaisesRegex(ValueError, "source manifest"):
            self.verify()

    def test_extension_must_be_explicitly_declared(self):
        self.pins["sweat_animation_extension"] = False
        with self.assertRaisesRegex(ValueError, "Sweat extension"):
            self.verify()

    def test_provenance_must_belong_to_the_metadata_directory(self):
        self.provenance = Path("/other/provenance.json")
        with self.assertRaisesRegex(ValueError, "metadata directory"):
            self.verify()

class NativePlayerDrawEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.environ.get("CELESTE_PLAYER_DRAW_NATIVE_TRACE")
        if not path:
            raise unittest.SkipTest("Set CELESTE_PLAYER_DRAW_NATIVE_TRACE to a fresh native Player command run")
        cls.blocks = player_blocks(Path(path), native=True)
        root = Path("/home/fred/projects/celeste-vita-worktrees/native-room-transition-vita/.audit/native-room-transition-vita"
                    "/gameplay-draw-profile-01/clean-commit-a2af9d05b662")
        cls.source = player_blocks(root / "source-run-a/trace.jsonl")
        provenance = os.environ.get("CELESTE_PLAYER_DRAW_PROVENANCE")
        cls.frames = verified_frames(
            Path(os.environ.get("CELESTE_PLAYER_DRAW_METADATA", "/home/fred/projects/celeste-vita-worktrees/native-dash-visual-feedback/.audit/native-dash-visual-feedback"
                 "/staging-probe-state-05/assets/native-room/player.txt")),
            Path("/home/fred/projects/celeste-vita/.audit/native-player-presentation/correction-preflight/source/Gameplay.meta"),
            root / "profile-01/sheets.json", Path(provenance) if provenance else None)

    def test_native_trace_contains_all_player_blocks(self):
        self.assertEqual(sorted(self.blocks), list(range(514)))
        for tick in (375, 513):
            self.assertEqual(len(self.blocks[tick]["commands"]), 22)

    def test_tick375_all_logical_commands_match(self):
        self.assertEqual(compare_block(375, self.source[375], self.blocks[375], self.frames), 22)

    def test_tick513_all_logical_commands_match(self):
        self.assertEqual(compare_block(513, self.source[513], self.blocks[513], self.frames), 22)

    @unittest.skipUnless(os.environ.get("CELESTE_PLAYER_DRAW_PROVENANCE"), "Full Sweat comparison requires the verified extended bank")
    def test_all514_player_blocks_match_every_source_command(self):
        self.assertEqual(sum(compare_block(tick, self.source[tick], self.blocks[tick], self.frames) for tick in range(514)), 11938)


if __name__ == "__main__":
    unittest.main()
