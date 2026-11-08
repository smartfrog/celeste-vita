import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / "scripts"))
from native_room_replay import replay_intent, verify_replay_intent, verify_replay_guest, completion_receipt
from smoke_native_room import main


def completed_replay_log():
    rows=["Celeste native room DIAGNOSTIC boot revision=synthetic fixed_step=1/60",
          f"guest replay fixture=first_room_climb_dash_v1 fixture_sha256={replay_intent()['sha256']} input_source=scripted_guest_controls max_frames=250 physical_controller_verified=false host_input_injected=false",
          "assets ready", "frame ready",
          "input frame=120 cross_held=1 cross_pressed=1",
          "jump frame=121 x=17 y=142 resets=0 jump_kind=Jump",
          "input frame=124 cross_held=0 cross_pressed=0",
          "frame_saved path=ux0:data/celeste_native_room-synthetic.ppm width=960 height=544"]
    for frame,event,y,stamina,state,grab,ground in (
        (133,"entered",132,110,1,1,0),(143,"drained",130,107,1,1,0),(147,"held",128,106,1,1,0),
        (149,"released",128,105,0,0,0),(161,"landed",144,110,0,0,1)):
        rows.append(f"climb {event} frame={frame} x=12 y={y} stamina={stamina} state={state} grab={grab} ground={ground} dead=0 resets=0")
    rows += ["manual reset frame=163 x=19 y=144 dead=0 resets=1 state=0",
             "jump frame=167 x=19 y=142 resets=1 state=0 jump_kind=Jump",
             "frame frame=167 x=19 y=142 vx=0.000 vy=-105.000 ground=1 dead=0 resets=1",
             "input frame=173 square_held=1 square_pressed=1",
             "dash transition frame=174 from=0 to=2 freeze=0.050000001 dashes=0",
             "freeze transition frame=174 from=0 to=1 state=2",
             "freeze transition frame=177 from=1 to=0 state=2",
             "dash launch frame=178 dir_x=0.000000 dir_y=-1.000000 vx=0.000 vy=-240.000",
             "dash transition frame=189 from=2 to=0 freeze=0.000000000",
             "input frame=192 x=1 y=0 cross_held=0 cross_pressed=0",
             "death frame=242 x=76 y=168 vx=0.000 vy=0.000 ground=0 dead=1 resets=1",
             "input frame=245 buttons=00001000 reset=1 exit=0",
             "manual reset frame=246 x=19 y=144 vx=0.000 vy=0.000 ground=0 dead=0 resets=2 state=0",
             "input frame=249 buttons=00000008 x=0 y=0 reset=0 exit=1",
             "clean exit frame=249 x=19 y=144 vx=0.000 vy=0.000 ground=1 dead=0 resets=2 state=0",
             "guest replay completed samples=250"]
    return "\n".join(rows)+"\n"


class ReplayIntentTests(unittest.TestCase):
    def test_intent_pins_exact_typed_fixture_source(self):
        intent = replay_intent()
        self.assertEqual(intent["sha256"],hashlib.sha256((ROOT / intent["source"]).read_bytes()).hexdigest())
        self.assertEqual(intent["id"],"first_room_climb_dash_v1")
        self.assertEqual(intent["frames"],250)

    def test_tampered_fixture_intent_rejected(self):
        intent = replay_intent() | {"sha256":"0"*64}
        with self.assertRaisesRegex(ValueError,"fixture"):
            verify_replay_intent({"guest_replay":intent},True)

    def test_manual_package_cannot_silently_be_replayed(self):
        with self.assertRaisesRegex(ValueError,"intent"):
            verify_replay_intent({},True)

    def test_replay_package_cannot_silently_be_manual(self):
        with self.assertRaisesRegex(ValueError,"intent"):
            verify_replay_intent({"guest_replay":replay_intent()},False)

    def test_manual_default_retains_absent_intent_compatibility(self):
        verify_replay_intent({},False)

    def test_start_receipt_does_not_claim_physical_controller(self):
        self.assertEqual(completion_receipt("synthetic"),
            "complete revision=synthetic input_source=scripted_guest_controls fixture=first_room_climb_dash_v1 status=0\n")

    def test_observed_complete_guest_replay_is_accepted(self):
        self.assertEqual(verify_replay_guest(completed_replay_log(),"synthetic",replay_intent())["samples"],250)

    def test_each_required_terminal_checkpoint_is_mandatory_parameterized(self):
        for marker in ("jump frame=121","climb entered","climb drained","climb held","climb released","climb landed",
                       "freeze transition frame=174","freeze transition frame=177","dash launch","dash transition frame=189",
                       "death frame=242","input frame=245","manual reset frame=246","input frame=249","clean exit frame=249",
                       "guest replay completed samples=250","fixture_sha256="):
            with self.subTest(marker=marker), self.assertRaises(ValueError):
                verify_replay_guest(completed_replay_log().replace(marker,"missing checkpoint"),"synthetic",replay_intent())


class ReplayHostBoundaryTests(unittest.TestCase):
    def test_guest_mode_timeout_never_opens_x11_or_ctypes_and_cleans_only_owned_runtime(self):
        feedback,order=self.run_scenario("timeout")
        self.assertEqual(order,["installer","runtime"])
        self.assertFalse(feedback["stages"]["full_completion"])

    def test_success_requires_closed_guest_frame_receipt_and_observed_events_without_host_input(self):
        feedback,order=self.run_scenario("complete")
        self.assertTrue(feedback["stages"]["full_completion"])
        self.assertTrue(feedback["stages"]["clean_exit"])
        self.assertEqual(order,["installer","runtime"])

    def test_closed_completion_without_native_frame_is_partial(self):
        feedback,_=self.run_scenario("no_frame")
        self.assertFalse(feedback["stages"]["full_completion"])

    def test_existing_frame_without_post_close_guest_log_marker_is_not_collected(self):
        feedback,_=self.run_scenario("unclosed_frame")
        self.assertFalse(feedback["stages"]["native_image"])
        self.assertFalse(feedback["stages"]["full_completion"])

    def test_invalid_completion_receipt_is_partial(self):
        feedback,_=self.run_scenario("bad_receipt")
        self.assertFalse(feedback["stages"]["full_completion"])

    def test_native_frame_survives_missing_guest_events_without_false_success(self):
        feedback,_=self.run_scenario("missing_events")
        self.assertTrue(feedback["stages"]["native_image"])
        self.assertFalse(feedback["stages"]["full_completion"])

    def test_guest_failure_receipt_aborts_without_waiting_for_completion(self):
        feedback,_=self.run_scenario("guest_failure")
        self.assertFalse(feedback["stages"]["full_completion"])

    def run_scenario(self,mode):
        directory = ROOT / ".audit/native-room-vita/replay-tests"
        directory.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory) as temporary:
            root=Path(temporary)
            fs,output,config,vpk=root/"state",root/"output",root/"config.yml",root/"synthetic.vpk"
            (fs/"ux0/app").mkdir(parents=True)
            (fs/"ux0/data").mkdir()
            config.write_text("backend-renderer: OpenGL\nresolution-multiplier: 1\ndisable-surface-sync: false\n")
            import zipfile
            payload=json.dumps({"revision":"synthetic","tracked_changes":False,"guest_replay":replay_intent()}).encode()
            member="assets/native-room/provenance.json"
            with zipfile.ZipFile(vpk,"w") as package: package.writestr(member,payload)
            order=[]
            class Process:
                def __init__(self,label,pid): self.label,self.pid,self.returncode=label,pid,None
                def terminate(self): order.append(self.label); self.returncode=-15
                def wait(self,timeout=None): return self.returncode
            installer,runtime=Process("installer",101),Process("runtime",102)
            def launch(*args,**kwargs):
                self.assertEqual(args[0][0],"bwrap")
                if not (fs/"ux0/app/CELR00001").exists():
                    destination=fs/"ux0/app/CELR00001"/member
                    destination.parent.mkdir(parents=True)
                    destination.write_bytes(payload)
                    return installer
                if mode!="timeout":
                    data=fs/"ux0/data"
                    (data/"celeste_native_room.ready").write_text("ready frame=0\n")
                    text=completed_replay_log()
                    if mode=="unclosed_frame": text=text.replace("frame_saved path=","not a closed frame path=")
                    (data/"celeste_native_room.log").write_text(text.replace("death frame=242","missing events") if mode=="missing_events" else text)
                    (data/"celeste_native_room-complete-synthetic.txt").write_text("invalid\n" if mode=="bad_receipt" else completion_receipt("synthetic"))
                    (output/"host.log").write_text("[on_game_closed]: Game closed: Celeste Native Room Diagnostic\n")
                    if mode=="guest_failure": (data/"celeste_native_room-failure-synthetic.txt").write_text("synthetic guest failure")
                return runtime
            arguments=["smoke_native_room.py","--guest-replay","--after-climb","--state",str(fs),"--output",str(output),"--vpk",str(vpk)]
            with patch("sys.argv",arguments), patch("smoke_native_room.prepare",return_value=(fs,config)), \
                 patch("smoke_native_room.source_state",return_value=("synthetic",[])), \
                 patch("smoke_native_room.X11",side_effect=AssertionError("No X11 or XTEST")), \
                 patch("smoke_native_room.C.CDLL",side_effect=AssertionError("No ctypes libraries")), \
                 patch("builtins.input",side_effect=AssertionError("No interactive input")), \
                 patch("smoke_native_room.collect_native_frame",return_value=None if mode=="no_frame" else {"artifacts":{},"black_letterbox_rows":True,"nonzero_rgb_bytes":1}), \
                 patch("smoke_native_room.subprocess.Popen",side_effect=launch), \
                 patch("smoke_native_room.os.pidfd_open",side_effect=[201,202]), patch("smoke_native_room.os.close"), \
                 patch("smoke_native_room.select.select",side_effect=TimeoutError("synthetic unattended timeout")):
                if mode=="complete": main()
                else:
                    error=TimeoutError if mode=="timeout" else ValueError if mode in {"bad_receipt","missing_events"} else RuntimeError
                    with self.assertRaises(error): main()
            self.assertEqual(order,["installer","runtime"])
            feedback=json.loads((output/"feedback.json").read_text())
            self.assertFalse(feedback["physical_controller_verified"])
            self.assertFalse(feedback["host_input_injected"])
            self.assertEqual(feedback["portal_requests"],0)
            self.assertEqual(feedback["input_source"],"scripted_guest_controls")
            self.assertEqual(json.loads((output/"x11-input.json").read_text()),[])
            return feedback,order


if __name__ == "__main__": unittest.main()
