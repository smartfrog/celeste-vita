"""Pure bounded private crop packing and exclusive, pinned file IO."""

import hashlib
import os
from pathlib import Path

from native_room_textures import blit_extruded, plan_rectangles


def verify_pin(pin):
    path = Path(pin['path'])
    if path.stat().st_size != pin['bytes'] or not 0 <= pin['bytes'] <= 32 * 1024 * 1024:
        raise ValueError(f"Size pin failed: {path}")
    data = path.read_bytes()
    if len(data) != pin['bytes'] or hashlib.sha256(data).hexdigest() != pin['sha256']:
        raise ValueError(f"SHA-256 pin failed: {path}")
    return data


def write_new(path, data):
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def pack_crops(crops):
    if not 1 <= len(crops) <= 26:
        raise ValueError("Private completion pack requires 1..26 crops")
    count, layout = plan_rectangles({key: (w, h) for key, (w, h, _) in crops.items()}, 128, 128, 2)
    for key, (width, height, rgba) in crops.items():
        if len(rgba) != width * height * 4:
            raise ValueError(f"Short or oversized crop pixels: {key}")
    pages = [bytearray(128 * 128 * 4) for _ in range(count)]
    for key, (width, height, rgba) in crops.items():
        page, x, y = layout[key]
        blit_extruded(pages[page], 128, 128, rgba, width, height, x, y)
    return [bytes(page) for page in pages], layout
