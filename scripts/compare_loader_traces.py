#!/usr/bin/env python3
"""Require every fixture-derived global mask row, then compare every cell exactly."""

import json
from pathlib import Path

from compare_native_traces import compare_rows
from fixture_protocol import IDENTIFIER, integer
from prepare_static_tilemap import map_dimensions

FIELDS = ("case", "row", "world_x", "world_y", "columns", "cells")


def fixture_rows(path):
    cases, expected = set(), []
    for driver in json.loads(Path(path).read_text())["cases"]:
        name = driver["case"]
        if not IDENTIFIER.fullmatch(name) or name in cases:
            raise ValueError("Invalid/duplicate loader case")
        cases.add(name)
        x, y, columns, rows = map_dimensions(driver)
        if columns <= 0 or rows <= 0 or columns * rows > 4_000_000:
            raise ValueError("Invalid/excessive fixture mask dimensions")
        expected.extend((name, str(row), str(x), str(y + row * 8), str(columns)) for row in range(rows))
    if not expected:
        raise ValueError("Empty loader fixtures")
    return expected


def validate_trace(rows, expected, name):
    for row, text in enumerate(rows, 1):
        f = text.split("\t")
        if len(f) != len(FIELDS) or row > len(expected):
            raise ValueError(f"{name} Row {row}: Invalid field count or extra operation")
        if tuple(f[:5]) != expected[row - 1]:
            raise ValueError(f"{name} Row {row}: Unexpected case/row/geometry; expected {expected[row - 1]}")
        integer(f[1], 0, 2147483647)
        integer(f[2], -2147483648, 2147483647)
        integer(f[3], -2147483648, 2147483647)
        columns = integer(f[4], 1, 2147483647)
        if len(f[5]) != columns or set(f[5]) - {"0", "1"}:
            raise ValueError(f"{name} Row {row}: Invalid mask row data")
    if len(rows) != len(expected):
        raise ValueError(f"{name}: Missing mask rows; expected {len(expected)}, got {len(rows)}")


def compare(reference, native, fixtures):
    expected = fixture_rows(fixtures)
    validate_trace(reference, expected, "reference")
    validate_trace(native, expected, "native")
    return compare_rows(reference, native, FIELDS)
