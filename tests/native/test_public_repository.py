from pathlib import Path
import hashlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import check_public_repository
from check_public_repository import audit


class PublicRepositoryTests(unittest.TestCase):
    media_name = "docs/images/reviewed.png"
    media_bytes = b"\x89PNG\r\n\x1a\n\0synthetic documentation image"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git("init", "--quiet")

    def git(self, *arguments):
        return subprocess.run(["git", *arguments], cwd=self.root, check=True, capture_output=True, text=True)

    def write_media(self, name=None, data=None):
        path = self.root / (name or self.media_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.media_bytes if data is None else data)
        return path

    def reviewed_media(self, data=None):
        digest = hashlib.sha256(self.media_bytes if data is None else data).hexdigest()
        return patch.object(check_public_repository, "REVIEWED_MEDIA", {self.media_name: digest})

    def commit(self):
        self.git("-c", "user.name=Synthetic Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "Synthetic fixture")

    def test_reviewed_candidate_image_is_allowed(self):
        self.write_media()
        with self.reviewed_media():
            self.assertEqual(audit(self.root)["findings"], [])

    def test_reviewed_indexed_image_is_allowed(self):
        self.write_media()
        self.git("add", self.media_name)
        with self.reviewed_media():
            self.assertEqual(audit(self.root)["findings"], [])

    def test_reviewed_historical_image_is_allowed(self):
        self.write_media()
        self.git("add", self.media_name)
        self.commit()
        with self.reviewed_media():
            self.assertEqual(audit(self.root, history=True)["findings"], [])

    def test_reviewed_image_at_another_path_is_rejected(self):
        self.write_media("docs/images/unreviewed.png")
        with self.reviewed_media():
            self.assertIn("binary payload", str(audit(self.root)["findings"]))

    def test_reviewed_image_replaced_by_text_is_rejected(self):
        self.write_media(data=b"not the reviewed image")
        with self.reviewed_media():
            self.assertIn("media hash mismatch", str(audit(self.root)["findings"]))

    def test_unreviewed_indexed_image_is_not_hidden_by_reviewed_working_image(self):
        path = self.write_media(data=self.media_bytes + b"changed")
        self.git("add", self.media_name)
        path.write_bytes(self.media_bytes)
        with self.reviewed_media():
            self.assertTrue(any(entry["scope"] == "index" for entry in audit(self.root)["findings"]))

    def test_unreviewed_historical_image_is_not_hidden_by_reviewed_working_image(self):
        path = self.write_media(data=self.media_bytes + b"changed")
        self.git("add", self.media_name)
        self.commit()
        path.write_bytes(self.media_bytes)
        self.git("add", self.media_name)
        with self.reviewed_media():
            self.assertTrue(any(entry["scope"] == "history" for entry in audit(self.root, history=True)["findings"]))

    def test_reviewed_hash_does_not_bypass_secret_detection(self):
        secret = "ghp_" + "a" * 36
        data = self.media_bytes + secret.encode()
        self.write_media(data=data)
        with self.reviewed_media(data):
            findings = audit(self.root)["findings"]
        self.assertIn("possible secret", str(findings))
        self.assertNotIn(secret, str(findings))

    def test_ignored_local_memory_is_not_scanned_or_removed(self):
        (self.root / ".gitignore").write_text("/.opencode/memory/\n")
        memory = self.root / ".opencode/memory/memory.db"
        memory.parent.mkdir(parents=True)
        memory.write_bytes(b"private memory")
        self.assertEqual(audit(self.root)["findings"], [])
        self.assertEqual(memory.read_bytes(), b"private memory")

    def test_tracked_memory_is_rejected_even_when_ignored(self):
        memory = self.root / ".opencode/memory/snapshot.db"
        memory.parent.mkdir(parents=True)
        memory.write_bytes(b"private memory")
        self.git("add", ".opencode/memory/snapshot.db")
        (self.root / ".gitignore").write_text("/.opencode/memory/\n")
        self.assertIn("private path", str(audit(self.root)["findings"]))

    def test_original_payload_is_rejected(self):
        (self.root / "Celeste.exe").write_bytes(b"synthetic executable")
        self.assertIn("payload", str(audit(self.root)["findings"]))

    def test_secret_is_reported_without_its_value(self):
        secret = "ghp_" + "a" * 36
        (self.root / "config.txt").write_text(secret)
        findings = audit(self.root)["findings"]
        self.assertIn("secret", str(findings))
        self.assertNotIn(secret, str(findings))

    def test_staged_secret_is_detected_when_working_tree_is_cleaned(self):
        path = self.root / "config.txt"
        secret = "ghp_" + "a" * 36
        path.write_text(secret)
        self.git("add", "config.txt")
        path.write_text("sanitized working tree")
        findings = audit(self.root)["findings"]
        self.assertTrue(any(entry["scope"] == "index" and "secret" in entry["reason"] for entry in findings))
        self.assertNotIn(secret, str(findings))

    def test_history_still_blocks_after_local_memory_is_untracked(self):
        memory = self.root / ".opencode/memory/snapshot.db"
        memory.parent.mkdir(parents=True)
        memory.write_bytes(b"private memory")
        self.git("add", ".opencode/memory/snapshot.db")
        self.commit()
        self.git("rm", "--cached", ".opencode/memory/snapshot.db")
        (self.root / ".gitignore").write_text("/.opencode/memory/\n")
        self.assertEqual(audit(self.root)["findings"], [])
        self.assertIn("history", str(audit(self.root, history=True)["findings"]))


if __name__ == "__main__":
    unittest.main()
