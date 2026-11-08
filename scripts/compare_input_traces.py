#!/usr/bin/env python3
"""Validate sampled-button operation coverage before exact field comparison."""

import argparse
from dataclasses import dataclass
from pathlib import Path

from compare_native_traces import compare_rows
from fixture_protocol import IDENTIFIER, integer, float_bits

FIELDS = ("case", "step", "phase", "operation", "buffer_time", "first", "multi",
          "buffer_counter", "repeat_counter", "can_repeat", "consumed", "repeating",
          "held", "raw_pressed", "raw_released", "disabled", "debug", "check", "pressed", "released", "delta")
DEFAULT_FIXTURES = Path(__file__).resolve().parents[1] / "tests/native/input.fixtures"
COUNTS = {"sample": 6, "tick": 2, "repeat": 2, "repeat_pair": 3, "buffer": 2,
          "consume_buffer": 1, "consume_press": 1, "query": 1}


@dataclass(frozen=True)
class Snapshot:
    case: str
    step: int
    phase: str
    operation: str
    configuration: tuple
    sample: tuple
    delta: str


def fixture_operations(path):
    snapshots, cases = [], set()
    case, step = None, 0
    for line, text in enumerate(Path(path).read_text().splitlines(), 1):
        fields = text.split()
        if not fields or fields[0].startswith("#"):
            continue
        try:
            kind = fields[0]
            if kind == "case":
                if len(fields) != 3 or not IDENTIFIER.fullmatch(fields[1]) or fields[1] in cases:
                    raise ValueError("Invalid/duplicate case")
                if case is not None and step == 0:
                    raise ValueError("Case has no operations")
                case, step = fields[1], 0
                cases.add(case)
                configuration = (float_bits(fields[2]), "00000000", "00000000")
                sample = ("0",) * 5
                delta = "00000000"
                continue
            if case is None:
                raise ValueError("Operation before case")
            if kind not in COUNTS or len(fields) != COUNTS[kind]:
                raise ValueError("Unknown command/invalid field count")
            if kind == "tick":
                delta = float_bits(fields[1])
            step += 1
            snapshots.append(Snapshot(case, step, "before", kind, configuration, sample, delta))
            if kind == "sample":
                for value in fields[1:]:
                    integer(value, 0, 1)
                sample = tuple(fields[1:])
            elif kind == "buffer":
                configuration = (float_bits(fields[1]), *configuration[1:])
            elif kind in {"repeat", "repeat_pair"}:
                first = float_bits(fields[1])
                multi = first if kind == "repeat" else float_bits(fields[2])
                configuration = (configuration[0], first, multi)
            snapshots.append(Snapshot(case, step, "after", kind, configuration, sample, delta))
        except ValueError as error:
            raise ValueError(f"Fixture {path} line {line}: {error}") from error
    if not snapshots or step == 0:
        raise ValueError("Fixture/case has no operations")
    return snapshots


def validate_trace(rows, snapshots, name):
    for row, text in enumerate(rows, 1):
        try:
            fields = text.split("\t")
            if len(fields) != len(FIELDS):
                raise ValueError(f"Expected {len(FIELDS)} TSV fields")
            if row > len(snapshots):
                raise ValueError("Unexpected row after final operation")
            snapshot = snapshots[row - 1]
            if fields[:4] != [snapshot.case, str(snapshot.step), snapshot.phase, snapshot.operation]:
                raise ValueError(f"Unexpected operation/phase {fields[:4]}; expected {snapshot}")
            for index in (*range(4, 9), 20):
                float_bits("@" + fields[index])
            for index in range(9, 20):
                integer(fields[index], 0, 1)
            if tuple(fields[4:7]) != snapshot.configuration:
                raise ValueError("Configuration fields do not match fixture")
            if tuple(fields[12:17]) != snapshot.sample:
                raise ValueError("Sample fields do not match fixture")
            if fields[20] != snapshot.delta:
                raise ValueError("Delta field does not match fixture")
        except ValueError as error:
            raise ValueError(f"{name} Row {row}: {error}") from error
    if len(rows) != len(snapshots):
        raise ValueError(f"{name}: Missing operation/phase; expected {len(snapshots)} rows, got {len(rows)}")


def compare(reference, native, fixtures=DEFAULT_FIXTURES):
    snapshots = fixture_operations(fixtures)
    validate_trace(reference, snapshots, "reference")
    validate_trace(native, snapshots, "native")
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
