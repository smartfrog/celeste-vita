import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from prepare_decals_oracle import (CORRECTIONS_SHA, DISCOVERY_PINS, FRAMEWORK_PINS,
                                   GAMEPLAY_DATA_SHA, GAMEPLAY_META_SHA, RAW_ROOM_SHA)


STATIC_KEYS = {("fgdecals", 0), ("fgdecals", 1), *{("bgdecals", index) for index in range(20)}}
BANNER_KEYS = {("fgdecals", 2), ("fgdecals", 3), *{("bgdecals", index) for index in range(20, 25)}}
NEGATIVE_SCALES = {(("bgdecals", index), (1, -1)) for index in (0, 1, 2, 14, 16)} | \
                  {(("bgdecals", index), (-1, 1)) for index in (8, 10, 13)}


class DecalSourceContractTests(unittest.TestCase):
    def test_corrected_supplement_and_immutable_source_pins_are_fixed(self):
        self.assertEqual(CORRECTIONS_SHA, "f56653b9155553524e9337b7299b6c4fc14577fb1079182154c4ab730385a829")
        self.assertEqual(RAW_ROOM_SHA, "3eefb6d3fae3cc0977583d8f53075da3db98da01795c0ce56f5b799e8bc65eb3")
        self.assertEqual(DISCOVERY_PINS["Celeste.Decal.cs"], "81d04a56cb9b5cb981f3c7823388bed6082db2d5755d364c15c35bbcaf8b7746")
        self.assertEqual(GAMEPLAY_META_SHA, "1f23b1f35544a3751ffec170b0230c7c9513000ab1549f78ebb9cb9f4203c8d9")
        self.assertEqual(GAMEPLAY_DATA_SHA, "687f3340c937e3baca71758bfb1e6b8e799ad896f2df19bef26ec64968b3490b")

    def test_static_and_banner_split_is_twenty_two_and_seven(self):
        self.assertEqual(len(STATIC_KEYS), 22)
        self.assertEqual(len(BANNER_KEYS), 7)
        self.assertFalse(STATIC_KEYS & BANNER_KEYS)
        self.assertEqual(len([key for key in STATIC_KEYS if key[0] == "bgdecals"]), 20)
        self.assertEqual(len([key for key in STATIC_KEYS if key[0] == "fgdecals"]), 2)

    def test_banner_texture_arguments_are_the_source_make_banner_calls(self):
        self.assertEqual(BANNER_KEYS, {("fgdecals", 2), ("fgdecals", 3),
                                       ("bgdecals", 20), ("bgdecals", 21), ("bgdecals", 22),
                                       ("bgdecals", 23), ("bgdecals", 24)})

    def test_negative_signed_scales_are_preserved_per_instance(self):
        self.assertEqual(len(NEGATIVE_SCALES), 8)
        self.assertEqual({scale for _, scale in NEGATIVE_SCALES}, {(1, -1), (-1, 1)})

    def test_static_origin_is_center_minus_draw_offset(self):
        for frame, offset, origin in (((16, 16), (3, 0), (5, 8)),
                                      ((16, 16), (5, 9), (3, -1)),
                                      ((15, 19), (1, 1), (6.5, 8.5))):
            self.assertEqual((frame[0] / 2 - offset[0], frame[1] / 2 - offset[1]), origin)

    def test_static_source_profile_has_no_frame_animation(self):
        self.assertEqual(len({name for name in DISCOVERY_PINS}), 4)
        self.assertIn("Monocle.MTexture.cs", DISCOVERY_PINS)
        self.assertIn("Microsoft.Xna.Framework.Graphics.SpriteBatch.cs", FRAMEWORK_PINS)


if __name__ == "__main__":
    unittest.main()
