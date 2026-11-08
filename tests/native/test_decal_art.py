import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from prepare_decals import (PAGE_HEIGHT, PAGE_WIDTH, mapped_pixel, pack, protocol_text)
from stage_native_room import checksum
from compare_decal_draws import recompute_quad, verify_instance
from native_room_feedback import validate_decal_pixels


def synthetic_crops():
    crops, metadata = {}, {}
    for index in range(15):
        name = f"decals/generic/t{index:02d}"
        crops[name] = bytes((index, 2, 3, 255)) * 16
        metadata[name] = ("Gameplay0", 0, 0, 4, 4, 0, 0, 16, 16)
    return crops, metadata


class DecalComparatorTests(unittest.TestCase):
    def fixture(self):
        import hashlib
        import struct
        crop = bytes((10, 20, 30, 255)) * 16
        texture = {"u": 1, "v": 1, "width": 4, "height": 4, "draw_offset": [2, 1], "frame": [8, 8],
                   "crop_sha256": hashlib.sha256(crop).hexdigest(), "page": [64, 128]}
        page = bytearray(PAGE_WIDTH * PAGE_HEIGHT * 4)
        for row in range(4):
            start = ((1 + row) * PAGE_WIDTH + 1) * 4
            page[start:start + 16] = crop[row * 16:(row + 1) * 16]
        instance = {"group": "bgdecals", "source_index": 0, "name": "decals/generic/t00", "position": [10, 20],
                    "scale": [1, 1], "depth": 9000, "frame": [8, 8], "draw_offset": [2, 1], "origin": [2, 3]}
        quad = recompute_quad(instance, texture)
        points = [(quad["left"], quad["top"]), (quad["right"], quad["top"]),
                  (quad["left"], quad["bottom"]), (quad["right"], quad["bottom"])]
        draw = {**instance, "behavior": "DecalImage",
                "vertices_bits": [struct.pack(">f", value).hex() for point in points for value in point]}
        return bytes(page), texture, instance, draw

    def test_comparator_accepts_exact_source_identity(self):
        page, texture, instance, draw = self.fixture()
        row = verify_instance(draw, instance, texture, page, PAGE_WIDTH)
        self.assertEqual(row["name"], "decals/generic/t00")

    def test_comparator_rejects_position_scale_depth_frame_and_texture_mutations(self):
        page, texture, instance, draw = self.fixture()
        for key, value in (("position", [11, 20]), ("scale", [-1, 1]), ("depth", -10500),
                           ("frame", [16, 16]), ("draw_offset", [3, 1]), ("origin", [3, 3]), ("name", "decals/generic/t01")):
            mutated = {**draw, key: value}
            with self.assertRaises(ValueError):
                verify_instance(mutated, instance, texture, page, PAGE_WIDTH)
        corrupted = bytearray(page)
        corrupted[(1 * PAGE_WIDTH + 1) * 4] ^= 1
        with self.assertRaises(ValueError):
            verify_instance(draw, instance, texture, bytes(corrupted), PAGE_WIDTH)

    def test_comparator_rejects_a_banner_draw_in_the_static_profile(self):
        page, texture, instance, draw = self.fixture()
        with self.assertRaises(ValueError):
            verify_instance({**draw, "behavior": "Banner"}, instance, texture, page, PAGE_WIDTH)


class DecalFeedbackTests(unittest.TestCase):
    def fixture(self):
        probes = [
            {"kind": "visible_static_bg_positive", "screen_pixel": [3, 3], "expected_rgb": [10, 20, 30]},
            {"kind": "visible_static_bg_flip_horizontal", "screen_pixel": [6, 3], "expected_rgb": [40, 50, 60]},
            {"kind": "visible_static_bg_flip_vertical", "screen_pixel": [9, 3], "expected_rgb": [70, 80, 90]},
            {"kind": "visible_static_fg", "screen_pixel": [12, 3], "expected_rgb": [100, 110, 120]},
        ]
        pixels = bytearray(960 * 544 * 3)
        for probe in probes:
            x, y = probe["screen_pixel"]
            pixels[(y * 960 + x) * 3:(y * 960 + x + 1) * 3] = bytes(probe["expected_rgb"])
        return bytes(pixels), {"content_probes": probes, "classification": {"static": 22, "banner_omitted": 7}}

    def test_decal_feedback_accepts_both_axes_bg_fg_and_no_diagnostic_red(self):
        pixels, decals = self.fixture()
        result = validate_decal_pixels(pixels, decals)
        self.assertEqual(result["static"], 22)
        self.assertEqual(len(result["probes"]), 4)

    def test_decal_feedback_rejects_a_wrong_probe_or_diagnostic_red(self):
        pixels, decals = self.fixture()
        wrong = bytearray(pixels)
        wrong[(3 * 960 + 3) * 3] ^= 1
        with self.assertRaises(ValueError):
            validate_decal_pixels(bytes(wrong), decals)
        red = bytearray(pixels)
        red[(1 * 960 + 1) * 3:(1 * 960 + 1) * 3 + 3] = bytes((255, 51, 51))
        with self.assertRaises(ValueError):
            validate_decal_pixels(bytes(red), decals)
        incomplete = {**decals, "content_probes": decals["content_probes"][:3]}
        with self.assertRaises(ValueError):
            validate_decal_pixels(pixels, incomplete)


class DecalAssetTests(unittest.TestCase):
    def test_packer_fits_fifteen_crops_in_one_bounded_page_without_overlap(self):
        crops, metadata = synthetic_crops()
        page, placed = pack(crops, metadata)
        self.assertEqual(len(page), PAGE_WIDTH * PAGE_HEIGHT * 4)
        self.assertEqual(len(placed), 15)
        for index, (name, (x, y, width, height)) in enumerate(sorted(placed.items())):
            self.assertEqual((width, height), (4, 4))
            self.assertGreaterEqual(x, 1)
            self.assertGreaterEqual(y, 1)
            self.assertLessEqual(x + width, PAGE_WIDTH - 1)
            self.assertLessEqual(y + height, PAGE_HEIGHT - 1)
            offset = (y * PAGE_WIDTH + x) * 4
            self.assertEqual(tuple(page[offset:offset + 4]), (int(name[-2:]), 2, 3, 255))

    def test_packer_refuses_an_oversized_crop_instead_of_truncating(self):
        crops, metadata = synthetic_crops()
        metadata["decals/generic/t00"] = ("Gameplay0", 0, 0, 200, 200, 0, 0, 200, 200)
        crops["decals/generic/t00"] = bytes(200 * 200 * 4)
        with self.assertRaises(ValueError):
            pack(crops, metadata)

    def test_protocol_preserves_instance_order_signed_scale_and_explicit_banner_rows(self):
        textures = {"decals/generic/t00": {"u": 1, "v": 1, "width": 8, "height": 8, "draw_offset": [0, 0], "frame": [16, 16]}}
        instances = [
            {"group": "bgdecals", "source_index": 0, "position": [10, 20], "scale": [1, -1], "name": "decals/generic/t00"},
            {"group": "fgdecals", "source_index": 0, "position": [30, 40], "scale": [-1, 1], "name": "decals/generic/t00"},
        ]
        banners = [("B", 20, "1-forsakencity/ragsB"), ("B", 21, "1-forsakencity/rags"),
                   ("B", 22, "1-forsakencity/ragsB"), ("B", 23, "1-forsakencity/rags"),
                   ("B", 24, "1-forsakencity/ragsB"), ("F", 2, "generic/grass_a"), ("F", 3, "generic/grass_d")]
        text = protocol_text(textures, instances, banners, bytes(PAGE_WIDTH * PAGE_HEIGHT * 4)).decode("ascii")
        lines = text.splitlines()
        self.assertEqual(lines[:3], ["CSD1", "fd73f8a2311fa5737ded550cbad4b75c85b7686b36432f59185e940fcb65fcfe",
                                     "ace1892261c03aa766f45aaa38cb2cd60a8823c34eda673f5b2ed8ab31c890ab"])
        page = bytes(PAGE_WIDTH * PAGE_HEIGHT * 4)
        self.assertEqual(lines[3:7], ["1", f"64 128 {checksum(page):08x}", "1", "decals/generic/t00 1 1 8 8 0 0 16 16"])
        self.assertEqual(lines[7:10], ["2", "B 0 10 20 1 -1 0", "F 0 30 40 -1 1 0"])
        self.assertEqual(lines[10], "7")
        self.assertEqual(lines[11:], ["B 20 1-forsakencity/ragsB", "B 21 1-forsakencity/rags", "B 22 1-forsakencity/ragsB",
                                      "B 23 1-forsakencity/rags", "B 24 1-forsakencity/ragsB",
                                      "F 2 generic/grass_a", "F 3 generic/grass_d"])

    def test_mapped_pixel_preserves_both_signed_axes(self):
        placed = {"x": (1, 1, 10, 10)}
        positive = {"name": "x", "origin": [5, 3], "scale": [1, 1], "position": [20, 20]}
        vertical = {"name": "x", "origin": [5, 3], "scale": [1, -1], "position": [20, 20]}
        horizontal = {"name": "x", "origin": [5, 3], "scale": [-1, 1], "position": [20, 20]}
        both = {"name": "x", "origin": [5, 3], "scale": [-1, -1], "position": [20, 20]}
        self.assertEqual(mapped_pixel(positive, placed, 0, 0), (15, 17))
        self.assertEqual(mapped_pixel(vertical, placed, 0, 0), (15, 22))
        self.assertEqual(mapped_pixel(horizontal, placed, 0, 0), (24, 17))
        self.assertEqual(mapped_pixel(both, placed, 0, 0), (24, 22))

    def test_page_checksum_line_is_fixed_width_and_present(self):
        textures = {"decals/generic/t00": {"u": 1, "v": 1, "width": 8, "height": 8, "draw_offset": [0, 0], "frame": [16, 16]}}
        text = protocol_text(textures, [], [], b"\0" * (PAGE_WIDTH * PAGE_HEIGHT * 4)).decode("ascii")
        dimensions = text.splitlines()[4].split()
        self.assertEqual(dimensions[:2], ["64", "128"])
        self.assertEqual(dimensions[2], f"{checksum(bytes(PAGE_WIDTH * PAGE_HEIGHT * 4)):08x}")


if __name__ == "__main__":
    unittest.main()
