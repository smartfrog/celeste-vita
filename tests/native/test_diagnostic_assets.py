import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from stage_native_room import checksum, hazard_text, verified_bytes
from prepare_static_tilemap import INPUT_SHA, MAP_SHA


class DiagnosticAssetTests(unittest.TestCase):
    def test_checksum_matches_runtime_known_vector(self):
        self.assertEqual(checksum(b"hello"), 0x4f9f2cab)

    def test_hazard_conversion_is_canonical_and_preserves_order(self):
        hazards = [{"direction": "left", "x": -8, "y": 0, "size": 16},
                   {"direction": "up", "x": 8, "y": 24, "size": 8}]
        self.assertEqual(hazard_text(hazards), f"CSH1\n{INPUT_SHA}\n{MAP_SHA}\n2\nleft -8 0 16\nup 8 24 8\n")

    def test_conversion_rejects_invalid_data_parameterized(self):
        for change in ({"direction": "down"}, {"size": 0}, {"x": True}, {"y": 1_000_001}):
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    hazard_text([{"direction": "up", "x": 0, "y": 0, "size": 8} | change])

    def test_provenance_rejects_content_corruption(self):
        directory = ROOT / ".audit/native-room-vita/test-assets"
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory) as temporary:
            path = Path(temporary) / "synthetic"
            path.write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "provenance mismatch"):
                verified_bytes(path, hashlib.sha256(b"expected").hexdigest())

    def test_missing_asset_propagates_io_error(self):
        with self.assertRaises(FileNotFoundError):
            verified_bytes(ROOT / ".audit/native-room-vita/nonexistent-asset", "0"*64)
