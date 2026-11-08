import hashlib
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from prepare_player_presentation_oracle import source_block, SOURCE_PINS
from read_player_presentation_sources import source_type


class PresentationRecipeTests(unittest.TestCase):
    def test_selected_original_source_bytes_are_not_rewritten(self):
        original = b"header\n\tpublic void Synthetic() { }\nfooter\n"
        digest = hashlib.sha256(original).hexdigest()
        self.assertEqual(source_block(original, [(2, 2)], digest), [b"\tpublic void Synthetic() { }\n"])

    def test_changed_original_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "source identity"):
            source_block(b"changed", [(1, 1)], "0" * 64)

    def test_missing_executable_lines_are_rejected(self):
        original = b"one\n"
        with self.assertRaisesRegex(ValueError, "range"):
            source_block(original, [(1, 2)], hashlib.sha256(original).hexdigest())

    def test_generic_chooser_type_is_explicitly_mapped(self):
        self.assertEqual(source_type("Monocle.Chooser_1.cs"), ("Celeste.exe", "Monocle.Chooser`1"))

    def test_original_random_comes_from_pinned_mscorlib(self):
        self.assertEqual(source_type("System.Random.cs"), ("mscorlib.dll", "System.Random"))

    def test_default_mode_callers_are_part_of_the_source_closure(self):
        self.assertTrue({"Celeste.Level.cs", "Celeste.AreaData.cs", "Celeste.PlayerInventory.cs", "Monocle.ComponentList.cs"} <= set(SOURCE_PINS))


if __name__ == "__main__":
    unittest.main()
