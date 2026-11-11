from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from check_public_repository import audit


class PublicRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git("init", "--quiet")

    def git(self, *arguments):
        return subprocess.run(["git", *arguments], cwd=self.root, check=True, capture_output=True, text=True)

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
        self.git("-c", "user.name=Synthetic Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "Synthetic fixture")
        self.git("rm", "--cached", ".opencode/memory/snapshot.db")
        (self.root / ".gitignore").write_text("/.opencode/memory/\n")
        self.assertEqual(audit(self.root)["findings"], [])
        self.assertIn("history", str(audit(self.root, history=True)["findings"]))


if __name__ == "__main__":
    unittest.main()
