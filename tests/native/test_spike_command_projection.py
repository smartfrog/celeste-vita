"""Bounded native Up/Left spike command projection vs the accepted SOURCE oracle.

The frozen SOURCE trace is streamed in place as a TEST oracle only. Production never
loads it. Every command is bound to the actual native draw roster and dispatch each
tick, so owner identity is verified as a semantic (room, authored id, kind) binding
rather than a cardinality count. Cross-tick object lifetimes are checked as well.
SOURCE owner bindings come from pinned room positions/authored ids plus the observed
Image component order, never from native order or a same-kind ordinal assumption.
This is logical CPU command comparison, not renderer/physics/input/timestep/RNG
parity. Lifetime inference is bounded to this zero-reload 514-frame route: it
detects cross-tick identity tampering, but an immediate same-room reload is not
modeled and would be rejected rather than treated as a fresh instance.
"""

import copy
import json
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests/native"))
from prepare_native_transition_fixture import room_records  # noqa: E402
from test_native_gameplay_draw_projection import (  # noqa: E402
    SOURCE_IDENTITY, SOURCE_TRACE, canonical_root, file_identity,
)

FRAMES = 514
SPIKE_TOTAL = 9107
SPIKE_COUNTS = {0: 19, 374: 28, 412: 28, 413: 9, 513: 9}
TICK_COUNTS = {19: 374, 28: 39, 9: 101}
ROOMS = Path("/home/fred/projects/celeste-vita-worktrees/native-room-transition-vita"
             "/.audit/native-room-transition-vita/gameplay-draw-profile-01"
             "/clean-commit-a2af9d05b662/profile-01/two-rooms.json")
ROOMS_IDENTITY = {"bytes": 15518,
                  "sha256": "b5c5814db9cb0084099a552d38890887f9f9602a97d86d99f07969e79602809f"}
AUDIT = canonical_root() / ".audit/native-spike-command-projection-01"
CATALOG = Path(os.environ.get("CELESTE_SPIKE_CATALOG", AUDIT / "descriptor-01/catalog.txt"))
NATIVE = Path(os.environ.get("CELESTE_SPIKE_NATIVE_TRACE",
                             AUDIT / "proof-01/native-run/spike-commands-fresh-release.jsonl"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def float32(value):
    return struct.pack("<f", float(value))


def read_catalog(path):
    lines = path.read_text().splitlines()
    require(len(lines) == 7 and lines[0] == "CSPK1", "Unknown private spike catalog version")
    require(all(len(pin) == 64 and set(pin) <= set("0123456789abcdef") for pin in lines[1:4]),
            "Invalid private spike catalog provenance pin")
    require(lines[4] == "2", "Private spike catalog must carry exactly two frames")
    frames = {}
    for line in lines[5:]:
        fields = line.split()
        require(len(fields) == 11 and fields[0] in ("up", "left") and fields[0] not in frames,
                "Invalid or duplicate private spike frame row")
        direction, sheet, *numbers, texture = fields
        values = list(map(int, numbers))
        require(len(values) == 8 and sheet == "Gameplay0", "Invalid private spike frame atlas tuple")
        x, y, width, height, offset_x, offset_y, frame_width, frame_height = values
        require(0 <= x <= 4096 - width and 0 <= y <= 4096 - height and width > 0 and height > 0,
                "Private spike crop is outside the atlas sheet")
        require(-4096 <= offset_x <= 4096 and -4096 <= offset_y <= 4096 and
                frame_width > 0 and frame_height > 0, "Private spike frame metadata is out of bounds")
        require(texture and ".." not in texture, "Invalid private spike atlas key")
        frames[direction] = {"sheet": sheet, "x": x, "y": y, "width": width, "height": height,
                             "offset_x": offset_x, "offset_y": offset_y,
                             "frame_width": frame_width, "frame_height": frame_height,
                             "texture": texture}
    require(set(frames) == {"up", "left"}, "Private spike catalog must cover both bounded directions")
    return frames


def expected_origin(frame, direction):
    if direction == "up":
        return [frame["frame_width"] * 0.5 + frame["offset_x"],
                frame["frame_height"] * 1.0 + frame["offset_y"]]
    return [frame["frame_width"] * 1.0 + frame["offset_x"],
            frame["frame_height"] * 0.5 + frame["offset_y"]]


def read_pinned_spikes():
    require(file_identity(ROOMS) == ROOMS_IDENTITY, "Pinned two-room metadata changed")
    records = room_records(json.loads(ROOMS.read_text()))
    require([room["name"] for room in records] == ["1", "2"],
            "Expected the pinned bounded two-room profile")
    result = {}
    for room in records:
        by_position = {}
        for kind, authored_id, x, y, size in room["objects"]:
            if kind not in ("spike_up", "spike_left"):
                continue
            direction = kind[len("spike_"):]
            require(direction in ("up", "left") and authored_id >= 0 and size > 0 and size % 8 == 0,
                    "Unsupported pinned room spike")
            key = (x, y)
            require(key not in by_position, "Ambiguous pinned spike position: " + repr(key))
            by_position[key] = {"authoredId": authored_id, "direction": direction, "size": size}
        result[room["name"]] = by_position
    require({room: len(values) for room, values in result.items()} == {"1": 5, "2": 3},
            "Pinned room spike owner counts changed")
    return result


def read_source(path, pinned):
    ticks, current = {}, None
    with path.open() as stream:
        for line in stream:
            if line.startswith('{"event":"draw-state"'):
                row = json.loads(line)
                if row["phase"] != "before-draw":
                    continue
                current = row["tick"]
                if current >= FRAMES:
                    break
                transition = row["state"].get("transition")
                iterator = transition.get("iterator") if transition else None
                ticks[current] = {"room": row["state"]["room"],
                                  "outgoing": set(iterator.get("outgoing") or []) if iterator else set(),
                                  "entities": {value["id"]: value for value in row["state"]["entities"]},
                                  "live": [], "commands": []}
            elif line.startswith('{"event":"draw-roster"') and current in ticks:
                row = json.loads(line)
                entities = ticks[current]["entities"]
                ticks[current]["live"] = [(value["entity"], entities[value["entity"]]["type"],
                                           value["Visible"], value["hudExcluded"])
                                          for value in row["live"]]
            elif line.startswith('{"event":"draw-command"') and current in ticks and '"Spikes"' in line:
                row = json.loads(line)
                if row["owner"]["type"] == "Spikes":
                    ticks[current]["commands"].append(row)
    require(sorted(ticks) == list(range(FRAMES)), "SOURCE spike observation must cover all 514 ticks")
    result = {}
    for tick, source in ticks.items():
        key_by_entity = {}
        for entity, kind, _visible, _hud in source["live"]:
            if kind != "Spikes":
                continue
            room = "1" if entity in source["outgoing"] else source["room"]
            require(room in pinned, f"tick {tick}: SOURCE spike owner has an unsupported room")
            position = tuple(source["entities"][entity]["position"])
            require(position in pinned[room],
                    f"tick {tick}: SOURCE spike position has no pinned authored owner")
            descriptor = pinned[room][position]
            key = (room, descriptor["authoredId"])
            require(key not in key_by_entity.values(),
                    f"tick {tick}: pinned authored spike owner is bound twice")
            key_by_entity[entity] = key
        commands, pieces = [], {}
        for command in source["commands"]:
            entity = command["owner"]["entity"]
            require(entity in key_by_entity, f"tick {tick}: SOURCE spike command has no roster owner")
            room, authored_id = key_by_entity[entity]
            descriptor = pinned[room][tuple(source["entities"][entity]["position"])]
            require(command["owner"]["componentType"] == "Image",
                    f"tick {tick}: SOURCE spike command is not an Image component")
            piece = pieces.get(entity, 0)
            pieces[entity] = piece + 1
            commands.append({"room": room, "authoredId": authored_id,
                             "direction": descriptor["direction"], "piece": piece,
                             "sheet": command["sheet"],
                             "sourceRectangle": command["sourceRectangle"],
                             "position": command["position"], "origin": command["origin"],
                             "scale": command["scale"], "color": command["color"],
                             "rotation": command["rotation"], "effects": command["effects"]})
        for entity, (room, authored_id) in key_by_entity.items():
            descriptor = pinned[room][tuple(source["entities"][entity]["position"])]
            require(pieces.get(entity, 0) == descriptor["size"] // 8,
                    f"tick {tick}: SOURCE Image component order count differs from authored size")
        result[tick] = commands
    total = sum(len(commands) for commands in result.values())
    require(total == SPIKE_TOTAL, "SOURCE spike command total changed")
    distribution = {}
    for commands in result.values():
        distribution[len(commands)] = distribution.get(len(commands), 0) + 1
    require(distribution == TICK_COUNTS, "SOURCE per-tick spike command distribution changed")
    return result


def read_native(path):
    rosters, dispatches, commands = {}, {}, {}
    with path.open() as stream:
        for line in stream:
            if line.startswith('{"event":"draw-owner-roster"'):
                row = json.loads(line)
                require(row["tick"] not in rosters, "Duplicate native draw roster tick")
                rosters[row["tick"]] = row
            elif line.startswith('{"event":"draw-owner-dispatch"'):
                row = json.loads(line)
                require(row["tick"] not in dispatches, "Duplicate native draw dispatch tick")
                dispatches[row["tick"]] = row["order"]
            elif line.startswith('{"event":"spike-command"'):
                row = json.loads(line)
                commands.setdefault(row["tick"], []).append(row)
    require(sorted(rosters) == list(range(FRAMES)), "Native draw rosters must cover all 514 ticks")
    require(sorted(dispatches) == list(range(FRAMES)), "Native draw dispatches must cover all 514 ticks")
    require(sorted(commands) == list(range(FRAMES)), "Native spike commands must cover all 514 ticks")
    return {"rosters": rosters, "dispatches": dispatches, "commands": commands}


def spike_entries(roster, tick):
    entries, seen = {}, set()
    for owner in roster["live"]:
        identity = owner["identity"]
        require(type(identity) is int and identity > 0, f"tick {tick}: invalid owner identity")
        require(identity not in seen, f"tick {tick}: duplicate native roster identity")
        seen.add(identity)
        if owner["kind"] != "Spikes":
            continue
        require(type(owner["authoredId"]) is int and owner["authoredId"] >= 0 and owner["room"],
                f"tick {tick}: invalid spike roster semantic binding")
        entries[identity] = (owner["room"], owner["authoredId"])
    return entries


def validate_dispatch(tick, roster, dispatch, commands):
    live = roster["live"]
    identities = [owner["identity"] for owner in live]
    require(len(set(identities)) == len(identities), f"tick {tick}: duplicate native roster identity")
    expected = [owner["identity"] for owner in live if owner["visible"] and not owner["hudExcluded"]]
    require(dispatch == expected, f"tick {tick}: native dispatch order differs from the live roster")
    require(len(set(dispatch)) == len(dispatch), f"tick {tick}: duplicate native dispatch identity")
    entries = spike_entries(roster, tick)
    spike_dispatch = [identity for identity in dispatch if identity in entries]
    order, pieces = [], {}
    for index, command in enumerate(commands):
        require(command["index"] == index, f"tick {tick}: native spike command index differs at {index}")
        identity = command["ownerIdentity"]
        require(identity in entries, f"tick {tick}: spike command owner is not in the native roster")
        require((command["room"], command["authoredId"]) == entries[identity],
                f"tick {tick}: spike command does not bind to its native roster owner")
        if not order or order[-1] != identity:
            require(identity not in order, f"tick {tick}: spike owner commands are not contiguous")
            order.append(identity)
        pieces.setdefault(identity, []).append(command["piece"])
    require(order == spike_dispatch,
            f"tick {tick}: native spike owner order differs from the native dispatch")
    for identity, values in pieces.items():
        require(sorted(values) == list(range(len(values))),
                f"tick {tick}: native spike piece order is incomplete or duplicated for owner {identity}")
    return entries


def validate_lifetimes(rosters):
    bindings, per_room = {}, {}
    for tick in range(FRAMES):
        for identity, key in spike_entries(rosters[tick], tick).items():
            require(bindings.setdefault(identity, key) == key,
                    f"tick {tick}: native spike identity changed its semantic owner")
            per_room.setdefault(key[0], {}).setdefault(tick, {})[key[1]] = identity
    for room, ticks in per_room.items():
        runs, run = [], []
        for tick in range(FRAMES):
            if tick in ticks:
                run.append(tick)
            elif run:
                runs.append(run)
                run = []
        if run:
            runs.append(run)
        seen_identities = set()
        for run in runs:
            owners = {}
            for tick in run:
                for authored_id, identity in ticks[tick].items():
                    require(owners.setdefault(authored_id, identity) == identity,
                            f"room {room}: authored owner {authored_id} changed identity during its lifetime")
            run_identities = set(owners.values())
            require(not (run_identities & seen_identities),
                    f"room {room}: a fresh load reused an unloaded instance identity")
            seen_identities |= run_identities
    return True


EXACT_FIELDS = ("room", "authoredId", "direction", "piece", "sheet", "sourceRectangle",
                "color", "rotation", "effects")
FLOAT_FIELDS = ("position", "origin", "scale")


def compare_tick(tick, expected, native, frames):
    roster = native["rosters"][tick]
    dispatch = native["dispatches"][tick]
    actual = native["commands"][tick]
    require(len(actual) == len(expected), f"tick {tick}: native spike command count differs from SOURCE")
    validate_dispatch(tick, roster, dispatch, actual)
    for index, (wanted, command) in enumerate(zip(expected, actual)):
        for field in EXACT_FIELDS:
            require(command[field] == wanted[field], f"tick {tick}: native {field} differs at {index}")
        for field in FLOAT_FIELDS:
            require([float32(value) for value in command[field]] ==
                    [float32(value) for value in wanted[field]],
                    f"tick {tick}: native {field} differs at {index}")
        frame = frames[wanted["direction"]]
        require(command["texture"] == frame["texture"], f"tick {tick}: native texture differs at {index}")
        require(command["sourceRectangle"] == [frame["x"], frame["y"], frame["width"], frame["height"]],
                f"tick {tick}: native source rectangle is not bound to the private material frame")
        require([float32(value) for value in command["origin"]] ==
                [float32(value) for value in expected_origin(frame, wanted["direction"])],
                f"tick {tick}: native origin is not the source justify minus draw offset")
        require(command["sourceRectangle"] == wanted["sourceRectangle"],
                f"tick {tick}: native rectangle differs from SOURCE at {index}")


class SpikeCommandProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        paths = (SOURCE_TRACE, CATALOG, NATIVE, ROOMS)
        present = [path.is_file() for path in paths]
        if not any(present):
            raise unittest.SkipTest("Actual private SOURCE/native spike observations are unavailable")
        if not all(present):
            raise ValueError("Partial spike evidence: pinned private fixtures must stay consistent")
        if file_identity(SOURCE_TRACE) != SOURCE_IDENTITY:
            raise ValueError("Immutable accepted SOURCE draw trace changed")
        cls.pinned = read_pinned_spikes()
        cls.frames = read_catalog(CATALOG)
        cls.source = read_source(SOURCE_TRACE, cls.pinned)
        cls.native = read_native(NATIVE)
        require(validate_lifetimes(cls.native["rosters"]), "Native spike lifetime validation failed")
        commands = cls.native["commands"]
        require(sum(len(values) for values in commands.values()) == SPIKE_TOTAL,
                "Native spike command total differs from the accepted SOURCE count")
        distribution = {}
        for values in commands.values():
            distribution[len(values)] = distribution.get(len(values), 0) + 1
        require(distribution == TICK_COUNTS, "Native per-tick spike command distribution changed")

    def native_tick(self, tick):
        return {"rosters": {tick: self.native["rosters"][tick]},
                "dispatches": {tick: self.native["dispatches"][tick]},
                "commands": {tick: self.native["commands"][tick]}}

    def compare(self, tick):
        return compare_tick(tick, self.source[tick], self.native_tick(tick), self.frames)

    def test_every_route_tick_matches_source(self):
        for tick in range(FRAMES):
            self.compare(tick)

    def test_every_route_tick_binds_actual_roster_and_dispatch(self):
        for tick in range(FRAMES):
            entries = spike_entries(self.native["rosters"][tick], tick)
            self.assertEqual(validate_dispatch(tick, self.native["rosters"][tick],
                                               self.native["dispatches"][tick],
                                               self.native["commands"][tick]), entries)

    def test_focused_counts_and_tick_edges(self):
        for tick, count in SPIKE_COUNTS.items():
            self.assertEqual(len(self.native["commands"][tick]), count)
        for tick in range(374, 413):
            self.assertTrue(all(command["room"] == "1" for command in self.native["commands"][tick][:19]))
            self.assertTrue(all(command["room"] == "2" for command in self.native["commands"][tick][19:]))
        for tick in range(413, FRAMES):
            self.assertTrue(all(command["room"] == "2" for command in self.native["commands"][tick]))

    def test_owner_piece_and_direction_splits(self):
        first = {}
        for command in self.native["commands"][0]:
            key = (command["room"], command["authoredId"], command["direction"])
            first[key] = first.get(key, 0) + 1
        self.assertEqual(first, {("1", 7, "up"): 5, ("1", 8, "up"): 5, ("1", 9, "up"): 4,
                                 ("1", 10, "up"): 3, ("1", 11, "left"): 2})
        second = {}
        for command in self.native["commands"][413]:
            key = (command["room"], command["authoredId"], command["direction"])
            second[key] = second.get(key, 0) + 1
        self.assertEqual(second, {("2", 8, "up"): 5, ("2", 9, "up"): 2, ("2", 14, "up"): 2})

    def test_known_room1_owner7_owner8_identity_swap_is_rejected(self):
        changed = copy.deepcopy(self.native_tick(0))
        commands = changed["commands"][0]
        first_commands = [command for command in commands if command["authoredId"] == 7]
        second_commands = [command for command in commands if command["authoredId"] == 8]
        self.assertEqual(len(first_commands), 5, "Fixture must retain five room1 owner7 pieces")
        self.assertEqual(len(second_commands), 5, "Fixture must retain five room1 owner8 pieces")
        first_identity = first_commands[0]["ownerIdentity"]
        second_identity = second_commands[0]["ownerIdentity"]
        self.assertNotEqual(first_identity, second_identity,
                            "Fixture owners must have distinct native identities")
        self.assertTrue(all(command["ownerIdentity"] == first_identity for command in first_commands),
                        "Fixture owner7 identity must be stable before mutation")
        self.assertTrue(all(command["ownerIdentity"] == second_identity for command in second_commands),
                        "Fixture owner8 identity must be stable before mutation")
        for command in commands:
            if command["authoredId"] == 7:
                command["ownerIdentity"] = second_identity
            elif command["authoredId"] == 8:
                command["ownerIdentity"] = first_identity
        swapped = {command["authoredId"]: command["ownerIdentity"] for command in commands
                   if command["authoredId"] in (7, 8)}
        self.assertEqual(swapped, {7: second_identity, 8: first_identity},
                         "Mutation must exchange the two saved identities")
        self.assertNotEqual(swapped[7], swapped[8], "Mutation must stay bijective, not alias")
        with self.assertRaisesRegex(ValueError, "bind"):
            compare_tick(0, self.source[0], changed, self.frames)

    def test_unknown_owner_identity_is_rejected(self):
        changed = copy.deepcopy(self.native_tick(0))
        changed["commands"][0][0]["ownerIdentity"] = 999999999
        with self.assertRaisesRegex(ValueError, "roster"):
            compare_tick(0, self.source[0], changed, self.frames)

    def test_aliased_same_owner_identity_is_rejected(self):
        changed = copy.deepcopy(self.native_tick(0))
        alias = changed["commands"][0][0]["ownerIdentity"]
        for command in changed["commands"][0]:
            if command["authoredId"] == 8:
                command["ownerIdentity"] = alias
        with self.assertRaisesRegex(ValueError, "bind|contiguous|order"):
            compare_tick(0, self.source[0], changed, self.frames)

    def test_duplicate_roster_identity_is_rejected(self):
        changed = copy.deepcopy(self.native_tick(0))
        live = changed["rosters"][0]["live"]
        first = next(owner for owner in live if owner["kind"] == "Spikes" and owner["authoredId"] == 7)
        second = next(owner for owner in live if owner["kind"] == "Spikes" and owner["authoredId"] == 8)
        second["identity"] = first["identity"]
        with self.assertRaisesRegex(ValueError, "duplicate native roster identity"):
            compare_tick(0, self.source[0], changed, self.frames)

    def test_missing_roster_member_and_command_are_rejected(self):
        changed = copy.deepcopy(self.native_tick(0))
        changed["rosters"][0]["live"] = [owner for owner in changed["rosters"][0]["live"]
                                         if not (owner["kind"] == "Spikes" and owner["authoredId"] == 7)]
        with self.assertRaisesRegex(ValueError, "dispatch"):
            compare_tick(0, self.source[0], changed, self.frames)
        changed = copy.deepcopy(self.native_tick(0))
        changed["commands"][0].pop(3)
        with self.assertRaisesRegex(ValueError, "count"):
            compare_tick(0, self.source[0], changed, self.frames)

    def test_dispatch_order_swap_is_rejected(self):
        changed = copy.deepcopy(self.native_tick(0))
        order = changed["dispatches"][0]
        entries = spike_entries(changed["rosters"][0], 0)
        positions = [index for index, identity in enumerate(order) if identity in entries]
        first, second = positions[0], positions[1]
        order[first], order[second] = order[second], order[first]
        with self.assertRaisesRegex(ValueError, "dispatch"):
            compare_tick(0, self.source[0], changed, self.frames)

    def test_same_owner_identity_lifetime_change_is_rejected(self):
        changed = copy.deepcopy(self.native["rosters"])
        target = changed[100]["live"]
        owner = next(owner for owner in target if owner["kind"] == "Spikes" and owner["authoredId"] == 7)
        owner["identity"] = 900000001
        with self.assertRaisesRegex(ValueError, "changed identity during its lifetime"):
            validate_lifetimes(changed)

    def test_fresh_load_may_replace_identity_but_must_not_reuse_it(self):
        def roster(identities):
            return {"live": [{"kind": "Spikes", "identity": identity, "authoredId": 7, "room": "1",
                              "visible": True, "hudExcluded": False} for identity in identities]}
        fresh = {tick: roster([6] if tick < 2 else ([] if tick == 2 else [99]))
                 for tick in range(FRAMES)}
        self.assertTrue(validate_lifetimes(fresh))
        reused = {tick: roster([6] if tick < 2 else ([] if tick == 2 else [6]))
                  for tick in range(FRAMES)}
        with self.assertRaisesRegex(ValueError, "reused an unloaded instance identity"):
            validate_lifetimes(reused)

    def test_piece_index_and_geometry_mutations_are_rejected(self):
        changed = copy.deepcopy(self.native_tick(0))
        changed["commands"][0][0]["piece"] = 1
        with self.assertRaisesRegex(ValueError, "piece"):
            compare_tick(0, self.source[0], changed, self.frames)
        changed = copy.deepcopy(self.native_tick(0))
        changed["commands"][0][0]["origin"][0] = float(changed["commands"][0][0]["origin"][0]) + 1
        with self.assertRaisesRegex(ValueError, "origin"):
            compare_tick(0, self.source[0], changed, self.frames)


if __name__ == "__main__":
    unittest.main()
