"""Static authored decal command projection vs accepted SOURCE, streamed in place.

Only the 41 STATIC authored owners are compared command-by-command. The 11 Banner
owners are reported as deferred: the comparator counts all 38,108 accepted SOURCE
Banner commands without claiming they were projected. This is logical CPU command
identity/order/geometry, not GL, GPU, pixels or Vita.
"""

import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests/native"))
from prepare_static_decal_descriptors import (  # noqa: E402
    AUDIT, ATLAS_SHA, AUTHORED_SHA, DECAL_SOURCE_SHA, INPUT_SHA, MAP_SHA,
    atlas_key, encode_catalog, frame_tuple, parse_authored_catalog, prepare,
)
from test_native_gameplay_draw_projection import (  # noqa: E402
    SOURCE_IDENTITY, SOURCE_TRACE, canonical_root, file_identity, source_entries, source_keys,
)

FRAMES = 514
STATIC_TOTAL = 11746
BANNER_TOTAL = 38108
STATIC_COUNTS = {0: 22, 374: 41, 413: 19, 513: 19}
BANNER_COUNTS = {0: 76, 374: 124, 413: 48, 513: 48}
DESCRIPTOR_RECEIPT = AUDIT / "descriptor-catalog-01/receipt.json"
PROOF_RECEIPT = AUDIT / "proof-01/receipt.json"
IDENTITY_NAMESPACE = 0x6000000000000000


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fnv1a(data):
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value


def float32(value):
    return struct.pack("<f", float(value))


def identity_for(room, background, ordinal):
    room_index = 1 if str(room) == "1" else 2
    return IDENTITY_NAMESPACE | room_index << 32 | (1 if background else 2) << 24 | ordinal + 1


def parse_descriptor_catalog(text, authored):
    lines = text.decode().splitlines()
    require(len(lines) >= 7 and lines[0] == "CDSC1", "Unknown descriptor catalog version")
    require(lines[1:6] == [INPUT_SHA, MAP_SHA, DECAL_SOURCE_SHA, ATLAS_SHA, AUTHORED_SHA],
            "Descriptor catalog provenance pins changed")
    family_count = int(lines[6])
    require(family_count == 23, "Descriptor catalog family count changed")
    families, index = [], 7
    for _ in range(family_count):
        fields = lines[index].split()
        index += 1
        require(len(fields) == 10, "Invalid descriptor family row")
        sheet, *values, texture = fields
        numbers = list(map(int, values))
        require(sheet == "Gameplay0" and len(numbers) == 8, "Invalid descriptor atlas tuple")
        x, y, width, height, offset_x, offset_y, frame_width, frame_height = numbers
        require(0 <= x <= 4096 - width and 0 <= y <= 4096 - height and width > 0 and height > 0,
                "Descriptor crop is outside the atlas sheet")
        require(-4096 <= offset_x <= 4096 and -4096 <= offset_y <= 4096,
                "Descriptor draw offset is out of bounds")
        require(frame_width > 0 and frame_height > 0, "Descriptor frame size is nonpositive")
        require(texture and ".." not in texture.replace("\\", "/"), "Invalid descriptor family key")
        require(texture not in [family["texture"] for family in families], "Duplicate descriptor family key")
        families.append({"sheet": sheet, "x": x, "y": y, "width": width, "height": height,
                         "offset_x": offset_x, "offset_y": offset_y,
                         "frame_width": frame_width, "frame_height": frame_height,
                         "texture": texture})
    owner_count = int(lines[index])
    index += 1
    require(owner_count == 41, "Descriptor static owner count changed")
    expected_static = {(value["room"], value["background"], value["ordinal"]): value
                       for value in authored if not value["banner"]}
    owners = {}
    for _ in range(owner_count):
        fields = lines[index].split()
        index += 1
        require(len(fields) == 5 and fields[0] == "O", "Invalid descriptor static owner row")
        room, layer, ordinal, family = fields[1], fields[2], int(fields[3]), int(fields[4])
        require(layer in ("B", "F") and 0 <= family < len(families), "Invalid descriptor owner layer/family")
        key = (room, layer == "B", ordinal)
        require(key in expected_static and key not in owners, "Unknown or duplicate static owner descriptor")
        authored_owner = expected_static[key]
        require(families[family]["texture"] == authored_owner["texture"],
                "Descriptor family is not bound to its authored owner key")
        owners[key] = {"identity": authored_owner["identity"], "room": room,
                       "background": layer == "B", "ordinal": ordinal,
                       "texture": authored_owner["texture"], "family": family,
                       "position": authored_owner["position"], "scale": authored_owner["scale"]}
    require(set(owners) == set(expected_static), "Static descriptor coverage is incomplete")
    deferred_count = int(lines[index])
    index += 1
    require(deferred_count == 11, "Deferred Banner descriptor count changed")
    expected_banner = {(value["room"], value["background"], value["ordinal"]): value
                       for value in authored if value["banner"]}
    deferred = {}
    for _ in range(deferred_count):
        fields = lines[index].split()
        index += 1
        require(len(fields) == 5 and fields[0] == "D", "Invalid deferred Banner descriptor row")
        room, layer, ordinal, texture = fields[1], fields[2], int(fields[3]), fields[4]
        require(layer in ("B", "F"), "Invalid deferred Banner layer")
        key = (room, layer == "B", ordinal)
        require(key in expected_banner and key not in deferred, "Unknown or duplicate deferred Banner owner")
        authored_owner = expected_banner[key]
        require(authored_owner["texture"] == texture, "Deferred Banner key differs from authored owner")
        deferred[key] = {"identity": authored_owner["identity"], "room": room,
                         "background": layer == "B", "ordinal": ordinal, "texture": texture}
    require(set(deferred) == set(expected_banner), "Deferred Banner coverage is incomplete")
    require(index == len(lines), "Trailing descriptor catalog data")
    return families, owners, deferred


def expected_command(owner, family):
    return {
        "ownerIdentity": owner["identity"],
        "room": owner["room"],
        "layer": "B" if owner["background"] else "F",
        "ordinal": owner["ordinal"],
        "texture": owner["texture"],
        "sheet": family["sheet"],
        "sourceRectangle": [family["x"], family["y"], family["width"], family["height"]],
        "position": owner["position"],
        "origin": [family["frame_width"] / 2 + family["offset_x"],
                   family["frame_height"] / 2 + family["offset_y"]],
        "scale": owner["scale"],
        "color": [255, 255, 255, 255],
        "rotation": 0,
        "effects": "None",
    }


def read_source(path):
    ticks, current, room, entities, outgoing = {}, None, None, {}, set()
    with path.open() as stream:
        for line in stream:
            if line.startswith('{"event":"draw-state"'):
                row = json.loads(line)
                if row["phase"] != "before-draw":
                    continue
                current = row["tick"]
                if current >= FRAMES:
                    break
                room = row["state"]["room"]
                entities = {value["id"]: value for value in row["state"]["entities"]}
                transition = row["state"].get("transition")
                iterator = transition.get("iterator") if transition else None
                outgoing = set(iterator.get("outgoing") or []) if iterator else set()
                ticks[current] = {"room": room, "outgoing": outgoing, "live": [],
                                  "commands": [], "entities": entities}
            elif line.startswith('{"event":"draw-roster"'):
                if current is None:
                    continue
                row = json.loads(line)
                ticks[current]["live"] = [(value["entity"], entities[value["entity"]]["type"],
                                           value["Visible"], value["hudExcluded"]) for value in row["live"]]
            elif line.startswith('{"event":"draw-command"') and '"type":"Decal"' in line:
                if current is None:
                    continue
                row = json.loads(line)
                if row["owner"]["type"] == "Decal":
                    ticks[current]["commands"].append(row)
    require(sorted(ticks) == list(range(FRAMES)), "SOURCE decal observation must cover all 514 ticks")
    result = {}
    for tick, source in ticks.items():
        keys = source_keys(tick, source)
        ids = [entry[0] for entry in source_entries(source)]
        key_by_id = {entry_id: key for entry_id, key in zip(ids, keys) if key[0] == "Decal"}
        banners = {entity for entity, value in source["entities"].items()
                   if any(component["type"] == "Banner" for component in value["components"])}
        static_commands, banner_commands = [], []
        for command in source["commands"]:
            entity = command["owner"]["entity"]
            require(entity in key_by_id, "SOURCE decal command has no roster key")
            key = key_by_id[entity]
            key = (key[1], key[2] == "bg", key[3])
            if entity in banners:
                banner_commands.append(command)
            else:
                static_commands.append((key, command))
        deferred = [(key_by_id[entry_id][1], key_by_id[entry_id][2] == "bg", key_by_id[entry_id][3])
                    for entry_id, entry in zip(ids, source["live"])
                    if entry[1] == "Decal" and entry_id in banners]
        result[tick] = {"room": source["room"], "static": static_commands,
                        "banner_commands": banner_commands, "deferred": deferred}
    return result


def read_native(path):
    commands, deferred = {}, {}
    with path.open() as stream:
        for line in stream:
            if line.startswith('{"event":"static-decal-command"'):
                row = json.loads(line)
                commands.setdefault(row["tick"], []).append(row)
            elif line.startswith('{"event":"static-decal-deferred"'):
                row = json.loads(line)
                deferred.setdefault(row["tick"], []).append(row)
    require(sorted(commands) == list(range(FRAMES)), "Native static decal commands must cover all 514 ticks")
    require(sorted(deferred) == list(range(FRAMES)), "Native deferred Banner report must cover all 514 ticks")
    return commands, deferred


def key_of(command):
    return (str(command["room"]), command["layer"] == "B", int(command["ordinal"]))


def compare_tick(tick, source, native_commands, native_deferred, owners, deferred, families):
    expected = []
    for key, command in source["static"]:
        require(key in owners, f"tick {tick}: SOURCE static owner has no descriptor")
        expected.append((key, command, expected_command(owners[key], families[owners[key]["family"]])))
    require(len(native_commands) == len(expected),
            f"tick {tick}: native static command count differs from SOURCE")
    for index, ((key, source_command, wanted), actual) in enumerate(zip(expected, native_commands)):
        require(key_of(actual) == key, f"tick {tick}: native static owner order differs at {index}")
        require(actual["ownerIdentity"] == wanted["ownerIdentity"],
                f"tick {tick}: native static owner identity differs at {index}")
        for field in ("sheet", "sourceRectangle", "rotation", "effects", "color", "texture"):
            require(actual[field] == wanted[field], f"tick {tick}: native {field} differs at {index}")
        for field in ("position", "origin", "scale"):
            require([float32(value) for value in actual[field]] ==
                    [float32(value) for value in wanted[field]],
                    f"tick {tick}: native {field} differs at {index}")
        require(actual["sourceRectangle"] == source_command["sourceRectangle"],
                f"tick {tick}: SOURCE crop identity differs at {index}")
        require([float32(value) for value in actual["origin"]] ==
                [float32(value) for value in source_command["origin"]],
                f"tick {tick}: native origin differs from SOURCE at {index}")
        for field in ("sheet", "rotation", "effects", "color"):
            require(actual[field] == source_command[field],
                    f"tick {tick}: native {field} differs from SOURCE at {index}")
        for field in ("position", "scale"):
            require([float32(value) for value in actual[field]] ==
                    [float32(value) for value in source_command[field]],
                    f"tick {tick}: native {field} differs from SOURCE at {index}")
    expected_deferred = source["deferred"]
    require(len(native_deferred) == len(expected_deferred),
            f"tick {tick}: deferred Banner owner count differs from SOURCE")
    for (room, background, ordinal), actual in zip(expected_deferred, native_deferred):
        key = (room, background, ordinal)
        require(key in deferred, f"tick {tick}: SOURCE Banner owner has no deferred descriptor")
        require(key_of(actual) == key and actual["ownerIdentity"] == deferred[key]["identity"] and
                actual["texture"] == deferred[key]["texture"],
                f"tick {tick}: deferred Banner identity/key differs from SOURCE")
    return len(expected), len(source["banner_commands"])


class StaticDecalEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        override = os.environ.get("CELESTE_STATIC_DECAL_NATIVE_TRACE")
        if override:
            native = Path(override)
            expected = os.environ.get("CELESTE_STATIC_DECAL_NATIVE_SHA256")
        else:
            if not PROOF_RECEIPT.exists():
                raise unittest.SkipTest("Fresh static decal native evidence is unavailable")
            receipt = json.loads(PROOF_RECEIPT.read_text())
            native = PROOF_RECEIPT.parent / receipt["native_trace"]
            expected = receipt["native_trace_sha256"]
        if file_identity(SOURCE_TRACE) != SOURCE_IDENTITY:
            raise ValueError("Immutable accepted SOURCE draw trace changed")
        if expected and file_identity(native)["sha256"] != expected:
            raise ValueError("Static decal native trace changed")
        if not DESCRIPTOR_RECEIPT.exists():
            raise unittest.SkipTest("Private static decal descriptor catalog is unavailable")
        descriptor_receipt = json.loads(DESCRIPTOR_RECEIPT.read_text())
        descriptor_path = Path(descriptor_receipt["output"]["path"])
        data = descriptor_path.read_bytes()
        require(descriptor_receipt["output"]["bytes"] == len(data), "Descriptor byte pin changed")
        require(descriptor_receipt["output"]["sha256"] == hashlib.sha256(data).hexdigest(),
                "Descriptor SHA-256 changed")
        require(descriptor_receipt["output"]["fnv1a"] == f"{fnv1a(data):08x}",
                "Descriptor FNV integrity changed")
        authored_text = Path(descriptor_receipt["authored_catalog"]["path"]).read_text()
        _, authored = parse_authored_catalog(authored_text)
        require(hashlib.sha256(authored_text.encode()).hexdigest() == AUTHORED_SHA,
                "Pinned authored decal catalog changed")
        cls.families, cls.owners, cls.deferred = parse_descriptor_catalog(data, authored)
        cls.source = read_source(SOURCE_TRACE)
        cls.commands, cls.deferred_rows = read_native(native)
        cls.native_path = native

    def test_descriptor_catalog_is_deterministically_bound(self):
        receipt = json.loads(DESCRIPTOR_RECEIPT.read_text())
        atlas = json.loads(Path(receipt["atlas"]["path"]).read_text())
        authored = Path(receipt["authored_catalog"]["path"]).read_text()
        self.assertEqual(encode_catalog(authored, atlas),
                         (AUDIT / "descriptor-catalog-01/static-decals.txt").read_bytes())

    def test_all_static_commands_and_deferred_banners_match_source(self):
        static_total = banner_total = 0
        for tick in range(FRAMES):
            with self.subTest(tick=tick):
                static_count, banner_count = compare_tick(
                    tick, self.source[tick], self.commands[tick], self.deferred_rows[tick],
                    self.owners, self.deferred, self.families)
                static_total += static_count
                banner_total += banner_count
        self.assertEqual(static_total, STATIC_TOTAL)
        self.assertEqual(banner_total, BANNER_TOTAL)

    def test_frontier_counts_are_22_41_19_19(self):
        for tick, count in STATIC_COUNTS.items():
            self.assertEqual(len(self.commands[tick]), count)
            self.assertEqual(len(self.source[tick]["static"]), count)
            self.assertEqual(len(self.source[tick]["banner_commands"]), BANNER_COUNTS[tick])

    def test_all_deferred_banners_are_explicitly_reported_not_projected(self):
        distinct = {key for tick in range(FRAMES) for key in
                    ((row["room"], row["layer"] == "B", row["ordinal"])
                     for row in self.deferred_rows[tick])}
        self.assertEqual(len(distinct), 11)
        self.assertTrue(all(key in self.deferred for key in distinct))
        for tick in range(FRAMES):
            for row, source_key in zip(self.deferred_rows[tick], self.source[tick]["deferred"]):
                self.assertEqual(key_of(row), source_key)
                self.assertNotIn(row["ownerIdentity"],
                                 [command["ownerIdentity"] for command in self.commands[tick]])

    def test_same_kind_owner_swap_is_rejected(self):
        commands = copy.deepcopy(self.commands[0])
        commands[0], commands[1] = commands[1], commands[0]
        with self.assertRaisesRegex(ValueError, "owner order|identity"):
            compare_tick(0, self.source[0], commands, self.deferred_rows[0],
                         self.owners, self.deferred, self.families)

    def test_identity_alias_is_rejected(self):
        commands = copy.deepcopy(self.commands[0])
        commands[1]["ownerIdentity"] = commands[0]["ownerIdentity"]
        with self.assertRaisesRegex(ValueError, "identity"):
            compare_tick(0, self.source[0], commands, self.deferred_rows[0],
                         self.owners, self.deferred, self.families)

    def test_missing_and_duplicate_commands_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "count"):
            compare_tick(0, self.source[0], self.commands[0][1:], self.deferred_rows[0],
                         self.owners, self.deferred, self.families)
        duplicated = copy.deepcopy(self.commands[0]) + [copy.deepcopy(self.commands[0][0])]
        with self.assertRaisesRegex(ValueError, "count"):
            compare_tick(0, self.source[0], duplicated, self.deferred_rows[0],
                         self.owners, self.deferred, self.families)

    def test_missing_banner_report_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "deferred Banner"):
            compare_tick(0, self.source[0], self.commands[0], self.deferred_rows[0][1:],
                         self.owners, self.deferred, self.families)

    def test_bad_atlas_payload_is_rejected_before_catalog_output(self):
        receipt = json.loads(DESCRIPTOR_RECEIPT.read_text())
        atlas = json.loads(Path(receipt["atlas"]["path"]).read_text())
        authored = Path(receipt["authored_catalog"]["path"]).read_text()
        _, owners = parse_authored_catalog(authored)
        texture = next(owner["texture"] for owner in owners if not owner["banner"])
        key = atlas_key(texture)
        missing = dict(atlas)
        missing.pop(key)
        with self.assertRaisesRegex(ValueError, "missing"):
            encode_catalog(authored, missing)
        out_of_bounds = copy.deepcopy(atlas)
        out_of_bounds[key][1] = 4096
        with self.assertRaisesRegex(ValueError, "outside the sheet"):
            encode_catalog(authored, out_of_bounds)
        changed = authored + "extra\n"
        with self.assertRaisesRegex(ValueError, "Trailing|header|CDO1"):
            encode_catalog(changed, atlas)

    def test_generator_requires_fresh_private_output(self):
        atlas = Path("/home/fred/projects/celeste-vita/.audit/native-player-presentation/compile-01/atlas.json")
        authored = Path("/home/fred/projects/celeste-vita/.audit/native-room2-decal-ownership-01/metadata-01/catalog.txt")
        with self.assertRaisesRegex(ValueError, "private audit namespace"):
            prepare(atlas, authored, ROOT / "descriptor-catalog.txt")
        with self.assertRaisesRegex(ValueError, "fresh"):
            prepare(atlas, authored, AUDIT / "descriptor-catalog-01/static-decals.txt")


if __name__ == "__main__":
    unittest.main()
