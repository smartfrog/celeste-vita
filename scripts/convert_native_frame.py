#!/usr/bin/env python3
"""Losslessly convert an already-exported native guest P6 image; never capture a screen."""

import argparse
from pathlib import Path
import struct
import zlib
from native_room_revision import REPO_ROOT


def ppm_to_png(data):
    if len(data) > 960*544*3+64:
        raise ValueError("Native P6 frame exceeds bound")
    try:
        magic, dimensions, maximum, pixels = data.split(b"\n",3)
        width, height = map(int,dimensions.split(b" "))
    except (ValueError,TypeError) as error:
        raise ValueError("Malformed native P6 header") from error
    if magic != b"P6" or maximum != b"255" or dimensions != f"{width} {height}".encode() or not (0 < width <= 960 and 0 < height <= 544):
        raise ValueError("Unsupported native P6 format/dimensions")
    if len(pixels) != width*height*3:
        raise ValueError("Wrong native P6 pixel length")
    def chunk(name,body):
        return struct.pack(">I",len(body))+name+body+struct.pack(">I",zlib.crc32(name+body))
    rows = b"".join(b"\0"+pixels[y*width*3:(y+1)*width*3] for y in range(height))
    return (b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",width,height,8,2,0,0,0))+
            chunk(b"IDAT",zlib.compress(rows))+chunk(b"IEND",b""))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ppm",type=Path,required=True)
    parser.add_argument("--png",type=Path,required=True)
    args = parser.parse_args()
    if any(not path.resolve().is_relative_to(REPO_ROOT / ".audit/native-room-vita") for path in (args.ppm,args.png)):
        parser.error("Native frame input/output must remain under the private diagnostic evidence directory")
    if args.ppm.stat().st_size > 960*544*3+64:
        parser.error("Native P6 frame exceeds bound")
    png = ppm_to_png(args.ppm.read_bytes())
    with args.png.open("xb") as output:
        if output.write(png) != len(png):
            raise OSError("Native PNG conversion write was incomplete")
