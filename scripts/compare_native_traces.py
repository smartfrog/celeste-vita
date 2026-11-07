#!/usr/bin/env python3
"""Compare raw fields, reporting the first divergent fixture operation/field."""

import argparse
from dataclasses import dataclass
from itertools import zip_longest
from pathlib import Path
import re


FIELDS = ("case", "step", "event", "result", "x", "y", "remainder_x", "remainder_y",
          "hit", "pusher", "direction_x", "direction_y", "moved_x", "moved_y", "target_x", "target_y")
DEFAULT_FIXTURES = Path(__file__).resolve().parents[1] / "tests/native/movement.fixtures"
POSITIVE_INTEGER = re.compile(r"[1-9][0-9]*\Z")
FLOAT_BITS = re.compile(r"[0-9a-f]{8}\Z")
CALLBACK_MODES = {"none", "record", "mutate", "reenterH", "reenterV"}
FIELD_COUNTS = {"case": 2, "actor": 10, "solid": 10, "jump": 10, "self": 1,
                "H": 4, "V": 4, "HX": 4, "VX": 4, "Q": 3, "O": 3}


@dataclass(frozen=True)
class Operation:
    case: str
    step: int
    terminal: str
    callback: str
    pusher: str
    bodies: frozenset[str]

    def event_patterns(self):
        if self.terminal == "query":
            return [("query",)]
        patterns = [("return",)]
        if self.callback in {"record", "mutate"}:
            patterns.append(("callback", "return"))
        elif self.callback in {"reenterH", "reenterV"}:
            patterns.extend([("callback", "reentry", "return"), ("callback", "callback", "reentry", "return")])
        return patterns


def fixture_operations(path):
    operations, cases = [], set()
    case, step, bodies, solids = None, 0, set(), set()
    for line, text in enumerate(Path(path).read_text().splitlines(), start=1):
        fields = text.split()
        if not fields or fields[0].startswith("#"):
            continue
        kind = fields[0]
        context = f"Fixture {path} line {line}"
        if kind not in FIELD_COUNTS or len(fields) != FIELD_COUNTS[kind]:
            raise ValueError(f"{context}: unknown operation or invalid field count")
        if kind == "case":
            case = fields[1]
            if case in cases:
                raise ValueError(f"{context}: duplicate case {case}")
            cases.add(case)
            step, bodies, solids = 0, set(), set()
        elif case is None:
            raise ValueError(f"{context}: operation before case")
        elif kind in {"solid", "jump"}:
            identity = fields[1]
            if not POSITIVE_INTEGER.fullmatch(identity) or int(identity) > 2147483647 or identity in bodies:
                raise ValueError(f"{context}: invalid or duplicate body ID {identity}")
            bodies.add(identity)
            if kind == "solid":
                solids.add(identity)
        elif kind in {"H", "V", "HX", "VX", "Q", "O"}:
            step += 1
            terminal = "query" if kind in {"Q", "O"} else "return"
            callback, pusher = ("none", "-1") if terminal == "query" else fields[2:4]
            if callback not in CALLBACK_MODES or (pusher != "-1" and pusher not in solids):
                raise ValueError(f"{context}: invalid callback mode or pusher ID")
            operations.append(Operation(case, step, terminal, callback, pusher, frozenset(bodies)))
    if not operations:
        raise ValueError(f"Fixture {path}: no trace-producing operations")
    return operations


def validate_trace(rows, operations, name):
    operation_index, events = 0, []
    callback_hits = set()
    for row, text in enumerate(rows, start=1):
        fields = text.split("\t")
        context = f"{name} Row {row}"
        if len(fields) != len(FIELDS):
            raise ValueError(f"{context}: expected {len(FIELDS)} TSV fields")
        case, step, event, result = fields[:4]
        if not POSITIVE_INTEGER.fullmatch(step):
            raise ValueError(f"{context}: invalid step {step!r}")
        if event not in {"callback", "reentry", "return", "query"}:
            raise ValueError(f"{context}: invalid event {event!r}")
        if result not in ({"-"} if event == "callback" else {"0", "1"}):
            raise ValueError(f"{context}: invalid {event} result {result!r}")
        for index in [4, 5, 6, 7, 10, 11, 12, 13, 14, 15]:
            value = fields[index]
            if not FLOAT_BITS.fullmatch(value) or int(value, 16) & 0x7f800000 == 0x7f800000:
                raise ValueError(f"{context}: invalid finite float32 bits for {FIELDS[index]}: {value!r}")
        for index in [8, 9]:
            value = fields[index]
            if value != "-1" and (not POSITIVE_INTEGER.fullmatch(value) or int(value) > 2147483647):
                raise ValueError(f"{context}: invalid identity for {FIELDS[index]}: {value!r}")
        if operation_index == len(operations):
            raise ValueError(f"{context}: unexpected operation {case} step {step} after final terminal")
        operation = operations[operation_index]
        if (case, step) != (operation.case, str(operation.step)):
            raise ValueError(f"{context}: unexpected operation {case} step {step}; expected "
                             f"{operation.case} step {operation.step} {operation.terminal} terminal")
        events.append(event)
        if not any(pattern[:len(events)] == tuple(events) for pattern in operation.event_patterns()):
            raise ValueError(f"{context}: invalid callback/reentry/terminal event order for {case} step {step}: {events}")
        hit, pusher = fields[8:10]
        if hit != "-1" and hit not in operation.bodies:
            raise ValueError(f"{context}: foreign hit identity {hit} in {case} step {step}")
        if event == "callback":
            if hit == "-1" or pusher != operation.pusher:
                raise ValueError(f"{context}: callback hit/pusher identity does not match fixture operation")
            if hit in callback_hits:
                raise ValueError(f"{context}: repeated callback hit {hit} in {case} step {step}")
            callback_hits.add(hit)
        else:
            if pusher != "-1" or any(value != "00000000" for value in fields[10:]):
                raise ValueError(f"{context}: non-callback event must have default collision payload")
            if event == "query":
                if (result == "1") != (hit != "-1"):
                    raise ValueError(f"{context}: query result and hit identity disagree")
            elif hit != "-1":
                raise ValueError(f"{context}: {event} must have default hit identity")
            if event == "reentry" and (result == "1") != (events.count("callback") == 2):
                raise ValueError(f"{context}: nested callback and reentry result disagree")
        if event == operation.terminal:
            if event == "return" and operation.callback != "none" and (result == "1") != ("callback" in events):
                raise ValueError(f"{context}: callback presence and terminal return result disagree")
            operation_index += 1
            events = []
            callback_hits.clear()
    if operation_index != len(operations):
        operation = operations[operation_index]
        raise ValueError(f"{name}: Missing operation/terminal {operation.case} step {operation.step} {operation.terminal}")


def compare(reference, native, fixtures=DEFAULT_FIXTURES):
    if not reference or not native:
        raise ValueError("Traces must not be empty")
    operations = fixture_operations(fixtures)
    validate_trace(reference, operations, "reference")
    validate_trace(native, operations, "native")
    return compare_rows(reference, native, FIELDS)


def compare_rows(reference, native, fields):
    for row, (expected, actual) in enumerate(zip_longest(reference, native), start=1):
        if expected is None or actual is None:
            raise ValueError(f"Row {row}: trace length mismatch; reference={expected!r}, native={actual!r}")
        left, right = expected.split("\t"), actual.split("\t")
        for field, expected_value, actual_value in zip(fields, left, right):
            if expected_value != actual_value:
                raise ValueError(f"Row {row}, {left[0]} step {left[1]} {left[2]}, {field}: "
                                 f"reference={expected_value}, native={actual_value}")
    return len(reference)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("native", type=Path)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    args = parser.parse_args()
    try:
        count = compare(args.reference.read_text().splitlines(), args.native.read_text().splitlines(), args.fixtures)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")
    print(f"MATCH: {count} trace rows, {len(FIELDS)} exact fields per row (float32 bits, no epsilon)")


if __name__ == "__main__":
    main()
