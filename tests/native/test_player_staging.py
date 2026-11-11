import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import stage_native_room as staging
from native_player_assets import player_metadata


class PlayerStagingTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / ".audit/native-player-death-respawn/artifact-tests"
        parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.player = self.root / "player"
        self.oracle = self.root / "oracle"
        self.player.mkdir()
        self.oracle.mkdir()
        self.bank = {"animations": [{"id": "idle", "delay": 0.1, "next": "idle", "frames": ["source-frame"]}],
                     "frames": [{"name": "source-frame", "rectangle": [0,0,1,1], "trim": [0,0], "size": [32,32],
                                 "hairOffset": [0,0], "hairFrame": 0, "hasHair": True}],
                     "bangs": ["source-frame"]*3, "hair": "source-frame"}
        self.layout = {"source-frame": [0,1,1]}
        (self.oracle / "bank.json").write_text(json.dumps(self.bank))
        (self.oracle / "source-manifest.json").write_text("{}")
        (self.player / "bank.json").write_text(json.dumps(self.bank, indent=2))
        (self.player / "player0.rgba").write_bytes(bytes(32768))
        (self.player / "player.txt").write_text(player_metadata(self.bank, self.layout, [staging.checksum(bytes(32768))]))
        self.provenance = {"pages": 1, "submitted_player_rgba_bytes": 32768,
                           "source_oracle": str(self.oracle), "death_animation_extension": False, "layout": self.layout,
                           "source_manifest_sha256": self.digest(self.oracle / "source-manifest.json"),
                           "bank_sha256": self.digest(self.oracle / "bank.json"),
                           "files": {p.name: self.digest(p) for p in self.player.iterdir()}}
        (self.player / "provenance.json").write_text(json.dumps(self.provenance))

    def digest(self, path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def check(self):
        return staging.verified_player_files(self.player, self.provenance)

    def test_bank_is_verified_evidence_not_a_packaged_payload(self):
        self.assertEqual(set(self.check()), {"player.txt", "player0.rgba"})

    def test_legacy_payload_only_provenance_remains_supported(self):
        (self.player / "bank.json").unlink()
        self.provenance["files"].pop("bank.json")
        self.assertEqual(set(self.check()), {"player.txt", "player0.rgba"})

    def test_explicit_payload_and_evidence_roles_are_checked(self):
        self.provenance.update(payload_files=["player.txt", "player0.rgba"], evidence_files=["bank.json"])
        self.assertEqual(set(self.check()), {"player.txt", "player0.rgba"})

    def test_bank_cannot_be_declared_as_payload(self):
        self.provenance.update(payload_files=["player.txt", "player0.rgba", "bank.json"], evidence_files=[])
        with self.assertRaisesRegex(ValueError, "role"):
            self.check()

    def test_unknown_pinned_file_is_rejected(self):
        (self.player / "extra.bin").write_bytes(b"unexpected")
        self.provenance["files"]["extra.bin"] = self.digest(self.player / "extra.bin")
        with self.assertRaisesRegex(ValueError, "asset set"):
            self.check()

    def test_unknown_unpinned_file_is_rejected(self):
        (self.player / "extra.bin").write_bytes(b"unexpected")
        with self.assertRaisesRegex(ValueError, "inventory"):
            self.check()

    def test_bank_evidence_without_its_pin_is_rejected(self):
        self.provenance["files"].pop("bank.json")
        with self.assertRaisesRegex(ValueError, "inventory"):
            self.check()

    def test_rehashed_but_wrong_bank_is_not_accepted_as_source_evidence(self):
        (self.player / "bank.json").write_text('{"animations": [], "frames": []}')
        self.provenance["files"]["bank.json"] = self.digest(self.player / "bank.json")
        with self.assertRaisesRegex(ValueError, "source.*bank|bank.*source"):
            self.check()

    def test_changed_source_oracle_bank_is_rejected(self):
        (self.oracle / "bank.json").write_text('{"changed": true}')
        with self.assertRaisesRegex(ValueError, "provenance mismatch"):
            self.check()

    def test_missing_original_bank_pin_is_rejected(self):
        self.provenance.pop("bank_sha256")
        with self.assertRaisesRegex(ValueError, "pins are required"):
            self.check()

    def test_changed_payload_is_rejected(self):
        (self.player / "player0.rgba").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "provenance mismatch"):
            self.check()

    def test_rehashed_short_page_is_rejected(self):
        path = self.player / "player0.rgba"
        path.write_bytes(b"short page")
        self.provenance["files"][path.name] = self.digest(path)
        metadata = self.player / "player.txt"
        metadata.write_text(player_metadata(self.bank, self.layout, [staging.checksum(path.read_bytes())]))
        self.provenance["files"][metadata.name] = self.digest(metadata)
        with self.assertRaisesRegex(ValueError, "page size"):
            self.check()

    def test_death_extension_cannot_use_edited_payload_only_provenance(self):
        self.provenance["death_animation_extension"] = True
        self.provenance["files"].pop("bank.json")
        (self.player / "bank.json").unlink()
        with self.assertRaisesRegex(ValueError, "evidence pin"):
            self.check()

    def test_rehashed_metadata_still_must_match_the_original_source_bank(self):
        path = self.player / "player.txt"
        path.write_bytes(path.read_bytes().replace(b"idle ", b"wrong ", 1))
        self.provenance["files"]["player.txt"] = self.digest(path)
        with self.assertRaisesRegex(ValueError, "metadata payload"):
            self.check()


if __name__ == "__main__":
    unittest.main()
