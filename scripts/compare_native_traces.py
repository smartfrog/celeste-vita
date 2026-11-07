#!/usr/bin/env python3
"""Compare raw fields, reporting the first divergent fixture operation/field."""

import argparse
from itertools import zip_longest
from pathlib import Path


FIELDS = ("case", "step", "event", "result", "x", "y", "remainder_x", "remainder_y",
          "hit", "pusher", "direction_x", "direction_y", "moved_x", "moved_y", "target_x", "target_y")


def compare(reference, native):
    if not reference or not native:
        raise ValueError("Traces must not be empty")
    for row, (expected, actual) in enumerate(zip_longest(reference, native), start=1):
        if expected is None or actual is None:
            raise ValueError(f"Row {row}: trace length mismatch; reference={expected!r}, native={actual!r}")
        left, right = expected.split("\t"), actual.split("\t")
        if len(left) != len(FIELDS) or len(right) != len(FIELDS):
            raise ValueError(f"Row {row}: expected {len(FIELDS)} TSV fields")
        for field, expected_value, actual_value in zip(FIELDS, left, right):
            if expected_value != actual_value:
                raise ValueError(f"Row {row}, {left[0]} step {left[1]} {left[2]}, {field}: "
                                 f"reference={expected_value}, native={actual_value}")
    return len(reference)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("native", type=Path)
    args = parser.parse_args()
    try:
        count = compare(args.reference.read_text().splitlines(), args.native.read_text().splitlines())
    except ValueError as error:
        parser.exit(1, str(error) + "\n")
    print(f"MATCH: {count} trace rows, {len(FIELDS)} exact fields per row (float32 bits, no epsilon)")


if __name__ == "__main__":
    main()
