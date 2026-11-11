import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / "scripts"))
from feedback_native_room import main
from native_room_feedback import collect_native_frame, RENDER_STAGE
from smoke_native_room import main as smoke_main, KEYBOARD_MAPPING


class NativeFeedbackTests(unittest.TestCase):
    def test_post_wall_jump_receipt_records_actual_frame_and_kind(self):
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as temporary:
            root = Path(temporary)
            source = root / "ux0/data/celeste_native_room-synthetic.ppm"
            source.parent.mkdir(parents=True)
            output = root / "output"
            output.mkdir()
            source.write_bytes(b"P6\n960 544\n255\n" + bytes(960*544*3))
            Path(str(source)+".txt").write_text(
                f"frame_saved path=ux0:data/celeste_native_room-synthetic.ppm width=960 height=544 revision=synthetic stage={RENDER_STAGE} "
                "frame=6 x=15 y=134 vx=130 vy=-105 ground=0 dead=0 resets=0 state=0 jump_kind=WallJump capture=wall_jump format=P6_RGB_top_down\n")
            frame = collect_native_frame(root,output,"synthetic",capture="wall_jump")
            self.assertEqual(frame["frame_state"]["frame"],6)
            self.assertEqual(frame["jump_kind"],"WallJump")

    def test_private_config_is_prepared_before_it_is_frozen(self):
        directory = ROOT / ".audit/native-room-vita/correction-tests"
        directory.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory) as temporary:
            root = Path(temporary)
            fs, config, output, vpk = root / "state", root / "config.yml", root / "output", root / "synthetic.vpk"
            (fs / "ux0/app").mkdir(parents=True)
            config.write_text("backend-renderer: OpenGL\nresolution-multiplier: 1\ndisable-surface-sync: false\n")
            with config.open("a") as stream:
                stream.write("".join(f"keyboard-button-{button}: {key}\n" for button, key in KEYBOARD_MAPPING.items()))
            with zipfile.ZipFile(vpk,"w") as package:
                package.writestr("assets/native-room/provenance.json",json.dumps({"revision":"synthetic","tracked_changes":False}))
            appdir = root / "appdir"
            (appdir / "usr/bin").mkdir(parents=True)
            (appdir / "usr/bin/Vita3K").write_bytes(b"synthetic")
            (appdir / "apprun-hooks").mkdir()
            (appdir / "apprun-hooks/linuxdeploy-plugin-qt-hook.sh").write_text("synthetic hook\n")
            with patch("sys.argv",["smoke_native_room.py","--state",str(fs),"--output",str(output),"--vpk",str(vpk),"--appdir",str(appdir),"--frame-only"]), \
                 patch("smoke_native_room.prepare",return_value=(fs,config)) as prepared, \
                 patch("smoke_native_room.X11",side_effect=RuntimeError("stop before X11")):
                with self.assertRaisesRegex(RuntimeError,"stop before X11"):
                    smoke_main()
            prepared.assert_called_once()
            self.assertEqual((output / "effective-config.yml").read_bytes(),config.read_bytes())
            feedback = json.loads((output / "feedback.json").read_text())
            self.assertFalse(feedback["emulator_config"]["disable_surface_sync"])

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
