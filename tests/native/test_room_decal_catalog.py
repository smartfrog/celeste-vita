"""Private authored metadata and full native owner coverage; no command/GPU parity."""
import hashlib
import copy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from test_native_gameplay_draw_projection import (
    FRAMES, SOURCE_IDENTITY, SOURCE_TRACE, canonical_root, file_identity,
    load_native, native_keys, sample_source, source_keys, source_entries, compare_tick,
)

EVIDENCE = canonical_root() / ".audit/native-room2-decal-ownership-01"
ARCHIVE = canonical_root() / ".audit/private-push-20261111/committed-preparation/game.zip"
DECAL_SOURCE = canonical_root() / ".audit/native-first-room-decals/source-discovery-f4/il/Celeste.Decal.cs"
METADATA_IDENTITY = {"bytes": 2556, "sha256": "1eb4bcb699363754df20ddf9b6f7b21738401cddf53e961755127f3ba5fda350"}


class AuthoredMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from prepare_gameplay_draw_profile import authored_rooms
        if not ARCHIVE.exists() or not DECAL_SOURCE.exists():
            raise unittest.SkipTest("Pinned private authored metadata inputs unavailable")
        cls.rooms, _ = authored_rooms(ARCHIVE)
        cls.source = DECAL_SOURCE.read_bytes()

    def test_metadata_is_deterministically_bound_to_both_original_rooms(self):
        from prepare_authored_decal_catalog import encode_catalog
        data = encode_catalog(self.rooms, self.source)
        self.assertEqual({"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}, METADATA_IDENTITY)

    def test_original_banner_classification_covers_room2_not_all_static(self):
        from prepare_authored_decal_catalog import banner_names, banner_texture
        names = banner_names(self.source)
        for room, expected in zip(self.rooms, ((22, 7), (19, 4))):
            decals = [decal for layer in room["children"] if layer["name"] in ("bgdecals", "fgdecals")
                      for decal in layer["children"]]
            banners = sum(banner_texture(decal["attributes"]["texture"], names) for decal in decals)
            self.assertEqual((len(decals) - banners, banners), expected)

    def test_changed_original_source_is_rejected(self):
        from prepare_authored_decal_catalog import encode_catalog
        with self.assertRaisesRegex(ValueError, "original Decal source"):
            encode_catalog(self.rooms, self.source + b"\n")

    def test_reordered_authored_layer_is_rejected(self):
        from prepare_authored_decal_catalog import encode_catalog
        rooms = copy.deepcopy(self.rooms)
        next(layer for layer in rooms[1]["children"] if layer["name"] == "bgdecals")["children"].reverse()
        with self.assertRaisesRegex(ValueError, "authored room"):
            encode_catalog(rooms, self.source)

    def test_changed_map_is_rejected_before_output_creation(self):
        from prepare_authored_decal_catalog import prepare
        output = EVIDENCE / "must-not-create-tampered-map/catalog.txt"
        archive = MagicMock()
        archive.__enter__.return_value.read.return_value = b"changed original map"
        with patch("prepare_gameplay_draw_profile.zipfile.ZipFile", return_value=archive):
            with self.assertRaisesRegex(ValueError, "original map member"):
                prepare(ARCHIVE, DECAL_SOURCE, output)
        self.assertFalse(output.parent.exists())

    def test_existing_metadata_cannot_be_overwritten(self):
        from prepare_authored_decal_catalog import prepare
        with patch.object(Path, "exists", return_value=True):
            with self.assertRaisesRegex(ValueError, "fresh"):
                prepare(ARCHIVE, DECAL_SOURCE, EVIDENCE / "existing-metadata.txt")

    def test_output_cannot_enter_the_public_worktree(self):
        from prepare_authored_decal_catalog import prepare
        with self.assertRaisesRegex(ValueError, "private audit namespace"):
            prepare(ARCHIVE, DECAL_SOURCE, ROOT / "catalog.txt")


class FullAuthoredProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        override = os.environ.get("CELESTE_NATIVE_DRAW_CATALOG_TRACE")
        if override:
            native = Path(override)
            expected = os.environ["CELESTE_NATIVE_DRAW_CATALOG_SHA256"]
        else:
            receipt = EVIDENCE / "proof-01/receipt.json"
            if not receipt.exists():
                raise unittest.SkipTest("Private full authored native projection evidence unavailable")
            record = json.loads(receipt.read_text())
            native = receipt.parent / record["full_native_trace"]
            expected = record["outputs"][native.name]["sha256"]
        if file_identity(SOURCE_TRACE) != SOURCE_IDENTITY:
            raise ValueError("Immutable accepted SOURCE draw trace changed")
        if file_identity(native)["sha256"] != expected:
            raise ValueError("Full authored native trace changed")
        cls.source = sample_source(SOURCE_TRACE)
        cls.rosters, cls.dispatches, cls.players = load_native(native)

    def test_room2_owners_close_the_entire_source_roster(self):
        self.assertEqual(native_keys(self.rosters[375]), source_keys(375, self.source[375]))
        self.assertEqual(len(self.rosters[375]["live"]), 72)
        self.assertEqual(len(self.dispatches[375]), 71)

    def test_every_route_tick_has_complete_source_owner_order(self):
        self.assertEqual(sorted(self.rosters), list(range(FRAMES)))
        for tick in range(FRAMES):
            with self.subTest(tick=tick):
                self.assertEqual(native_keys(self.rosters[tick]), source_keys(tick, self.source[tick]))
                self.assertEqual(self.rosters[tick]["decalGapRooms"], [])

    def test_all514_full_owner_visibility_hud_dispatch_and_stable_identity_bindings(self):
        bindings, native_bindings, source_bindings = {}, {}, {}
        for tick in range(FRAMES):
            self.assertEqual(compare_tick(tick, self.source[tick], self.rosters[tick], self.dispatches[tick],
                                          self.players[tick], frozenset({"1", "2"})), [])
            for key, entry, owner in zip(source_keys(tick, self.source[tick]),
                                         source_entries(self.source[tick]), self.rosters[tick]["live"]):
                binding = (entry[0], owner["identity"])
                self.assertEqual(bindings.setdefault(key, binding), binding)
                self.assertEqual(native_bindings.setdefault(owner["identity"], key), key)
                self.assertEqual(source_bindings.setdefault(entry[0], key), key)
        self.assertEqual(sum(key[0] == "Decal" for key in bindings), 52)

    def test_native_authored_positions_and_banner_owners_match_source_all514(self):
        for tick in range(FRAMES):
            for entry, owner in zip(source_entries(self.source[tick]), self.rosters[tick]["live"]):
                if owner["kind"] != "Decal":
                    continue
                self.assertEqual(owner["position"], self.source[tick]["decals"][entry[0]]["position"])
                self.assertEqual(owner["banner"], self.source[tick]["decals"][entry[0]]["banner"])

    def test_native_original_keys_ordinals_transforms_and_namespace_match_pinned_map(self):
        from prepare_authored_decal_catalog import banner_names, banner_texture
        from prepare_gameplay_draw_profile import authored_rooms
        rooms, _ = authored_rooms(ARCHIVE)
        banners = banner_names(DECAL_SOURCE.read_bytes())
        expected = {}
        for room_index, room in enumerate(rooms, 1):
            attributes = room["attributes"]
            for layer in room["children"]:
                if layer["name"] not in ("bgdecals", "fgdecals"):
                    continue
                background = layer["name"] == "bgdecals"
                for ordinal, decal in enumerate(layer["children"]):
                    value = decal["attributes"]
                    key = ("Decal", attributes["name"][4:], "bg" if background else "fg", ordinal)
                    expected[key] = {"identity": 0x6000000000000000 | room_index << 32 |
                                    (1 if background else 2) << 24 | ordinal + 1,
                                     "texture": value["texture"],
                                     "position": [attributes["x"] + value["x"], attributes["y"] + value["y"]],
                                     "scale": [value["scaleX"], value["scaleY"]],
                                     "banner": banner_texture(value["texture"], banners)}
        actual = {key: {field: owner[field] for field in expected[key]}
                  for key, owner in zip(native_keys(self.rosters[375]), self.rosters[375]["live"])
                  if key[0] == "Decal"}
        self.assertEqual(actual, expected)

    def test_outgoing_room_retention_and_actual_room_load_unload_boundaries(self):
        for tick in range(FRAMES):
            rooms = [owner["room"] for owner in self.rosters[tick]["live"] if owner["kind"] == "Decal"]
            self.assertEqual(rooms.count("1"), 29 if tick < 413 else 0)
            self.assertEqual(rooms.count("2"), 23 if tick >= 374 else 0)
        for tick in (413, 513):
            self.assertFalse(any(owner["kind"] == "Entity" for owner in self.rosters[tick]["live"]))
            self.assertEqual([owner["kind"] for owner in self.rosters[tick]["live"] if owner["sortDepthBand"] == 0],
                             ["Player", "WindController"])

    def test_placement_lag_stays_distinct_from_current_depth(self):
        for tick, band in ((35, -1000000), (36, 0)):
            self.assertGreater(self.source[tick]["player_current_depth"], -0.001)
            self.assertEqual(next(owner["sortDepthBand"] for owner in self.rosters[tick]["live"]
                                  if owner["kind"] == "Player"), band)

    def test_room2_missing_owner_cannot_be_hidden_by_an_empty_gap_flag(self):
        roster = copy.deepcopy(self.rosters[375])
        roster["live"].remove(next(owner for owner in roster["live"]
                                  if owner["kind"] == "Decal" and owner["room"] == "2"))
        with self.assertRaisesRegex(ValueError, "gap must equal|chronology"):
            compare_tick(375, self.source[375], roster, self.dispatches[375], self.players[375], frozenset({"1", "2"}))


if __name__ == "__main__":
    unittest.main()
