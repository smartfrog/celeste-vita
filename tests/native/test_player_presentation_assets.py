import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from native_player_assets import pack_player_crops


class SweatBankTests(unittest.TestCase):
    def setUp(self):
        self.bank = {"animations": [{"id": str(i)} for i in range(27)], "frames": []}
        self.xml = b'''<Sprites><player_sweat path="s/" start="idle"><Justify x=".5" y="1"/>
            <Loop id="idle" path="idle"/><Anim id="climb" path="climb" frames="0,1" delay=".1" goto="climbLoop"/>
            <Loop id="climbLoop" path="climb" frames="2-7" delay=".1"/><Loop id="still" path="still" delay=".1"/>
            <Anim id="jump" path="jump" delay=".1" goto="idle"/><Loop id="danger" path="danger" delay=".05"/>
            </player_sweat></Sprites>'''
        self.atlas = {f"s/{name}{i:02d}": ("Gameplay0", 1, 2, 3, 4, -12, -15, 32, 32)
                      for name, count in (("idle", 1), ("climb", 8), ("still", 2), ("jump", 3), ("danger", 2))
                      for i in range(count)}

    def extend(self, xml=None, atlas=None):
        from native_player_assets import extend_sweat_bank
        return extend_sweat_bank(self.bank, self.xml if xml is None else xml, self.atlas if atlas is None else atlas)

    def test_preserves_body_bank_and_exports_namespaced_source_animations(self):
        result = self.extend()
        self.assertEqual(result["animations"][:27], self.bank["animations"])
        self.assertEqual([a["id"] for a in result["animations"][27:]],
                         ["player_sweat_" + name for name in ("idle", "climb", "climbLoop", "still", "jump", "danger")])
        self.assertEqual(len(result["frames"]), 16)
        self.assertEqual(self.bank["frames"], [])

    def test_missing_idle_delay_defaults_to_zero(self):
        self.assertEqual(self.extend()["animations"][27]["delay"], 0)

    def test_climb_intro_and_loop_retain_source_order_and_float_delay(self):
        import struct
        intro, loop = self.extend()["animations"][28:30]
        self.assertEqual(intro["frames"], ["s/climb00", "s/climb01"])
        self.assertEqual(intro["next"], "player_sweat_climbLoop")
        self.assertEqual(loop["frames"], [f"s/climb{i:02d}" for i in range(2, 8)])
        self.assertEqual(loop["next"], loop["id"])
        self.assertEqual(intro["delay"], struct.unpack("<f", struct.pack("<f", .1))[0])

    def test_exports_per_frame_trim_without_hair(self):
        frame = self.extend()["frames"][0]
        self.assertEqual((frame["trim"], frame["size"], frame["hasHair"]), ([12, 15], [32, 32], False))

    def test_implicit_frames_expand_beyond_idle00(self):
        atlas = {**self.atlas, "s/idle01": self.atlas["s/idle00"]}
        self.assertEqual(self.extend(atlas=atlas)["animations"][27]["frames"], ["s/idle00", "s/idle01"])

    def test_unknown_goto_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "goto"):
            self.extend(xml=self.xml.replace(b'goto="climbLoop"', b'goto="missing"'))

    def test_missing_explicit_frame_is_rejected(self):
        atlas = dict(self.atlas)
        del atlas["s/climb07"]
        with self.assertRaisesRegex(ValueError, "frame"):
            self.extend(atlas=atlas)

    def test_duplicate_animation_id_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "animation"):
            self.extend(xml=self.xml.replace(b'id="still"', b'id="idle"'))


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
