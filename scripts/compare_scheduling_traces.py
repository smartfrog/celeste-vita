#!/usr/bin/env python3
"""Validate the scheduling fixture protocol and compare exact observable fields."""

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import struct

from compare_native_traces import FLOAT_BITS, compare_rows

FIELDS = ("case", "step", "event", "detail", "state", "previous", "changed", "locked",
          "active", "finished", "wait", "depth", "ended", "removals", "raw", "delta", "raw_delta")
DEFAULT_FIXTURES = Path(__file__).resolve().parents[1] / "tests/native/scheduling.fixtures"
IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")
INTEGER = re.compile(r"(?:0|-?[1-9][0-9]*)\Z")
COUNTS = {"construct": 2, "replace": 2, "cancel": 1, "tick": 3, "snapshot": 1,
          "raw": 2, "active": 2, "remove": 2, "lock": 2, "set": 2, "force": 2,
          "added": 2, "entity_added": 1}


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


def validate_action(spec, scripts, count, role):
    if spec == "-":
        return
    tokens = spec.split(",")
    for token in tokens:
        parts = token.split(":")
        kind = parts[0]
        if token in {"record", "cancel", "throw"}:
            continue
        if len(parts) != 2:
            raise ValueError(f"Invalid callback action {token}")
        if kind in {"set", "force", "return"}:
            integer(parts[1], 0, count - 1)
        elif kind == "lock":
            integer(parts[1], 0, 1)
        elif kind in {"replace", "script"} and parts[1] in scripts:
            pass
        else:
            raise ValueError(f"Invalid callback action {token}")
        if kind in {"return", "script"} and (token != tokens[-1] or kind != {"update": "return", "factory": "script"}.get(role)):
            raise ValueError(f"Invalid {kind} for callback role {role}")
    if role == "update" and not (tokens[-1].startswith("return:") or tokens[-1] == "throw"):
        raise ValueError("Update callback requires a return or throw")
    if role == "factory" and not (tokens[-1].startswith("script:") or tokens[-1] == "throw"):
        raise ValueError("Factory callback requires a script or throw")


def validate_script(tokens, scripts, count):
    for token in tokens:
        if token in {"n", "done", "throw"}:
            continue
        parts = token.split(":")
        kind = parts[0]
        if kind == "i" and len(parts) == 2:
            integer(parts[1], -2147483648, 2147483647)
        elif kind == "f" and len(parts) == 2:
            float_bits(parts[1])
        elif kind == "child" and len(parts) == 2 and parts[1] in scripts:
            pass
        elif kind == "cancel" and len(parts) == 2 and parts[1] in {"n", "done"}:
            pass
        elif kind == "replace" and len(parts) == 3 and parts[1] in scripts and parts[2] in {"n", "done"}:
            pass
        elif kind == "set" and len(parts) == 3 and parts[2] in {"n", "done"}:
            integer(parts[1], 0, count - 1)
        else:
            raise ValueError(f"Invalid script token {token}")


@dataclass(frozen=True)
class Operation:
    case: str
    step: int
    events: tuple
    mode: str
    count: int
    delta: str
    raw_delta: str


def fixture_operations(path):
    operations, cases = [], set()
    case, step, scripts, callbacks = None, 0, {}, {}
    delta = raw_delta = "00000000"
    for line, text in enumerate(Path(path).read_text().splitlines(), 1):
        fields = text.split()
        if not fields or fields[0].startswith("#"):
            continue
        try:
            kind = fields[0]
            if kind == "case":
                if len(fields) != 4 or not IDENTIFIER.fullmatch(fields[1]) or fields[1] in cases or fields[2] not in {"C", "M"}:
                    raise ValueError("Invalid/duplicate case")
                case, mode = fields[1:3]
                count = integer(fields[3], 0 if mode == "C" else 1, 1 if mode == "C" else 2147483647)
                cases.add(case)
                step, scripts, callbacks = 0, {}, {}
                delta = raw_delta = "00000000"
                continue
            if case is None:
                raise ValueError("Operation before case")
            if kind == "script":
                if len(fields) < 2 or not IDENTIFIER.fullmatch(fields[1]) or fields[1] in scripts:
                    raise ValueError("Invalid/duplicate script")
                scripts[fields[1]] = fields[2:]
                validate_script(fields[2:], scripts, count if mode == "M" else 0)
                continue
            if kind == "callbacks":
                if mode != "M" or len(fields) != 6:
                    raise ValueError("Invalid callbacks declaration")
                index = integer(fields[1], 0, count - 1)
                for role, spec in zip(("update", "factory", "begin", "end"), fields[2:]):
                    validate_action(spec, scripts, count, role)
                    callbacks[(role, str(index))] = spec != "-"
                continue
            separator = fields.index("=>") if "=>" in fields else len(fields)
            command, expectation = fields[:separator], fields[separator + 1:]
            if kind not in COUNTS or len(command) != COUNTS[kind]:
                raise ValueError("Unknown command/invalid field count")
            if kind in {"construct", "replace"} and command[1] not in scripts:
                raise ValueError("Unknown script")
            if kind == "construct" and mode != "C":
                raise ValueError("Construct is coroutine-only")
            if kind in {"lock", "set", "force", "added", "entity_added"} and mode != "M":
                raise ValueError("Machine-only command")
            if kind in {"raw", "active", "remove", "lock", "added"}:
                integer(command[1], 0, 1)
            if kind in {"set", "force"}:
                integer(command[1], 0, count - 1)
            if kind == "tick":
                delta, raw_delta = map(float_bits, command[1:])
            events = []
            terminal = "throw" if expectation and expectation[-1] == "!" else "return"
            if terminal == "throw":
                expectation = expectation[:-1]
                if kind not in {"tick", "set", "force", "added", "entity_added"}:
                    raise ValueError("Command cannot raise a synthetic callback exception")
            for event in expectation:
                role, _, detail = event.partition(":")
                if role == "move":
                    identity, _, offset = detail.partition(":")
                    if kind != "tick" or identity not in scripts:
                        raise ValueError("Invalid expected move")
                    integer(offset, 0, len(scripts[identity]))
                elif role == "remove":
                    if kind != "tick" or detail != "-":
                        raise ValueError("Invalid expected removal")
                elif role not in {"begin", "end", "factory", "update"} or not callbacks.get((role, detail)):
                    raise ValueError("Undeclared expected callback")
                elif kind not in {"set", "force", "added", "entity_added", "tick"} or (role == "update" and kind != "tick"):
                    raise ValueError("Invalid callback for command")
                events.append((role, detail))
            roles = [event[0] for event in events]
            if roles.count("move") > 1 or roles.count("update") > 1 or roles.count("remove") > 1:
                raise ValueError("Scheduling tick permits at most one update, move and removal")
            if "update" in roles and roles[0] != "update":
                raise ValueError("State update callback must be the first tick event")
            if "remove" in roles and (roles[-1] != "remove" or "move" not in roles or terminal == "throw"):
                raise ValueError("Removal must follow a completing move without an exception")
            events.append((terminal, kind))
            step += 1
            operations.append(Operation(case, step, tuple(events), mode, count, delta, raw_delta))
        except (ValueError, IndexError) as error:
            raise ValueError(f"Fixture {path} line {line}: {error}") from error
    if not operations:
        raise ValueError("Fixture has no trace-producing operations")
    return operations


def validate_trace(rows, operations, name):
    expected = [(operation, event) for operation in operations for event in operation.events]
    for row, text in enumerate(rows, 1):
        context = f"{name} Row {row}"
        fields = text.split("\t")
        try:
            if len(fields) != len(FIELDS):
                raise ValueError(f"Expected {len(FIELDS)} TSV fields")
            if row > len(expected):
                raise ValueError("Unexpected operation/event after final terminal")
            operation, event = expected[row - 1]
            if fields[:4] != [operation.case, str(operation.step), *event]:
                raise ValueError(f"Unexpected operation/event {fields[:4]}; expected {operation.case} step {operation.step} {event}")
            for index in (4, 5):
                integer(fields[index], -1, operation.count - 1 if operation.mode == "M" else -1)
            for index in (6, 7, 8, 9, 12, 14):
                integer(fields[index], 0, 1)
            if operation.mode == "C" and fields[6:8] != ["0", "0"]:
                raise ValueError("Coroutine-only trace has machine flags")
            for index in (10, 15, 16):
                float_bits("@" + fields[index])
            for index in (11, 13):
                integer(fields[index], 0, 2147483647)
            if fields[15:] != [operation.delta, operation.raw_delta]:
                raise ValueError("Trace delta fields do not match fixture")
            if event[0] in {"begin", "factory", "update"} and fields[4] != event[1]:
                raise ValueError("Callback state does not match event identity")
            if event[0] == "end" and fields[5] != event[1]:
                raise ValueError("End callback PreviousState does not match identity")
        except ValueError as error:
            raise ValueError(f"{context}: {error}") from error
    if len(rows) != len(expected):
        raise ValueError(f"{name}: Missing operation/event; expected {len(expected)} rows, got {len(rows)}")


def compare(reference, native, fixtures=DEFAULT_FIXTURES):
    operations = fixture_operations(fixtures)
    validate_trace(reference, operations, "reference")
    validate_trace(native, operations, "native")
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
