import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"scripts"))
from prepare_native_transition_fixture import room_records, catalog_text

class NativeTransitionFixtureTests(unittest.TestCase):
    def room(self):
        return {"attributes":{"name":"lvl_2","x":240,"y":-184,"width":320,"height":184},"children":[
            {"name":"entities","children":[
                {"name":"player","attributes":{"id":0,"x":24,"y":160}},
                {"name":"spikesUp","attributes":{"id":8,"x":160,"y":112,"type":"default","width":40}},
                {"name":"jumpThru","attributes":{"id":7,"x":8,"y":160,"width":40,"texture":"default"}}]}]}
    def test_authored_texture_type_cannot_overwrite_mechanical_kind(self):
        record=room_records([self.room()])[0]
        self.assertEqual(record["objects"][0],["spike_up",8,400,-72,40])
    def test_normalized_spawn_and_seed_come_from_room_fields(self):
        record=room_records([self.room()])[0]
        self.assertEqual((record["bounds"],record["spawn"],record["load_seed"]),([240,-184,320,180],[264,-24],50))
    def test_catalog_preserves_authored_order(self):
        text=catalog_text(room_records([self.room()]))
        self.assertLess(text.index("spike_up"),text.index("jump_thru"))
    def test_unknown_entity_fails_closed(self):
        room=self.room();room["children"][0]["children"].append({"name":"puffer","attributes":{"id":99,"x":0,"y":0}})
        with self.assertRaisesRegex(ValueError,"Unsupported"):
            room_records([room])
