"""Read-only route checks for native Banner lifetime/update state, not draw-command parity."""
import copy
import json
import math
import os
from pathlib import Path
import struct
import unittest


def float32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_phases(rows):
    states, phases, rosters, scopes = {}, {}, {}, {}
    for row in rows:
        event = row["event"]
        if event == "phase":
            key = row["tick"], row["phase"]
            require(key not in states, "Duplicate session phase")
            states[key] = row["state"]
        elif event == "banner-phases":
            key = row["tick"], row["phase"], row["room"]
            require(key not in phases, "Duplicate Banner room phase")
            identities = [owner["identity"] for owner in row["owners"]]
            require(len(set(identities)) == len(identities), "Aliased Banner owner identity")
            require(len(identities) == {"1": 7, "2": 4}[row["room"]], "Missing Banner phase")
            require(all(type(owner["sineTimer"]) in (int, float) and math.isfinite(owner["sineTimer"])
                        for owner in row["owners"]), "Invalid Banner float field")
            if row["room"] in scopes:
                require(scopes[row["room"]] == row["roomScope"], "Room-instance identity changed")
            else:
                require(row["roomScope"] not in scopes.values(), "Room-instance identity aliases another room")
                scopes[row["room"]] = row["roomScope"]
            phases[key] = {owner["identity"]: float32(owner["sineTimer"]) for owner in row["owners"]}
        elif event == "draw-owner-roster":
            require(row["tick"] not in rosters, "Duplicate draw roster")
            rosters[row["tick"]] = row["live"]
    require(len(states) == 514 * 5 and len(rosters) == 514, "Incomplete route observation")
    for tick in range(514):
        before = states[tick, "before-update"]
        before_rooms = {"1"} if tick <= 374 else ({"1", "2"} if tick <= 413 else {"2"})
        after_rooms = {"1"} if tick < 374 else ({"1", "2"} if tick < 413 else {"2"})
        for phase, expected_rooms in (("before-frame", before_rooms), ("before-update", before_rooms),
                                      ("before-eof", after_rooms), ("after-eof", after_rooms), ("after-frame", after_rooms)):
            require({room for frame, name, room in phases if (frame, name) == (tick, phase)} == expected_rooms,
                    "Banner room lifetime changed")
        for room in before_rooms:
            start = phases[tick, "before-frame", room]
            require(start == phases[tick, "before-update", room], "Observation advanced Banner phase")
            if tick and (tick - 1, "after-frame", room) in phases:
                require(start == phases[tick - 1, "after-frame", room], "Between-frame Banner mutation")
            if room not in after_rooms:
                continue
            expected = {identity: float32(value + (0 if before["Transitioning"] else float32(1 / 60)))
                        for identity, value in start.items()}
            require(phases[tick, "before-eof", room] == expected, "Banner update float/order changed")
        for room in after_rooms:
            value = phases[tick, "before-eof", room]
            require(value == phases[tick, "after-eof", room] == phases[tick, "after-frame", room],
                    "End-of-frame observation advanced Banner phase")
            expected_owners = {owner["identity"] for owner in rosters[tick] if owner["room"] == room and owner["banner"]}
            require(set(value) == expected_owners, "Banner phases are not bound to actual room draw owners")
    require(phases[374, "after-frame", "2"] == phases[413, "after-frame", "2"], "Incoming transition phases advanced")
    require(phases[373, "after-frame", "1"] == phases[412, "after-frame", "1"], "Outgoing transition phases advanced")
    return {"frames": 514, "room_phase_records": len(phases), "room_instances": len(scopes)}


class BannerPhaseTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.environ.get("CELESTE_NATIVE_BANNER_PHASE_TRACE")
        if not path:
            raise unittest.SkipTest("Set CELESTE_NATIVE_BANNER_PHASE_TRACE to a fresh native --banner-phases trace")
        cls.rows = []
        with Path(path).open() as stream:
            for line in stream:
                if line.startswith(('{"event":"phase"', '{"event":"banner-phases"', '{"event":"draw-owner-roster"')):
                    cls.rows.append(json.loads(line))

    def altered(self, predicate, mutate):
        rows = copy.deepcopy(self.rows)
        mutate(next(row for row in rows if predicate(row)))
        return rows

    def test_all_route_phases_follow_actual_room_lifetimes(self):
        self.assertEqual(validate_phases(self.rows)["room_instances"], 2)

    def test_owner_identity_alias_rejects(self):
        rows = self.altered(lambda row: row["event"] == "banner-phases",
                            lambda row: row["owners"][1].update(identity=row["owners"][0]["identity"]))
        with self.assertRaisesRegex(ValueError, "Aliased"):
            validate_phases(rows)

    def test_missing_banner_phase_rejects(self):
        rows = self.altered(lambda row: row["event"] == "banner-phases", lambda row: row["owners"].pop())
        with self.assertRaisesRegex(ValueError, "Missing"):
            validate_phases(rows)

    def test_single_float32_bit_tamper_rejects(self):
        def mutate(row):
            owner = row["owners"][0]
            bits = struct.unpack("<I", struct.pack("<f", owner["sineTimer"]))[0]
            owner["sineTimer"] = struct.unpack("<f", struct.pack("<I", bits + 1))[0]
        rows = self.altered(lambda row: row["event"] == "banner-phases" and row["phase"] == "before-eof", mutate)
        with self.assertRaisesRegex(ValueError, "float/order"):
            validate_phases(rows)

    def test_room_instance_alias_rejects(self):
        scope = next(row["roomScope"] for row in self.rows if row["event"] == "banner-phases")
        rows = self.altered(lambda row: row["event"] == "banner-phases" and row["room"] == "2",
                            lambda row: row.update(roomScope=scope))
        with self.assertRaisesRegex(ValueError, "aliases"):
            validate_phases(rows)

    def test_nonfinite_phase_rejects(self):
        rows = self.altered(lambda row: row["event"] == "banner-phases",
                            lambda row: row["owners"][0].update(sineTimer=float("nan")))
        with self.assertRaisesRegex(ValueError, "float field"):
            validate_phases(rows)
