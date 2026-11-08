"""Canonical scalar grammar shared by synthetic source-oracle fixtures."""

import re
import struct

from compare_native_traces import FLOAT_BITS

IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")
INTEGER = re.compile(r"(?:0|-?[1-9][0-9]*)\Z")


def integer(value, minimum, maximum):
    if not INTEGER.fullmatch(value) or not minimum <= int(value) <= maximum:
        raise ValueError(f"Invalid integer {value!r}")
    return int(value)


def float_bits(value):
    if value.startswith("@"):
        bits = value[1:]
    else:
        try:
            bits = struct.pack(">f", float(value)).hex()
        except (ValueError, OverflowError) as error:
            raise ValueError(f"Invalid float32 {value!r}") from error
    if not FLOAT_BITS.fullmatch(bits) or int(bits, 16) & 0x7f800000 == 0x7f800000:
        raise ValueError(f"Invalid finite float32 bits {bits!r}")
    return bits
