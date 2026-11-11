from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import prepare_game


class PrepareGameTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_rejects_output_outside_private_directory(self):
        with self.assertRaisesRegex(ValueError, "private"):
            prepare_game.preparation_output(self.root / "outside", self.root)

    def test_preserves_existing_preparation(self):
        output = self.root / ".audit/prepared"
        output.mkdir(parents=True)
        with self.assertRaisesRegex(FileExistsError, "fresh"):
            prepare_game.preparation_output(output, self.root)

    def test_rejects_symlink_escape(self):
        (self.root / ".audit").symlink_to(self.root.parent, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "private"):
            prepare_game.preparation_output(self.root / ".audit/prepared", self.root)

    def test_checks_input_before_installing_tools(self):
        with patch.object(prepare_game, "ensure_tools") as tools:
            with self.assertRaises(FileNotFoundError):
                prepare_game.prepare(self.root / "missing.zip", self.root / ".audit/prepared", root=self.root)
        tools.assert_not_called()

    def test_extracts_raw_room_in_existing_canonical_serialization(self):
        room = {"name": "level", "attributes": {"name": "lvl_1"}, "children": []}
        root = {"children": [{"name": "levels", "children": [room]}]}
        self.assertEqual(prepare_game.raw_room_text(root),
                         '{\n  "name": "level",\n  "attributes": {\n    "name": "lvl_1"\n  },\n  "children": []\n}\n')

    def test_preparation_pins_all_decompiler_reference_assemblies(self):
        self.assertTrue({"System.dll", "System.Xml.dll", "System.Core.dll", "Celeste.Content.dll"} <= prepare_game.GAME_PINS.keys())


if __name__ == "__main__":
    unittest.main()
