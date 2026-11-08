import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from check_player_runtime_reuse import normalized_revision, require_equal, resident_sections


class RuntimeReuseProofTests(unittest.TestCase):
    def test_only_declared_revision_text_is_normalized(self):
        self.assertEqual(normalized_revision(b"code old-revision other-data", "old-revision"), b"code <REVISION> other-data")

    def test_changed_runtime_bytes_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "differs"):
            require_equal(b"old-code", b"new-code", "runtime")

    def test_equal_asset_bytes_are_hash_recorded(self):
        result = require_equal(b"synthetic-owned-asset", b"synthetic-owned-asset", "asset")
        self.assertEqual(result["baseline_sha256"], result["current_sha256"])
        self.assertTrue(result["equal"])

    def test_non_elf_resident_image_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "not-elf"
            path.write_bytes(b"not an executable")
            with self.assertRaisesRegex(ValueError, "ELF32"):
                resident_sections(path, "revision")


if __name__ == "__main__":
    unittest.main()
