from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from native_room_feedback import collect_native_frame, RENDER_STAGE
from smoke_native_room import verify_climb_guest


class ClimbFeedbackTests(unittest.TestCase):
    def collect(self, **overrides):
        temporary = tempfile.TemporaryDirectory(dir="/tmp/opencode")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source = root / "ux0/data/celeste_native_room-synthetic.ppm"
        source.parent.mkdir(parents=True)
        output = root / "output"
        output.mkdir()
        source.write_bytes(b"P6\n960 544\n255\n" + bytes(960*544*3))
        metadata = dict(path="ux0:data/celeste_native_room-synthetic.ppm", width=960, height=544, revision="synthetic", stage=RENDER_STAGE,
                        frame=35, x=12, y=130, vx=0, vy=-45, ground=0, dead=0, resets=0, state=1, stamina=105, grab=1,
                        jump_kind="Jump", capture="climb", format="P6_RGB_top_down")
        metadata.update(overrides)
        Path(str(source)+".txt").write_text("frame_saved " + " ".join(f"{key}={value}" for key,value in metadata.items()) + "\n")
        return collect_native_frame(root, output, "synthetic", capture="climb")

    def test_airborne_drained_climb_receipt_is_preserved(self):
        self.assertEqual(self.collect()["frame_state"]["stamina"], 105)

    def test_invalid_climb_receipt_is_rejected_parameterized(self):
        for values in ({"ground":1}, {"state":0}, {"stamina":110}, {"stamina":0}, {"grab":0}, {"frame":0}, {"stamina":"nan"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.collect(**values)

    def test_complete_climb_log_requires_ordered_ascent_drain_release_landing(self):
        rows = []
        for frame, event, y, stamina, state, grab, ground in (
            (12,"entered",132,110,1,1,0), (23,"drained",131,108,1,1,0),
            (27,"held",130,107,1,1,0), (28,"released",130,107,0,0,0), (45,"landed",144,110,0,0,1)):
            rows.append(f"climb {event} frame={frame} x=12 y={y} stamina={stamina} state={state} grab={grab} ground={ground} dead=0 resets=0")
        self.assertEqual(len(verify_climb_guest("\n".join(rows))), 5)

    def test_missing_climb_log_cannot_claim_completion(self):
        with self.assertRaises(ValueError):
            verify_climb_guest("")
