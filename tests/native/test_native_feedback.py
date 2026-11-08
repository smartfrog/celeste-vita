import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / "scripts"))
from feedback_native_room import main
from native_room_feedback import collect_native_frame, RENDER_STAGE


class NativeFeedbackTests(unittest.TestCase):
    def test_closed_black_guest_file_is_retained_and_losslessly_converted(self):
        directory = ROOT / ".audit/native-room-vita/correction-tests"
        directory.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory) as temporary:
            root = Path(temporary)
            fs, output = root / "synthetic-state", root / "artifacts"
            source = fs / "ux0/data/celeste_native_room-synthetic.ppm"
            source.parent.mkdir(parents=True)
            output.mkdir()
            data = b"P6\n960 544\n255\n"+bytes(960*544*3)
            source.write_bytes(data)
            Path(str(source)+".txt").write_text(
                f"frame_saved path=ux0:data/celeste_native_room-synthetic.ppm width=960 height=544 revision=synthetic stage={RENDER_STAGE} "
                "frame=0 x=19 y=144 vx=0 vy=0 ground=0 dead=0 resets=0 format=P6_RGB_top_down\n")
            frame = collect_native_frame(fs,output,"synthetic")
            self.assertEqual(frame["nonzero_rgb_bytes"],0)
            self.assertEqual((output / "native-frame.ppm").read_bytes(),data)
            self.assertTrue((output / "native-frame.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(set(frame["artifacts"]),{"native-frame.ppm","native-frame.png","native-frame.txt"})

    def test_dirty_source_failure_preserves_structured_partial_feedback(self):
        directory = ROOT / ".audit/native-room-vita/correction-tests"
        directory.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory) as temporary:
            output = Path(temporary) / "synthetic-feedback"
            with patch("sys.argv",["feedback_native_room.py","--output",str(output)]), \
                 patch("feedback_native_room.source_state",return_value=("synthetic",[" M src/input.cpp"])):
                with self.assertRaisesRegex(ValueError,"Current source/config"):
                    main()
            feedback = json.loads((output / "feedback.json").read_text())
            self.assertEqual(feedback["revision"],"synthetic")
            self.assertFalse(any(feedback["stages"].values()))
            self.assertIn("Current source/config",feedback["errors"][0]["message"])
            self.assertEqual(feedback["commands"],[])
