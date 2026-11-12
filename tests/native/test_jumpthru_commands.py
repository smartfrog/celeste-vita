"""Bounded JumpThru evidence, independent SOURCE bindings and input-pin negatives."""
import copy
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest

from compare_native_jumpthru_draw import compare, compare_frame, read_native, read_source
from prepare_jumpthru_catalog import PINS, encode, prepare
from test_native_gameplay_draw_projection import SOURCE_TRACE


class JumpThruCommandEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.environ.get("CELESTE_JUMPTHRU_COMMAND_TRACE")
        if not path:
            raise unittest.SkipTest("Requires fresh --jumpthru-commands native trace")
        cls.source = read_source(SOURCE_TRACE)
        cls.native = read_native(Path(path))

    def test_all_514_frames_and_700_ordered_logical_commands(self):
        self.assertEqual(compare(self.source, self.native)["commands"], 700)

    def test_lifetime_frontiers(self):
        for tick, count in ((0, 0), (373, 0), (374, 5), (412, 5), (413, 5), (513, 5)):
            with self.subTest(tick=tick):
                self.assertEqual(len(self.native[tick]["commands"]), count)

    def test_unknown_identity_rejects(self):
        native = copy.deepcopy(self.native[374]);native["commands"][0]["ownerIdentity"] = 999999
        with self.assertRaisesRegex(ValueError, "binding"):
            compare_frame(374, self.source[374], native, None)

    def test_known_same_kind_component_swap_rejects(self):
        source = copy.deepcopy(self.source[374])
        a, b = source["commands"][:2]
        a["owner"]["component"], b["owner"]["component"] = b["owner"]["component"], a["owner"]["component"]
        with self.assertRaisesRegex(ValueError, "Image binding"):
            compare_frame(374, source, self.native[374], None)

    def test_native_lifetime_change_rejects(self):
        identity = compare_frame(374, self.source[374], self.native[374], None)
        native = copy.deepcopy(self.native[375]);replacement = 999999
        for owner in native["owners"]:
            if owner["identity"] == identity:
                owner["identity"] = replacement
        native["dispatch"] = [replacement if value == identity else value for value in native["dispatch"]]
        for row in native["commands"]:
            row["ownerIdentity"] = replacement
        with self.assertRaisesRegex(ValueError, "lifetime"):
            compare_frame(375, self.source[375], native, identity)

    def test_missing_cell_rejects(self):
        native = copy.deepcopy(self.native[374]);native["commands"].pop()
        with self.assertRaisesRegex(ValueError, "Missing"):
            compare_frame(374, self.source[374], native, None)

    def test_every_logical_field_mutation_rejects_parameterized(self):
        for field in ("sheet", "dimensions", "sourceRectangle", "position", "origin", "scale", "rotation", "color", "effects"):
            with self.subTest(field=field):
                native = copy.deepcopy(self.native[374]);row = native["commands"][1]
                if isinstance(row[field], list):
                    row[field][0] += 1
                elif isinstance(row[field], str):
                    row[field] += "changed"
                else:
                    row[field] += 1
                with self.assertRaisesRegex(ValueError, "logical " + field):
                    compare_frame(374, self.source[374], native, None)

    def test_single_float_bit_mutation_rejects(self):
        native = copy.deepcopy(self.native[374]);row = native["commands"][0]
        bits = struct.unpack("<I", struct.pack("<f", row["position"][0]))[0]
        row["position"][0] = struct.unpack("<f", struct.pack("<I", bits ^ 1))[0]
        with self.assertRaisesRegex(ValueError, "logical position"):
            compare_frame(374, self.source[374], native, None)

    def test_dispatch_binding_rejects(self):
        native = copy.deepcopy(self.native[374]);native["commands"][0]["dispatchIndex"] += 1
        with self.assertRaisesRegex(ValueError, "dispatch binding"):
            compare_frame(374, self.source[374], native, None)

    def test_row1_is_clipped_not_logical_frame_height(self):
        row = self.native[374]["commands"][1]
        self.assertEqual(row["sourceRectangle"][2:], [8, 4])


class JumpThruCatalogEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.environ.get("CELESTE_JUMPTHRU_CATALOG_RECEIPT")
        if not path:
            raise unittest.SkipTest("Requires fresh private JumpThru catalog receipt")
        cls.receipt = json.loads(Path(path).read_text())
        cls.paths = {name: Path(value["path"]) for name, value in cls.receipt["inputs"].items()}
        cls.inputs = {name: path.read_bytes() for name, path in cls.paths.items()}

    def test_catalog_regenerates_from_actual_pinned_inputs(self):
        self.assertEqual(encode(self.inputs), Path(self.receipt["output"]["path"]).read_bytes())

    def test_each_actual_input_pin_mutation_rejects_parameterized(self):
        for name in PINS:
            with self.subTest(name=name):
                inputs = dict(self.inputs);inputs[name] += b"tampered"
                with self.assertRaisesRegex(ValueError, "input pin changed: " + name):
                    encode(inputs)

    def test_bad_pin_creates_no_output(self):
        with tempfile.TemporaryDirectory(dir=Path(self.receipt["output"]["path"]).parent.parent) as directory:
            directory = Path(directory);bad = directory / "bad-source"
            bad.write_bytes(b"changed")
            paths = dict(self.paths);paths["platform"] = bad
            output = directory / "catalog" / "jumpthru.txt"
            with self.assertRaisesRegex(ValueError, "input pin changed"):
                prepare(paths, output)
            self.assertFalse(output.parent.exists())

    def test_existing_output_is_never_overwritten(self):
        path = Path(self.receipt["output"]["path"])
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "private and fresh"):
            prepare(self.paths, path)
        self.assertEqual(path.read_bytes(), before)
