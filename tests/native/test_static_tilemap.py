import struct
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from binary_map import Reader
from prepare_static_tilemap import Layer, build_mask, merge_text, mask_text, read_mask, tile_bounds


class StaticTilemapTests(unittest.TestCase):
    def test_global_extrusion(self):
        mask = build_mask({"levels": [{"name": "lvl_test", "x": 0, "y": 0, "width": 8, "height": 8, "solids": "1", "bg": ""}], "filler": []})
        x, y, columns, rows, cells = mask
        self.assertEqual((x, y, columns, rows), (-64, -64, 17, 17))
        self.assertEqual(cells[(0 - y) // 8 * columns + (-8 - x) // 8], "1")

    def test_newlines_short_overlong_and_zero_overwrite_parameterized(self):
        for separator in ("\r\n", "\n\r", "\n", "\r"):
            with self.subTest(separator=separator):
                layer = Layer(6, 3, "0")
                merge_text(layer, 1, 0, "11111" + separator + "11")
                merge_text(layer, 2, 0, "0" + separator + "")
                self.assertEqual("".join(layer.data), "010111011000000000")

    def test_room_reservations_use_global_origin(self):
        rooms = [dict(name="lvl_left", x=0, y=0, width=8, height=8, solids="1", bg=""),
                 dict(name="lvl_right", x=16, y=0, width=8, height=8, solids="0", bg="")]
        x, y, columns, rows, cells = build_mask({"levels": rooms, "filler": []})
        self.assertEqual(cells[(-y // 8) * columns + (16 - x) // 8], "0")

    def test_raw_storage_out_of_bounds_rejected(self):
        with self.assertRaisesRegex(ValueError, "Raw VirtualMap"):
            merge_text(Layer(1, 1, "0"), 0, 0, "11")

    def test_normalized_height_and_negative_origin(self):
        self.assertEqual(tile_bounds(dict(x=-7, y=-9, width=320, height=184)), (0, -1, 40, 23))

    def test_mask_round_trip(self):
        mask = (-8, 0, 2, 1, "10")
        self.assertEqual(read_mask(mask_text(mask)), mask)

    def test_invalid_mask_parameterized(self):
        good = mask_text((0, 0, 1, 1, "1"))
        for text in (good.replace("CSTM1", "CSTM2"), good.replace("fd73", "0000"), good.replace("0 0 1 1", "0 0 2 1"),
                     good.replace("0 0 1 1", "0 0 -1 1"), good[:-2] + "2\n", good + "\n", good.replace("0 0 1 1", "2147483647 0 1 1")):
            with self.subTest(text=text), self.assertRaises(ValueError):
                read_mask(text)

    def test_binary_map_minimal(self):
        def string(value):
            return bytes([len(value)]) + value.encode()
        data = string("CELESTE MAP") + string("test") + struct.pack("<h", 1) + string("root") + struct.pack("<hBh", 0, 0, 0)
        package, root = Reader(data).map()
        self.assertEqual((package, root["name"]), ("test", "root"))

    def test_binary_map_invalid_parameterized(self):
        for data in (b"", b"\xff" * 5, b"\x03bad", b"\x0bCELESTE MAP\x00\xff\xff"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                Reader(data).map()

    def test_binary_attribute_types_parameterized(self):
        examples = [(b"\x00\x01", True), (b"\x01\xff", 255), (b"\x02" + struct.pack("<h", -12), -12),
                    (b"\x03" + struct.pack("<i", -100000), -100000), (b"\x04" + struct.pack("<f", 1.5), 1.5),
                    (b"\x05\x00\x00", "lookup"), (b"\x06\x03abc", "abc"),
                    (b"\x07\x04\x00\x03a\x02b", "aaabb")]
        for data, value in examples:
            with self.subTest(data=data):
                reader = Reader(data); reader.strings = ["lookup"]
                self.assertEqual(reader.value(), value)

    def test_binary_invalid_attribute_parameterized(self):
        for data in (b"\x00\x02", b"\x08", b"\x05\xff\xff", b"\x07\xff\xff", b"\x07\x03\x00abc", b"\x03\x00"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                Reader(data).value()
