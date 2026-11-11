import copy
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
from compare_native_room_transition import source_projection,native_projection,compare,read_rows,validate_native_end
from compare_room_transition_contract import same
from native_room_revision import file_identity

class NativeTransitionProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        native=ROOT/".audit/native-room-transition/native-implementation-01/idle-selector-correction-01/native-release.jsonl"
        source=ROOT/".audit/native-room-transition/source-contract-01/frozen-source-02/trace.jsonl"
        rooms=ROOT/".audit/native-room-transition/source-contract-01/frozen-profile-02/two-rooms.json"
        if not all(path.is_file() for path in (native,source,rooms)):
            raise unittest.SkipTest("Actual private native/SOURCE observations are unavailable")
        if file_identity(source)["sha256"]!="10dd86fba9c9fc5232abb41653e1825bb1c505e81515088c1b5b1fdf9293d594":
            raise ValueError("Immutable SOURCE recording changed")
        cls.source=read_rows(source);cls.native=read_rows(native);cls.rooms=json.loads(rooms.read_text())
        cls.expected,_=source_projection(cls.source,cls.rooms)
    def compare_projection(self,native):
        actual=native_projection(native)
        same(self.expected,actual,"entire-native-transition-projection")
    def state(self,rows,tick,phase="before-eof"):
        return next(row["state"] for row in rows if row.get("event")=="phase" and row["tick"]==tick and row["phase"]==phase)
    def test_actual_native_projection_is_exact_for_the_entire_route(self):
        self.compare_projection(self.native)
    def test_full_route_and_negative_api_guards_compare_exactly(self):
        self.assertEqual(compare(self.source,self.native,self.rooms)["phases_compared"],2570)
    def test_omitted_idle_recovery_is_rejected(self):
        changed=copy.deepcopy(self.native);self.state(changed,492)["animation"]=""
        with self.assertRaisesRegex(ValueError,"animation"):
            compare(self.source,changed,self.rooms)
    def test_recreated_player_is_rejected(self):
        changed=copy.deepcopy(self.native);self.state(changed,380)["player"]+=100000
        with self.assertRaisesRegex(ValueError,"Recreated"):
            self.compare_projection(changed)
    def test_recreated_presentation_is_rejected(self):
        changed=copy.deepcopy(self.native);self.state(changed,380)["presentation"]+=100000
        with self.assertRaisesRegex(ValueError,"Recreated"):
            self.compare_projection(changed)
    def test_early_room_commit_is_rejected(self):
        changed=copy.deepcopy(self.native);self.state(changed,373)["room"]="2"
        with self.assertRaises(ValueError):self.compare_projection(changed)
    def test_incorrect_transition_filter_is_rejected(self):
        changed=copy.deepcopy(self.native)
        berry=next(entity for entity in self.state(changed,380)["entities"] if entity["kind"]=="strawberry")
        berry["wobble"]=0.1
        with self.assertRaises(ValueError):self.compare_projection(changed)
    def test_integer_clock_float_coercion_is_rejected(self):
        changed=copy.deepcopy(self.native);self.state(changed,380)["sessionTime"]=57499769.0
        with self.assertRaisesRegex(ValueError,"Type mismatch"):
            self.compare_projection(changed)
    def test_world_origin_loss_is_rejected(self):
        changed=copy.deepcopy(self.native);self.state(changed,380)["bounds"][0]=0
        with self.assertRaises(ValueError):self.compare_projection(changed)
    def test_missing_platform_is_rejected(self):
        changed=copy.deepcopy(self.native);state=self.state(changed,380);state["entities"]=[entity for entity in state["entities"] if entity["kind"]!="jump_thru"]
        with self.assertRaises(ValueError):self.compare_projection(changed)
    def test_outgoing_leak_is_rejected(self):
        changed=copy.deepcopy(self.native);old=copy.deepcopy(next(entity for entity in self.state(changed,380)["entities"] if entity.get("room")=="1"))
        self.state(changed,413)["entities"].append(old)
        with self.assertRaises(ValueError):self.compare_projection(changed)
    def test_rng_word_float_coercion_is_rejected(self):
        changed=copy.deepcopy(self.native);self.state(changed,380)["rng"]["words"][0]=1.0
        with self.assertRaisesRegex(ValueError,"exact integer"):
            self.compare_projection(changed)
    def test_actual_negative_api_guards_ran_after_the_route(self):
        validate_native_end(self.native,514,2)
    def test_guard_bypass_is_rejected(self):
        changed=copy.deepcopy(self.native)
        next(row for row in changed if row.get("event")=="native-guard")["rejected"]=False
        with self.assertRaises(ValueError):validate_native_end(changed,514,2)
    def test_guard_boolean_integer_coercion_is_rejected(self):
        changed=copy.deepcopy(self.native)
        next(row for row in changed if row.get("event")=="native-guard")["rejected"]=1
        with self.assertRaisesRegex(ValueError,"Type mismatch"):
            validate_native_end(changed,514,2)
    def test_retained_hidden_outgoing_room_ownership_is_rejected(self):
        changed=copy.deepcopy(self.native);self.state(changed,413)["ownsOutgoingRoom"]=True
        with self.assertRaisesRegex(ValueError,"native-outgoing-room-ownership"):
            self.compare_projection(changed)
    def test_unrepresented_source_entity_leaf_is_rejected(self):
        changed=copy.deepcopy(self.source)
        self.state(changed,380)["entities"][0]["newSemanticLeaf"]=True
        with self.assertRaisesRegex(ValueError,"Unknown SOURCE entity leaf"):
            source_projection(changed,self.rooms)
