"""Bounded offline BinaryPacker reader, reused from the private map inventory."""

import io
import struct


class Reader:
    def __init__(self, data):
        self.stream = io.BytesIO(data)
        self.strings = []

    def read(self, size):
        data = self.stream.read(size)
        if len(data) != size:
            raise ValueError("Truncated map")
        return data

    def number(self, kind):
        return struct.unpack("<" + kind, self.read(struct.calcsize("<" + kind)))[0]

    def string(self):
        size = 0
        for shift in range(0, 35, 7):
            byte = self.number("B")
            size |= (byte & 127) << shift
            if byte < 128:
                if size > 16 * 1024 * 1024:
                    raise ValueError("Map string exceeds preparation bound")
                return self.read(size).decode("utf-8")
        raise ValueError("Invalid .NET string length")

    def lookup(self):
        index = self.number("h")
        if not 0 <= index < len(self.strings):
            raise ValueError(f"Invalid map string index: {index}")
        return self.strings[index]

    def value(self):
        kind = self.number("B")
        if kind == 0:
            value = self.number("B")
            if value not in (0, 1):
                raise ValueError("Invalid boolean")
            return bool(value)
        if kind in (1, 2, 3, 4):
            return self.number({1: "B", 2: "h", 3: "i", 4: "f"}[kind])
        if kind == 5:
            return self.lookup()
        if kind == 6:
            return self.string()
        if kind == 7:
            count = self.number("h")
            if count < 0 or count % 2:
                raise ValueError("Invalid run-length byte count")
            data = self.read(count)
            return "".join(chr(data[i + 1]) * data[i] for i in range(0, len(data), 2))
        raise ValueError(f"Unsupported attribute type: {kind}")

    def element(self, depth=0):
        if depth > 100:
            raise ValueError("Map nesting exceeds preparation bound")
        name = self.lookup()
        attributes = {}
        for _ in range(self.number("B")):
            key = self.lookup()
            if key in attributes:
                raise ValueError(f"Duplicate attribute: {key}")
            attributes[key] = self.value()
        count = self.number("h")
        if count < 0:
            raise ValueError("Negative child count")
        return {"name": name, "attributes": attributes, "children": [self.element(depth + 1) for _ in range(count)]}

    def map(self):
        if self.string() != "CELESTE MAP":
            raise ValueError("Unexpected map signature")
        package = self.string()
        count = self.number("h")
        if count < 0:
            raise ValueError("Negative string lookup count")
        self.strings = [self.string() for _ in range(count)]
        root = self.element()
        if self.stream.read(1):
            raise ValueError("Unexpected trailing map bytes")
        return package, root
