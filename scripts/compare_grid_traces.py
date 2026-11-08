#!/usr/bin/env python3
"""Validate Grid fixture grammar and ordered operation coverage before exact equality."""

import argparse
from pathlib import Path
import struct

from compare_native_traces import FIELDS, Operation, compare_rows, validate_trace
from fixture_protocol import IDENTIFIER, integer, float_bits

DEFAULT_FIXTURES = Path(__file__).resolve().parents[1] / "tests/native/grid.fixtures"


def scalar(text, minimum=None):
    value = struct.unpack(">f", bytes.fromhex(float_bits(text)))[0]
    if minimum is not None and value < minimum:
        raise ValueError("Negative dimension")
    return value


def grid_fields(f):
    if len(f) != 12:
        raise ValueError("Expected 12 Grid fields")
    integer(f[1], 1, 2147483647)
    for value in f[2:6]:
        scalar(value)
    if scalar(f[6]) <= 0 or scalar(f[7]) <= 0:
        raise ValueError("Cell sizes must be positive")
    columns, rows = (integer(v, 0, 2147483647) for v in f[8:10])
    cells = "" if f[10] == "-" else f[10]
    if len(cells) != columns * rows or set(cells) - {"0", "1"}:
        raise ValueError("Grid dimensions/data mismatch")
    integer(f[11], 0, 1)


def fixture_operations(path):
    operations, cases = [], set()
    case, step, bodies, actor = None, 0, set(), False
    for line, text in enumerate(Path(path).read_text().splitlines(), 1):
        f = text.split()
        if not f or f[0].startswith("#"):
            continue
        try:
            op = f[0]
            if op == "case":
                if len(f) != 2 or not IDENTIFIER.fullmatch(f[1]) or f[1] in cases or (case is not None and not step):
                    raise ValueError("Invalid/duplicate/empty case")
                case, step, bodies, actor = f[1], 0, set(), False
                cases.add(case)
            elif case is None:
                raise ValueError("Operation before case")
            elif op == "actor":
                if len(f) != 10:
                    raise ValueError("Invalid actor fields")
                for i, value in enumerate(f[1:7], 1):
                    scalar(value, 0 if i in (3, 4) else None)
                for value in f[7:]:
                    integer(value, 0, 1)
                actor = True
            elif op in {"grid", "solid"}:
                if op == "grid":
                    grid_fields(f)
                else:
                    if len(f) != 10:
                        raise ValueError("Invalid solid fields")
                    integer(f[1], 1, 2147483647)
                    for i, value in enumerate(f[2:8], 2):
                        scalar(value, 0 if i in (4, 5) else None)
                    for value in f[8:]:
                        integer(value, 0, 1)
                if step or f[1] in bodies:
                    raise ValueError("Late/duplicate static body")
                bodies.add(f[1])
            elif op in {"Q", "H", "V", "HX", "VX"}:
                if not actor or len(f) != (3 if op == "Q" else 4):
                    raise ValueError("Missing actor or invalid operation fields")
                if op == "Q":
                    scalar(f[1]); scalar(f[2])
                    callback, pusher = "none", "-1"
                else:
                    integer(f[1], -2147483648, 2147483647) if op.endswith("X") else scalar(f[1])
                    callback, pusher = f[2:4]
                    if callback not in {"none", "record"} or (pusher != "-1" and pusher not in bodies):
                        raise ValueError("Invalid callback/pusher")
                step += 1
                operations.append(Operation(case, step, "query" if op == "Q" else "return", callback, pusher, frozenset(bodies)))
            else:
                raise ValueError("Unknown Grid operation")
        except ValueError as error:
            raise ValueError(f"Fixture {path} line {line}: {error}") from error
    if not operations or not step:
        raise ValueError("Empty fixture/case")
    return operations


def compare(reference, native, fixtures=DEFAULT_FIXTURES):
    expected = fixture_operations(fixtures)
    validate_trace(reference, expected, "reference")
    validate_trace(native, expected, "native")
    return compare_rows(reference, native, FIELDS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("native", type=Path)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    args = parser.parse_args()
    try:
        rows = compare(args.reference.read_text().splitlines(), args.native.read_text().splitlines(), args.fixtures)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")
    print(f"MATCH: {rows} rows, {len(FIELDS)} exact fields per row")


if __name__ == "__main__":
    main()
