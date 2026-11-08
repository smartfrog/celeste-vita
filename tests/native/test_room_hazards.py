import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from prepare_room_hazards import room_hazards, hazard_fixtures
from compare_hazard_traces import fixture_operations


def synthetic_map():
    entities = [{"name": "player", "attributes": {"id": 0, "x": 19, "y": 144}}]
    for i in range(5):
        entities.append({"name": "spikesUp" if i < 4 else "spikesLeft",
                         "attributes": {"id": i + 1, "x": 8 + i * 16, "y": 16 + i * 8, "width": 8, "height": 8}})
    entities.append({"name": "goldenBerry", "attributes": {"id": 6}})
    solids = "1" * 363 + "0" * (40 * 23 - 363)
    room = {"attributes": {"name": "lvl_1", "x": 0, "y": 0, "width": 320, "height": 184},
            "children": [{"name": "solids", "attributes": {"innerText": "\n".join(solids[i:i+40] for i in range(0, len(solids), 40))}},
                         {"name": "entities", "children": entities}]}
    return {"children": [{"name": "levels", "children": [room]}]}


class RoomHazardPreparationTests(unittest.TestCase):
    def test_synthetic_map_preserves_hazard_order_and_sizes(self):
        facts, hazards = room_hazards(synthetic_map())
        self.assertEqual([h["map_order"] for h in hazards], [1, 2, 3, 4, 5])
        self.assertEqual([h["entity_id"] for h in hazards], [1, 2, 3, 4, 5])
        self.assertEqual([h["direction"] for h in hazards], ["up"] * 4 + ["left"])
        self.assertEqual(facts["spawns"], [[19, 144]])

    def test_generated_fixture_has_all_spikes_for_every_probe(self):
        facts, hazards = room_hazards(synthetic_map())
        fixture = hazard_fixtures((0, 0, 2, 2, "0000"), facts, hazards)
        directory = ROOT / ".audit/native-room-hazards/preparation-tests"
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory) as temporary:
            path = Path(temporary) / "synthetic.fixtures"
            path.write_text(fixture)
            snapshots = fixture_operations(path)
        self.assertEqual(len(snapshots), 11)
        self.assertEqual(fixture.count("spike "), 55)
        self.assertEqual(fixture.count("grid "), 11)

    def test_invalid_hazard_profile_parameterized(self):
        for kind in ("direction", "zero_size", "duplicate", "missing", "golden"):
            with self.subTest(kind=kind):
                root = copy.deepcopy(synthetic_map())
                entities = root["children"][0]["children"][0]["children"][1]["children"]
                if kind == "direction":
                    entities[1]["name"] = "spikesDown"
                elif kind == "zero_size":
                    entities[1]["attributes"]["width"] = 0
                elif kind == "duplicate":
                    entities[2]["attributes"]["id"] = 1
                elif kind == "missing":
                    del entities[1]
                else:
                    entities.pop()
                with self.assertRaises(ValueError):
                    room_hazards(root)
