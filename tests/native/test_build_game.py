import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from build_game import read_preparation, toolchain_environment, vitagl_include_directory


class BuildGameTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_rejects_missing_vita_sdk_before_creating_build(self):
        with self.assertRaisesRegex(ValueError, "VitaSDK"):
            toolchain_environment(self.root / "missing", self.root / "libvitaGL.a")

    def test_rejects_missing_vitagl_archive(self):
        (self.root / "sdk/share").mkdir(parents=True)
        (self.root / "sdk/share/vita.toolchain.cmake").touch()
        with self.assertRaisesRegex(ValueError, "vitaGL"):
            toolchain_environment(self.root / "sdk", self.root / "missing.a")

    def test_rejects_incomplete_preparation(self):
        path = self.root / "preparation.json"
        path.write_text(json.dumps({"schema": 1, "status": "failed"}))
        with self.assertRaisesRegex(ValueError, "completed"):
            read_preparation(path, self.root)

    def test_rejects_preparation_paths_outside_private_directory(self):
        path = self.root / "preparation.json"
        path.write_text(json.dumps({"schema": 1, "status": "prepared", **{
            key: str(self.root / "outside") for key in
            ("archive", "mask_dir", "hazard_dir", "visual_dir", "player_dir", "decal_dir")}}))
        with self.assertRaisesRegex(ValueError, "private"):
            read_preparation(path, self.root)

    def test_finds_header_in_matching_vitagl_source_checkout(self):
        directory = self.root / "vitaGL/source"
        directory.mkdir(parents=True)
        (directory / "vitaGL.h").write_text("synthetic header")
        self.assertEqual(vitagl_include_directory(self.root / "sdk", self.root / "vitaGL/libvitaGL.a"), directory)

    def test_finds_header_in_installed_sdk(self):
        directory = self.root / "sdk/arm-vita-eabi/include"
        directory.mkdir(parents=True)
        (directory / "vitaGL.h").write_text("synthetic header")
        self.assertEqual(vitagl_include_directory(self.root / "sdk", self.root / "libvitaGL.a"), directory)

    def test_missing_vitagl_header_fails_early(self):
        with self.assertRaisesRegex(ValueError, "vitagl-include"):
            vitagl_include_directory(self.root / "sdk", self.root / "libvitaGL.a")

    def test_invalid_explicit_include_does_not_fall_back(self):
        directory = self.root / "vitaGL/source"
        directory.mkdir(parents=True)
        (directory / "vitaGL.h").write_text("synthetic header")
        with self.assertRaisesRegex(ValueError, "vitagl-include"):
            vitagl_include_directory(self.root / "sdk", self.root / "vitaGL/libvitaGL.a", self.root / "missing")


if __name__ == "__main__":
    unittest.main()
