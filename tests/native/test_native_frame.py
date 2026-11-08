from pathlib import Path
import struct
import sys
import unittest
import zlib

sys.dont_write_bytecode = True
sys.path.insert(0,str(Path(__file__).resolve().parents[2] / "scripts"))
from convert_native_frame import ppm_to_png


class NativeFrameConversionTests(unittest.TestCase):
    def test_conversion_preserves_top_down_rgb_pixels_losslessly(self):
        pixels = bytes([255,0,0,0,255,0,0,0,255,255,255,255])
        png = ppm_to_png(b"P6\n2 2\n255\n"+pixels)
        self.assertEqual(png[:8],b"\x89PNG\r\n\x1a\n")
        chunks = {}
        offset = 8
        while offset < len(png):
            length = struct.unpack_from(">I",png,offset)[0]
            name, body = png[offset+4:offset+8], png[offset+8:offset+8+length]
            self.assertEqual(struct.unpack_from(">I",png,offset+8+length)[0],zlib.crc32(name+body))
            chunks[name] = body
            offset += length+12
        self.assertEqual(chunks[b"IHDR"],struct.pack(">IIBBBBB",2,2,8,2,0,0,0))
        self.assertEqual(zlib.decompress(chunks[b"IDAT"]),b"\0"+pixels[:6]+b"\0"+pixels[6:])

    def test_invalid_guest_ppm_parameterized(self):
        for data in (b"",b"P3\n1 1\n255\nabc",b"P6\n0 1\n255\n",b"P6\n961 1\n255\n",
                     b"P6\n1 1\n256\nabc",b"P6\n1 1\n255\nab",b"P6\n01 1\n255\nabc"):
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    ppm_to_png(data)
