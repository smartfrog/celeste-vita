import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import bootstrap_game_tools as tools


class GameToolsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.package = self.root / "tool.nupkg"

    def install(self, files):
        with zipfile.ZipFile(self.package, "w") as package:
            for name, data in files.items():
                package.writestr(name, data)
        digest = hashlib.sha256(self.package.read_bytes()).hexdigest()
        with patch.object(tools, "PACKAGE_SHA", digest), patch.object(tools, "PACKAGE_BYTES", self.package.stat().st_size):
            tools.install_ilspy(self.package, self.root / "tool")

    def test_installs_verified_tool_package(self):
        self.install({"tools/net8.0/any/tool.dll": b"synthetic"})
        self.assertEqual((self.root / "tool/tools/net8.0/any/tool.dll").read_bytes(), b"synthetic")

    def test_rejects_unrecognized_package_before_extraction(self):
        self.package.write_bytes(b"not the pinned tool")
        with self.assertRaisesRegex(ValueError, "identity"):
            tools.install_ilspy(self.package, self.root / "tool")
        self.assertFalse((self.root / "tool").exists())

    def test_rejects_unsafe_tool_member(self):
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            self.install({"../escape": b"bad"})
        self.assertFalse((self.root / "escape").exists())

    def test_existing_changed_tool_is_not_overwritten(self):
        self.install({"tool.dll": b"synthetic"})
        (self.root / "tool/tool.dll").write_bytes(b"local changes")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.install({"tool.dll": b"synthetic"})
        self.assertEqual((self.root / "tool/tool.dll").read_bytes(), b"local changes")


if __name__ == "__main__":
    unittest.main()
