import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from native_player_assets import pack_player_crops


class PlayerCropTests(unittest.TestCase):
    def test_death_extension_keeps_legacy_animations_and_uses_original_frames(self):
        from native_player_assets import extend_death_bank
        bank = {"animations": [{"id": str(i)} for i in range(24)], "frames": []}
        xml = b'<Sprites><player path="p/"><Anim id="deadup" path="death" delay="0.02" frames="0-1"/><Anim id="deaddown" path="death" delay="0.02" frames="0-1"/><Anim id="deadside" path="death" delay="0.02" frames="0-1"/><Metadata/></player><player_sweat path="s/"><Loop id="idle" path="idle" frames="0"/></player_sweat></Sprites>'
        atlas = {"p/death00": ("Gameplay0",1,2,3,4,-5,-6,32,32), "p/death01": ("Gameplay0",11,12,3,4,-5,-6,32,32), "s/idle00": ("Gameplay0",21,22,1,1,0,0,32,32)}
        result = extend_death_bank(bank, xml, atlas)
        self.assertEqual(result["animations"][:24], bank["animations"])
        self.assertEqual([a["id"] for a in result["animations"][24:]], ["deadup", "deaddown", "deadside"])
        self.assertEqual(result["animations"][24]["frames"], ["p/death00", "p/death01"])
        self.assertEqual(result["frames"][0]["trim"], [5,6])
        self.assertFalse(result["frames"][0]["hasHair"])

    def test_death_extension_rejects_unresolved_animation(self):
        from native_player_assets import extend_death_bank
        with self.assertRaisesRegex(ValueError, "death animation"):
            extend_death_bank({"animations": [{}]*24, "frames": []}, b'<Sprites><player path="p/"/></Sprites>', {})

    def test_identical_crops_share_page_rectangle(self):
        pages, layout = pack_player_crops({"a": (2, 2, bytes([50, 25, 0, 128]) * 4),
                                           "b": (2, 2, bytes([50, 25, 0, 128]) * 4)})
        self.assertEqual(layout["a"], layout["b"])
        self.assertEqual(len(pages), 1)

    def test_edge_extrusion_preserves_premultiplied_bytes(self):
        rgba = bytes([50, 25, 0, 128])
        pages, layout = pack_player_crops({"a": (1, 1, rgba)})
        _, x, y = layout["a"]
        for dx, dy in ((-1, -1), (0, 0), (1, 1)):
            offset = ((y + dy) * 128 + x + dx) * 4
            self.assertEqual(pages[0][offset:offset + 4], rgba)

    def test_upload_pages_have_fixed_bounded_dimensions(self):
        pages, _ = pack_player_crops({"a": (15, 13, bytes(15 * 13 * 4))})
        self.assertEqual([len(page) for page in pages], [128 * 64 * 4])

    def test_oversized_crop_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "crop"):
            pack_player_crops({"a": (127, 1, bytes(127 * 4))})

    def test_closure_over_budget_is_rejected_without_omission(self):
        crops = {str(i): (126, 62, bytes([i, 0, 0, 255]) * (126 * 62)) for i in range(11)}
        with self.assertRaisesRegex(ValueError, "budget"):
            pack_player_crops(crops)


if __name__ == "__main__":
    unittest.main()
