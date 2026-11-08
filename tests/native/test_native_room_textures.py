import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from native_room_textures import atlas_metadata, decode_crops, extrude


def string(value):
    encoded = value.encode()
    return bytes([len(encoded)]) + encoded


def metadata(rect=(0, 0, 2, 1, -1, -2, 4, 4)):
    return (struct.pack("<i", 5) + string("synthetic") + struct.pack("<i", 0)
            + struct.pack("<h", 1) + string("sheet") + struct.pack("<h", 1)
            + string("tile") + struct.pack("<8h", *rect))


class TextureTests(unittest.TestCase):
    def test_signed_metadata_fields(self):
        self.assertEqual(atlas_metadata(metadata())["tile"], ("sheet", 0, 0, 2, 1, -1, -2, 4, 4))

    def test_metadata_truncation(self):
        with self.assertRaises(ValueError):
            atlas_metadata(metadata()[:-1])

    def test_metadata_negative_crop(self):
        with self.assertRaises(ValueError):
            atlas_metadata(metadata((-1, 0, 2, 1, 0, 0, 2, 1)))

    def test_metadata_trailing_bytes(self):
        with self.assertRaises(ValueError):
            atlas_metadata(metadata() + b"foreign")

    def test_transparent_runs_advance_positions(self):
        data = struct.pack("<iiB", 4, 1, 1) + bytes([2, 0, 2, 128, 30, 20, 10])
        self.assertEqual(decode_crops(data, {"crop": (1, 0, 3, 1)})["crop"],
                         bytes([0, 0, 0, 0, 10, 20, 30, 128, 10, 20, 30, 128]))

    def test_nonalpha_pixels(self):
        data = struct.pack("<iiB", 2, 1, 0) + bytes([2, 3, 2, 1])
        self.assertEqual(decode_crops(data, {"crop": (0, 0, 2, 1)})["crop"], bytes([1, 2, 3, 255]) * 2)

    def test_run_overrun(self):
        with self.assertRaises(ValueError):
            decode_crops(struct.pack("<iiB", 1, 1, 1) + bytes([2, 0]), {})

    def test_zero_run(self):
        with self.assertRaises(ValueError):
            decode_crops(struct.pack("<iiB", 1, 1, 1) + bytes([0, 0]), {})

    def test_truncated_run(self):
        with self.assertRaises(ValueError):
            decode_crops(struct.pack("<iiB", 1, 1, 1) + bytes([1, 128, 2]), {})

    def test_invalid_dimensions(self):
        with self.assertRaises(ValueError):
            decode_crops(struct.pack("<iiB", -1, 1, 1), {})

    def test_crop_outside_sheet(self):
        with self.assertRaises(ValueError):
            decode_crops(struct.pack("<iiB", 1, 1, 1) + bytes([1, 0]), {"crop": (1, 0, 1, 1)})

    def test_entire_stream_validated_outside_crop(self):
        with self.assertRaises(ValueError):
            decode_crops(struct.pack("<iiB", 2, 1, 1) + bytes([1, 0]), {"crop": (0, 0, 1, 1)})

    def test_one_pixel_extruded_border(self):
        a, b = bytes([1, 2, 3, 4]), bytes([5, 6, 7, 8])
        self.assertEqual(extrude(a + b, 2, 1, 4, 4), (a + a + b + b) * 3 + bytes(16))


if __name__ == "__main__":
    unittest.main()
