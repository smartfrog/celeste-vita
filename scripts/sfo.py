"""Shared standard-library SFO metadata reader for private package inspection."""

import struct


def parse_sfo(data):
    magic, _, keys, values, count = struct.unpack_from("<5I", data)
    if magic != 0x46535000 or 20 + count * 16 > keys or not keys < values <= len(data):
        raise ValueError("Invalid SFO header")
    result = {}
    for index in range(count):
        key_offset, kind, size, capacity, value_offset = struct.unpack_from("<HHIII", data, 20 + index * 16)
        if keys + key_offset >= values or size > capacity or values + value_offset + capacity > len(data):
            raise ValueError(f"Invalid SFO entry: {index}")
        key = data[keys + key_offset:values].split(b"\0", 1)[0].decode()
        value = data[values + value_offset:values + value_offset + size]
        if kind == 0x404:
            value = struct.unpack("<I", value)[0]
        elif kind == 0x204:
            value = value.rstrip(b"\0").decode()
        else:
            value = value.hex()
        if key in result:
            raise ValueError(f"Duplicate SFO key: {key}")
        result[key] = value
    return result
