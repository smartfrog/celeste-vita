import hashlib
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / "scripts"))
from native_room_replay import replay_intent, verify_replay_intent, verify_replay_guest, completion_receipt
from smoke_native_room import main
from native_room_feedback import collect_native_frame


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
        self.assertEqual(order,["installer"])

    def test_closed_completion_without_native_frame_is_partial(self):
        feedback,_=self.run_scenario("no_frame")
        self.assertTrue(feedback["stages"]["clean_exit"])
        self.assertFalse(feedback["stages"]["full_completion"])

    def test_existing_pair_skip_preserves_guest_checks_but_claims_no_current_run_capture(self):
        feedback,_=self.run_scenario("skip_existing")
        self.assertTrue(feedback["stages"]["input"])
        self.assertTrue(feedback["stages"]["clean_exit"])
        self.assertFalse(feedback["stages"]["native_image"])
        self.assertFalse(feedback["stages"]["full_completion"])
        self.assertIn("current-run",feedback["errors"][-1]["message"])

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

    def test_host_crash_after_guest_exit_keeps_proven_guest_stages_but_not_full_completion(self):
        feedback,order=self.run_scenario("host_failure",host_exit_code=133)
        self.assertTrue(feedback["stages"]["input"])
        self.assertTrue(feedback["stages"]["clean_exit"])
        self.assertTrue(feedback["stages"]["native_image"])
        self.assertFalse(feedback["stages"]["full_completion"])
        self.assertEqual(order,["installer"])
        self.assertIn("133",feedback["errors"][0]["message"])

    def test_host_wait_timeout_cleanup_crash_keeps_verified_guest_but_is_partial(self):
        feedback,order=self.run_scenario("host_timeout",host_exit_code=None,cleanup_exit_code=133)
        self.assertTrue(feedback["stages"]["input"])
        self.assertTrue(feedback["stages"]["clean_exit"])
        self.assertTrue(feedback["stages"]["native_image"])
        self.assertFalse(feedback["stages"]["full_completion"])
        self.assertEqual(feedback["errors"][0]["type"],"TimeoutError")
        self.assertIn("30 seconds",feedback["errors"][0]["message"])
        self.assertEqual(feedback["host_events"][-1]["host_exit_code"],133)
        self.assertEqual(order,["installer","runtime"])

    def test_host_wait_timeout_cleanup_never_promotes_completion_parameterized(self):
        for cleanup_exit_code in (-15,0):
            with self.subTest(cleanup_exit_code=cleanup_exit_code):
                feedback,_=self.run_scenario("host_timeout",host_exit_code=None,cleanup_exit_code=cleanup_exit_code)
                self.assertTrue(feedback["stages"]["input"])
                self.assertTrue(feedback["stages"]["clean_exit"])
                self.assertTrue(feedback["stages"]["native_image"])
                self.assertFalse(feedback["stages"]["full_completion"])
                self.assertEqual(feedback["errors"][0]["type"],"TimeoutError")
                self.assertEqual(feedback["host_events"][-1]["host_exit_code"],cleanup_exit_code)

    def run_scenario(self,mode,host_exit_code=0,cleanup_exit_code=-15,automatic=False,frame_fixture=None,dash_probe=False,
                     late_failure_kind=None,late_failure_phase='host_wait'):
        directory = ROOT / ".audit/native-room-vita/replay-tests"
        directory.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory) as temporary:
            root=Path(temporary)
            fs,output,config,vpk=root/"state",root/"output",root/"config.yml",root/"synthetic.vpk"
            (fs/"ux0/app").mkdir(parents=True)
            (fs/"ux0/data").mkdir()
            config.write_text("backend-renderer: OpenGL\nresolution-multiplier: 1\ndisable-surface-sync: false\n")
            appdir = root / "appdir"
            (appdir / "usr/bin").mkdir(parents=True)
            (appdir / "usr/bin/Vita3K").write_bytes(b"synthetic")
            (appdir / "apprun-hooks").mkdir()
            (appdir / "apprun-hooks/linuxdeploy-plugin-qt-hook.sh").write_text("synthetic hook\n")
            import zipfile
            provenance={"revision":"synthetic","tracked_changes":False,
                        "guest_replay":None if automatic or dash_probe else replay_intent(),
                        "guest_automatic":"first_room_auto_death_v2" if automatic else None,
                        "guest_automatic_fixture":dict(id="first_room_auto_death_v2", samples=365, exit_frame=364,
                                                       source="src/vita/guest_automatic_replay.hpp",sha256="e"*64) if automatic else None}
            if automatic:
                provenance.update(render_style="animated_player_partial",player={"death_animation_extension":True})
            if dash_probe:
                from test_dash_probe_runtime import probe_fixture, probe_completion
                provenance.update(guest_dash_probe=probe_fixture()['id'],guest_dash_probe_fixture=probe_fixture())
            suffix = '-dash-probe' if dash_probe else ''
            closed = probe_completion() if dash_probe else completion_receipt('synthetic',automatic=automatic)
            if frame_fixture:
                provenance.update(frame_fixture["provenance"])
            payload=json.dumps(provenance).encode()
            member="assets/native-room/provenance.json"
            with zipfile.ZipFile(vpk,"w") as package: package.writestr(member,payload)
            order=[]
            failure = fs / f'ux0/data/celeste_native_room-failure-synthetic{suffix}.txt'
            late_failure_event = None
            raised_error = None
            def publish_late_failure(phase):
                nonlocal late_failure_event
                self.assertIsNone(late_failure_event)
                self.assertEqual((output/'guest-complete.txt').read_text(),closed)
                self.assertFalse(failure.exists() or failure.is_symlink())
                self.assertNotIn('FATAL',(fs/'ux0/data/celeste_native_room.log').read_text())
                if late_failure_kind=='regular':
                    failure.write_bytes(b'\xffopaque failure')
                elif late_failure_kind=='symlink':
                    target = root / 'failure-target.txt'
                    target.write_bytes(b'\xffopaque failure target')
                    failure.symlink_to(target)
                elif late_failure_kind=='dangling_symlink':
                    failure.symlink_to(root/'missing-failure-target.txt')
                elif late_failure_kind!='unknown':
                    raise ValueError('Unknown late failure fixture kind')
                late_failure_event = dict(phase=phase,kind=late_failure_kind,closed_completion_already_observed=True,
                                          log_still_has_no_FATAL=True,path=str(failure))
            original_lstat = Path.lstat
            def lstat(path,*args,**kwargs):
                if late_failure_event and late_failure_kind=='unknown' and path==failure:
                    raise PermissionError(13,'Synthetic unknown failure-path state',str(path))
                return original_lstat(path,*args,**kwargs)
            class Process:
                def __init__(self,label,pid): self.label,self.pid,self.returncode=label,pid,None
                def terminate(self): order.append(self.label); self.returncode=-15
                def wait(self,timeout=None):
                    if self.label=="runtime":
                        if timeout==30:
                            if late_failure_kind and late_failure_phase=='host_wait': publish_late_failure('host_wait')
                            if host_exit_code is None: raise subprocess.TimeoutExpired("synthetic-owned-runtime",timeout)
                            self.returncode=host_exit_code
                        elif timeout==15:
                            if late_failure_kind and late_failure_phase=='cleanup': publish_late_failure('cleanup')
                            self.returncode=cleanup_exit_code
                    return self.returncode
            installer,runtime=Process("installer",101),Process("runtime",102)
            deferred=[]
            def publish_native_frame():
                if mode=='no_frame': return
                if frame_fixture:
                    source=fs/f"ux0/data/celeste_native_room-synthetic{suffix}.ppm"
                    source.write_bytes(frame_fixture["ppm"])
                    Path(str(source)+".txt").write_text(frame_fixture["receipt"])
                    if dash_probe:
                        Path(str(source)+'.trail.rgba').write_bytes(frame_fixture['raw'])
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
                    if automatic:
                        from test_guest_automatic import completed_automatic_log
                        text=completed_automatic_log()
                    if dash_probe:
                        text=frame_fixture['log']
                    if mode=="unclosed_frame": text=text.replace("frame_saved path=","not a closed frame path=")
                    if mode=="skip_existing": text=text.replace(
                        f"frame_saved path=ux0:data/celeste_native_room-synthetic{suffix}.ppm ",
                        f"capture_skipped_existing path=ux0:data/celeste_native_room-synthetic{suffix}.ppm prior_capture_preserved=ppm_and_receipt current_run_capture=false ")
                    missing = 'frame=40 ' if dash_probe else "frame=36 x=1" if automatic else "death frame=242"
                    if mode=="deferred_frame": deferred.append(text)
                    (data/"celeste_native_room.log").write_text(text.replace(missing,"missing events") if mode=="missing_events" else text)
                    if mode!="deferred_frame":
                        completion_suffix = '' if mode=='wrong_mode_completion' else suffix
                        (data/f"celeste_native_room-complete-synthetic{completion_suffix}.txt").write_text("invalid\n" if mode=="bad_receipt" else closed)
                        publish_native_frame()
                    else:
                        (data/"celeste_native_room.log").write_text(text.replace("frame_saved path=","pending native export path="))
                    (output/"host.log").write_text("sdl frontend closed\n")
                    if mode=="guest_failure": (data/f"celeste_native_room-failure-synthetic{suffix}.txt").write_text("synthetic guest failure")
                    if mode=='wrong_mode_failure': (data/'celeste_native_room-failure-synthetic.txt').write_text('another mode failure')
                    if mode=="config_mutation": config.write_text(config.read_text()+"changed: true\n")
                return runtime
            arguments=["smoke_native_room.py","--guest-replay","--after-climb","--state",str(fs),"--output",str(output),"--vpk",str(vpk),"--appdir",str(appdir)]
            if automatic:
                arguments[1:3]=["--guest-automatic","--source-root",str(root),"--build",str(root/"build"),"--staging",str(root/"staging")]
            if dash_probe:
                arguments[1:3]=['--guest-dash-probe','--source-root',str(root),'--build',str(root/'build'),'--staging',str(root/'staging')]
            automatic_provenance={"source_checkout":str(root),"source":{"state_sha256":"synthetic"},
                                  "package":{"vpk_sha256":hashlib.sha256(vpk.read_bytes()).hexdigest(),
                                              "build_binding":{"capture_policy":"dash_trails" if dash_probe else "initial_respawn"}}}
            if dash_probe:
                automatic_provenance['fixture'] = probe_fixture()
            source_after=automatic_provenance if mode!="source_drift" else automatic_provenance | {"source":{"state_sha256":"changed"}}
            if mode=="source_verify_failure": source_after=ValueError("native source/artifact changed")
            def select_wait(*args):
                if mode!="deferred_frame" or not deferred:
                    raise TimeoutError("synthetic unattended timeout")
                current=json.loads((output/"feedback.json").read_text())
                self.assertTrue(current["stages"]["startup"])
                self.assertFalse(current["stages"]["native_image"])
                publish_native_frame()
                (fs/"ux0/data/celeste_native_room.log").write_text(deferred.pop())
                (fs/"ux0/data/celeste_native_room-complete-synthetic.txt").write_text(completion_receipt("synthetic",automatic=automatic))
                return ([],[],[])
            with patch.dict("os.environ",{"DISPLAY":"unit-test-only.invalid:99.0"}), \
                 patch("sys.argv",arguments), patch("smoke_native_room.prepare",return_value=(fs,config)), \
                 patch("native_room_replay.source_state",return_value=("synthetic",[])), \
                 patch("smoke_native_room.verify_automatic_source",side_effect=[automatic_provenance,source_after]) as source_verifier, \
                 patch("smoke_native_room.verify_dash_probe_source",side_effect=[automatic_provenance,source_after]) as dash_verifier, \
                 patch("smoke_native_room.X11",side_effect=AssertionError("No X11 or XTEST")), \
                 patch("smoke_native_room.C.CDLL",side_effect=AssertionError("No ctypes libraries")), \
                 patch("builtins.input",side_effect=AssertionError("No interactive input")), \
                 patch("smoke_native_room.collect_native_frame",side_effect=collect_native_frame if frame_fixture else None,
                       return_value=None if mode=="no_frame" else {"artifacts":{},"black_letterbox_rows":True,"nonzero_rgb_bytes":1,
                                                                  "capture":"initial_respawn" if automatic else "climb","frame_state":{"frame":36}}), \
                 patch("smoke_native_room.subprocess.Popen",side_effect=launch), \
                 patch("smoke_native_room.os.pidfd_open",side_effect=[201,202]), patch("smoke_native_room.os.close"), \
                 patch.object(Path,'lstat',lstat), \
                 patch("smoke_native_room.select.select",side_effect=select_wait):
                if late_failure_kind:
                    try:
                        main()
                    except (RuntimeError,OSError) as error:
                        raised_error = dict(type=type(error).__name__,message=str(error))
                elif mode in {"complete","deferred_frame","wrong_mode_failure"}: main()
                else:
                    error=TimeoutError if mode in {"timeout","host_timeout","wrong_mode_completion"} else ValueError if mode in {"bad_receipt","missing_events","source_drift","source_verify_failure","invalid_native_frame","wrong_capture_frame"} or dash_probe and mode in {'unclosed_frame','skip_existing'} else RuntimeError
                    with self.assertRaises(error): main()
            if automatic: self.assertEqual(source_verifier.call_count,2)
            if dash_probe: self.assertEqual(dash_verifier.call_count,2)
            self.assertEqual(order,["installer"] if mode in {"complete","deferred_frame","wrong_mode_failure","wrong_capture_frame","host_failure","missing_events","no_frame","unclosed_frame","skip_existing","source_drift","source_verify_failure","config_mutation"} else ["installer","runtime"])
            feedback=json.loads((output/"feedback.json").read_text())
            self.assertNotIn("[on_game_closed]",(output/"host.log").read_text())
            self.assertFalse(feedback["physical_controller_verified"])
            self.assertFalse(feedback["host_input_injected"])
            self.assertEqual(feedback["portal_requests"],0)
            self.assertEqual(feedback["input_source"],"scripted_guest_controls")
            if not automatic and not dash_probe:
                self.assertEqual(feedback["guest_replay_provenance"]["source_checkout"],str(ROOT))
                self.assertEqual(feedback["guest_replay_provenance"]["source_revision"],"synthetic")
                self.assertEqual(feedback["guest_replay_provenance"]["host_harness"]["root"],str(ROOT))
            self.assertEqual(json.loads((output/"x11-input.json").read_text()),[])
            host_events=json.loads((output/"events.json").read_text())
            commands=[event["command"] for event in host_events if "command" in event]
            self.assertEqual(len(commands),2)
            installer,runtime=commands
            for command in commands:
                self.assertIn("--unshare-pid",command)
                self.assertIn("--unshare-net",command)
            self.assertNotIn("--frontend",installer)
            self.assertEqual(runtime[runtime.index("--frontend")+1],"sdl")
            feedback["host_events"]=host_events
            if late_failure_kind:
                self.assertIsNotNone(late_failure_event)
                feedback['late_failure_event'] = late_failure_event
                feedback['raised_error'] = raised_error
            return feedback,order


if __name__ == "__main__": unittest.main()
