import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import native_room_revision as revision


class ExactSourceStateTests(unittest.TestCase):
    def fixture(self, root):
        (root / "native.cpp").write_text("native work in progress\n")
        return patch.multiple(revision, source_state=lambda _: ("base", [" M native.cpp"]))

    def test_opt_in_verifies_exact_dirty_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.fixture(root), patch.object(revision.subprocess, "check_output", return_value=b"native.cpp\0"):
                state = revision.source_identity(root)
                self.assertEqual(revision.validate_source_state(state, root), state)
                self.assertEqual(state["paths"]["native.cpp"]["sha256"], hashlib.sha256((root / "native.cpp").read_bytes()).hexdigest())

    def test_default_still_rejects_dirty_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.fixture(root):
                with self.assertRaisesRegex(ValueError, "committed"):
                    revision.validate_source_state(root=root)

    def test_changed_bytes_fail_expected_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.fixture(root), patch.object(revision.subprocess, "check_output", return_value=b"native.cpp\0"):
                state = revision.source_identity(root)
                (root / "native.cpp").write_text("different\n")
                with self.assertRaisesRegex(ValueError, "exact source"):
                    revision.validate_source_state(state, root)

    def test_unknown_untracked_source_fails_expected_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.fixture(root), patch.object(revision.subprocess, "check_output", return_value=b"native.cpp\0") as files:
                state = revision.source_identity(root)
                (root / "unknown.cpp").write_text("unknown\n")
                files.return_value = b"native.cpp\0unknown.cpp\0"
                with self.assertRaisesRegex(ValueError, "exact source"):
                    revision.validate_source_state(state, root)

    def test_changed_base_fails_expected_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.fixture(root), patch.object(revision.subprocess, "check_output", return_value=b"native.cpp\0"):
                state = revision.source_identity(root)
                state["base_head"] = "different"
                with self.assertRaisesRegex(ValueError, "exact source"):
                    revision.validate_source_state(state, root)

    def test_identical_bytes_at_relocated_path_fail_expected_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "before/kernel.cpp"
            relocated = root / "after/kernel.cpp"
            original.parent.mkdir()
            original.write_text("unchanged kernel\n")
            with patch.object(revision, "source_state", return_value=("base", [])), \
                 patch.object(revision.subprocess, "check_output", return_value=b"before/kernel.cpp\0") as files:
                state = revision.source_identity(root)
                relocated.parent.mkdir()
                original.rename(relocated)
                files.return_value = b"after/kernel.cpp\0"
                with self.assertRaisesRegex(ValueError, "exact source"):
                    revision.validate_source_state(state, root)


if __name__ == "__main__":
    unittest.main()
