"""All ordered logical Decal submissions and Source CPU geometry bits; never GPU consumption."""
import copy
import json
import os
from pathlib import Path
import struct
import unittest

from test_static_decal_draw_projection import (SOURCE_IDENTITY, SOURCE_TRACE, file_identity, read_source,
                                               identity_for, key_of, float32, parse_authored_catalog)
from prepare_static_decal_descriptors import encode_catalog, banner_parameters, atlas_key, frame_tuple


def compare_frame(tick, source, actual, owners):
    expected = source["ordered"]
    if len(expected) != len(actual):
        raise ValueError(f"tick {tick}: missing/reordered Decal commands")
    for index, ((key, wanted, banner), row) in enumerate(zip(expected, actual)):
        context = f"tick {tick} command {index}"
        if row["index"] != index or key_of(row) != key or row["ownerIdentity"] != identity_for(*key):
            raise ValueError(context + ": owner identity/order")
        if row["texture"] != owners[key]["texture"] or (row["slice"] >= 0) != banner:
            raise ValueError(context + ": descriptor/classification")
        for field in ("sheet", "dimensions", "sourceRectangle", "color", "effects"):
            if row[field] != wanted[field]:
                raise ValueError(context + ": logical " + field + f" {row[field]} != {wanted[field]}")
        for field in ("position", "origin", "scale"):
            if list(map(float32, row[field])) != list(map(float32, wanted[field])):
                raise ValueError(context + ": logical " + field + f" {row[field]} != {wanted[field]}")
        if float32(row["rotation"]) != float32(wanted["rotation"]):
            raise ValueError(context + ": logical rotation")
        if row["finiteGeometry"] != wanted["finiteGeometry"] or row["verticesFloat32Bits"] != wanted["verticesFloat32Bits"]:
            raise ValueError(context + ": Source CPU geometry bits " + str(row["verticesFloat32Bits"]) + " != " + str(wanted["verticesFloat32Bits"]))


class BannerCommandEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.environ.get("CELESTE_BANNER_COMMAND_TRACE")
        catalog = os.environ.get("CELESTE_BANNER_AUTHORED_CATALOG")
        if not path or not catalog:
            raise unittest.SkipTest("Requires fresh --decal-commands trace and pinned CDO1 metadata")
        if file_identity(SOURCE_TRACE) != SOURCE_IDENTITY:
            raise ValueError("Pinned original Source trace changed")
        _, authored = parse_authored_catalog(Path(catalog).read_text())
        cls.owners = {(owner["room"], owner["background"], owner["ordinal"]): owner for owner in authored}
        cls.source = read_source(SOURCE_TRACE)
        cls.native = {}
        with Path(path).open() as stream:
            for line in stream:
                if line.startswith('{"event":"decal-command"'):
                    row = json.loads(line)
                    cls.native.setdefault(row["tick"], []).append(row)
        if sorted(cls.native) != list(range(514)):
            raise ValueError("Incomplete native Decal command trace")

    def test_all_49854_ordered_commands_and_geometry_bits(self):
        for tick in range(514):
            compare_frame(tick, self.source[tick], self.native[tick], self.owners)
        self.assertEqual(sum(map(len, self.native.values())), 49854)

    def test_banner_static_and_nonfinite_counts(self):
        rows = [row for frame in self.native.values() for row in frame]
        self.assertEqual(sum(row["slice"] >= 0 for row in rows), 38108)
        self.assertEqual(sum(row["slice"] < 0 for row in rows), 11746)
        self.assertEqual(sum(not row["finiteGeometry"] for row in rows), 5929)

    def test_frontier_frame_counts(self):
        for tick, count in ((0, 98), (374, 165), (413, 67), (513, 67)):
            with self.subTest(tick=tick):
                self.assertEqual(len(self.native[tick]), count)

    def test_missing_command_rejects(self):
        rows = copy.deepcopy(self.native[0]);rows.pop()
        with self.assertRaisesRegex(ValueError, "missing"):
            compare_frame(0, self.source[0], rows, self.owners)

    def test_same_kind_owner_swap_rejects(self):
        rows = copy.deepcopy(self.native[0]);rows[0], rows[1] = rows[1], rows[0]
        with self.assertRaisesRegex(ValueError, "identity/order"):
            compare_frame(0, self.source[0], rows, self.owners)

    def test_logical_float_sign_and_single_bit_mutations_reject(self):
        for field in ("position", "origin", "scale"):
            for sign in (False, True):
                with self.subTest(field=field, sign=sign):
                    rows = copy.deepcopy(self.native[0]);row = next(row for row in rows if row["slice"] >= 0)
                    value = row[field][0]
                    bits = struct.unpack("<I", float32(value))[0]
                    row[field][0] = struct.unpack("<f", struct.pack("<I", bits ^ (0x80000000 if sign else 1)))[0]
                    with self.assertRaisesRegex(ValueError, "logical " + field):
                        compare_frame(0, self.source[0], rows, self.owners)

    def test_nonfinite_geometry_bit_tamper_rejects(self):
        rows = copy.deepcopy(self.native[0]);row = next(row for row in rows if not row["finiteGeometry"])
        row["verticesFloat32Bits"][0][0] ^= 1
        with self.assertRaisesRegex(ValueError, "geometry bits"):
            compare_frame(0, self.source[0], rows, self.owners)

    def test_descriptor_tamper_rejects(self):
        rows = copy.deepcopy(self.native[0]);rows[0]["sourceRectangle"][0] += 1
        with self.assertRaisesRegex(ValueError, "logical sourceRectangle"):
            compare_frame(0, self.source[0], rows, self.owners)

    def test_source_float_field_tamper_rejects(self):
        source = copy.deepcopy(self.source[0])
        command = next(command for _, command, banner in source["ordered"] if banner)
        bits = struct.unpack("<I", float32(command["position"][0]))[0]
        command["position"][0] = struct.unpack("<f", struct.pack("<I", bits ^ 1))[0]
        with self.assertRaisesRegex(ValueError, "logical position"):
            compare_frame(0, source, self.native[0], self.owners)

    def test_descriptor_regeneration_and_all27_singletons(self):
        path = os.environ.get("CELESTE_BANNER_DESCRIPTOR_RECEIPT")
        if not path:
            self.skipTest("Requires the fresh private descriptor receipt")
        receipt = json.loads(Path(path).read_text())
        atlas = json.loads(Path(receipt["atlas"]["path"]).read_text())
        authored = Path(receipt["authored_catalog"]["path"]).read_text()
        source = Path(os.environ["CELESTE_BANNER_DECAL_SOURCE"]).read_bytes()
        self.assertEqual(encode_catalog(authored, atlas, source), Path(receipt["output"]["path"]).read_bytes())
        import re
        keys = {atlas_key(owner["texture"]) for owner in self.owners.values()}
        self.assertEqual(len(keys), 27)
        for key in keys:
            self.assertEqual(sum(bool(re.fullmatch(re.escape(key) + r"\d*", candidate)) for candidate in atlas), 1)
        self.assertTrue(all(len(frame_tuple(atlas, owner["texture"])) == 9 for owner in self.owners.values()))

    def test_source_parameter_pin_tamper_rejects(self):
        with self.assertRaisesRegex(ValueError, "Pinned"):
            banner_parameters(b"synthetic changed Source input")
