"""Bounded host-only atlas metadata/RLE reader; retain requested RGBA crops only."""

import struct


class MetadataReader:
    def __init__(self, data):
        self.data, self.offset = data, 0

    def take(self, length):
        if length < 0 or self.offset + length > len(self.data):
            raise ValueError("Truncated atlas metadata")
        result = self.data[self.offset:self.offset + length]
        self.offset += length
        return result

    def number(self, format):
        return struct.unpack(format, self.take(struct.calcsize(format)))

    def string(self):
        length = 0
        for shift in range(0, 35, 7):
            value = self.take(1)[0]
            length |= (value & 127) << shift
            if not value & 128:
                if length > 4096:
                    raise ValueError("Excessive atlas string")
                try:
                    return self.take(length).decode("utf-8").replace("\\", "/")
                except UnicodeDecodeError as error:
                    raise ValueError("Invalid atlas string") from error
        raise ValueError("Invalid 7-bit string length")


def atlas_metadata(data):
    reader = MetadataReader(data)
    if reader.number("<i")[0] != 5:
        raise ValueError("Unsupported atlas metadata version")
    reader.string()
    reader.number("<i")
    sheets = reader.number("<h")[0]
    if not 1 <= sheets <= 16:
        raise ValueError("Invalid atlas sheet count")
    result = {}
    for _ in range(sheets):
        sheet = reader.string()
        count = reader.number("<h")[0]
        if not sheet or not 0 <= count <= 16000:
            raise ValueError("Invalid atlas sheet")
        for _ in range(count):
            name = reader.string()
            rect = reader.number("<8h")
            x, y, width, height, _, _, frame_width, frame_height = rect
            if (not name or name in result or min(x, y) < 0 or min(width, height, frame_width, frame_height) <= 0
                    or x + width > 4096 or y + height > 4096):
                raise ValueError("Invalid atlas rectangle/reference")
            result[name] = (sheet, *rect)
    if reader.offset != len(data):
        if reader.string() != "LINKS":
            raise ValueError("Unexpected atlas metadata trailer")
        count = reader.number("<h")[0]
        if count < 0:
            raise ValueError("Invalid atlas link count")
        for _ in range(count):
            alias, target = reader.string(), reader.string()
            if not alias or alias in result or target not in result:
                raise ValueError("Invalid atlas link")
            result[alias] = result[target]
    if reader.offset != len(data):
        raise ValueError("Trailing atlas metadata")
    return result


def decode_crops(data, crops, audit=None):
    if len(data) < 9:
        raise ValueError("Truncated texture header")
    width, height, alpha = struct.unpack_from("<iiB", data)
    if not 1 <= width <= 4096 or not 1 <= height <= 4096:
        raise ValueError("Invalid texture dimensions")
    buffers = {}
    for name, (x, y, w, h) in crops.items():
        if min(x, y) < 0 or min(w, h) <= 0 or x + w > width or y + h > height:
            raise ValueError("Crop outside texture")
        buffers[name] = bytearray(w * h * 4)
    position, offset, total = 0, 9, width * height
    while position < total:
        if offset + 2 > len(data):
            raise ValueError("Truncated texture run")
        run = data[offset]
        a = data[offset + 1] if alpha == 1 else 255
        length = (2 if a == 0 else 5) if alpha == 1 else 4
        if run == 0 or position + run > total or offset + length > len(data):
            raise ValueError("Invalid/truncated texture run")
        if a == 0:
            pixel = bytes(4)
        else:
            b, g, r = data[offset + length - 3:offset + length]
            pixel = bytes((r, g, b, a))
        if audit is not None and 0 < a < 255 and "partial_alpha" not in audit:
            audit["partial_alpha"] = {"sheet_pixel": [position % width, position // width], "rgba": list(pixel), "run_offset": offset}
        end = position + run
        cursor = position
        while cursor < end:
            row, column = divmod(cursor, width)
            row_end = min(end, (row + 1) * width)
            for name, (x, y, w, h) in crops.items():
                if y <= row < y + h:
                    left, right = max(column, x), min(row_end - row * width, x + w)
                    if left < right:
                        start = ((row - y) * w + left - x) * 4
                        buffers[name][start:start + (right - left) * 4] = pixel * (right - left)
            cursor = row_end
        position, offset = end, offset + length
    if offset != len(data):
        raise ValueError("Trailing texture bytes")
    return {name: bytes(buffer) for name, buffer in buffers.items()}


def extrude(rgba, width, height, texture_width, texture_height):
    if len(rgba) != width * height * 4 or min(width, height) <= 0 or texture_width < width + 2 or texture_height < height + 2:
        raise ValueError("Invalid extruded texture dimensions/data")
    output = bytearray(texture_width * texture_height * 4)
    for y in range(height + 2):
        row = min(height - 1, max(0, y - 1))
        source = rgba[row * width * 4:(row + 1) * width * 4]
        source = source[:4] + source + source[-4:]
        output[y * texture_width * 4:y * texture_width * 4 + len(source)] = source
    return bytes(output)


def plan_rectangles(rectangles, page_width, page_height, maximum_pages):
    if not rectangles or min(page_width, page_height, maximum_pages) <= 0:
        raise ValueError("Invalid bounded rectangle plan")
    for name, (width, height) in rectangles.items():
        if not name or min(width, height) <= 0 or width + 2 > page_width or height + 2 > page_height:
            raise ValueError(f"Rectangle {name}: {width}x{height} exceeds {page_width}x{page_height} with border")
    page = x = y = row_height = 0
    layout = {}
    for name, (width, height) in sorted(rectangles.items(), key=lambda entry: (-entry[1][1], -entry[1][0], entry[0])):
        if x + width + 2 > page_width:
            x, y, row_height = 0, y + row_height, 0
        if y + height + 2 > page_height:
            page += 1
            if page >= maximum_pages:
                raise ValueError(f"Rectangle {name}: {width}x{height} exceeds {maximum_pages}-page budget at {page_width}x{page_height}")
            x = y = row_height = 0
        layout[name] = page, x + 1, y + 1
        x, row_height = x + width + 2, max(row_height, height + 2)
    return page + 1, layout


def blit_extruded(page, page_width, page_height, rgba, width, height, x, y):
    if len(page) != page_width * page_height * 4 or not (
            1 <= x <= page_width - width - 1 and 1 <= y <= page_height - height - 1):
        raise ValueError("Extruded crop outside actual page bounds")
    padded = extrude(rgba, width, height, width + 2, height + 2)
    for dy in range(height + 2):
        start = dy * (width + 2) * 4
        target = ((y - 1 + dy) * page_width + x - 1) * 4
        page[target:target + (width + 2) * 4] = padded[start:start + (width + 2) * 4]
