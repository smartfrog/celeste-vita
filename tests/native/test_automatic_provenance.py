import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from native_room_replay import (AUTOMATIC_ID, AUTOMATIC_SOURCE, verify_automatic_source,
                                verify_automatic_intent, native_source_identity)
from feedback_native_room import main as feedback_main
from smoke_native_room import main as smoke_main


class AutomaticProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir="/tmp/opencode")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.vpk = self.root / "synthetic.vpk"
        self.vpk.write_bytes(b"explicit mocked native package")
        header = self.root / AUTOMATIC_SOURCE
        header.parent.mkdir(parents=True)
        header.write_text("synthetic input-only header\n")
        self.provenance = dict(guest_automatic=AUTOMATIC_ID, guest_replay=None,
                               render_style="animated_player_partial", player={"death_animation_extension":True})
        source = {"schema":1,"state_sha256":"full-source-identity"}
        self.package = {"staging":self.provenance,"source_before":source,"source_after":source,
                        "vpk_sha256":hashlib.sha256(self.vpk.read_bytes()).hexdigest(),"exact_wip":True,
                        "build_binding":{"source":source,"self_matches_rebuilt_chain":True,"token":"resident","capture_policy":"initial_respawn"}}

    def verify(self, expected=None, package=None):
        result = SimpleNamespace(stdout=json.dumps(self.package if package is None else package))
        with patch("native_room_replay.subprocess.run",return_value=result) as run, \
             patch("native_room_replay.source_state",return_value=("synthetic-host",[" M harness.py"])):
            selected = verify_automatic_source(self.provenance,self.vpk,self.root,self.root/"build/src/vita",self.root/"staging",expected)
        return selected, run.call_args

    def test_exact_wip_is_forwarded_only_by_explicit_manifest_opt_in(self):
        state = self.root / "expected.json"
        selected, call = self.verify(state)
        self.assertFalse(selected["source_clean"])
        self.assertIn(str(self.root/"scripts/verify_native_room_vpk.py"),call.args[0])
        self.assertEqual(call.args[0][-2:],["--expected-source-state",str(state)])
        self.assertEqual(call.kwargs["cwd"],self.root)
        self.assertTrue(call.kwargs["check"])

    def test_clean_default_never_adds_expected_state_or_dirty_fallback(self):
        package = copy.deepcopy(self.package)
        package["exact_wip"] = False
        _, call = self.verify(package=package)
        self.assertNotIn("--expected-source-state",call.args[0])

    def test_native_verifier_rejection_is_propagated_with_no_fallback(self):
        with patch("native_room_replay.subprocess.run",side_effect=subprocess.CalledProcessError(1,["native verifier"],stderr="dirty/tampered resident image")) as run:
            with self.assertRaisesRegex(ValueError,"dirty/tampered"):
                verify_automatic_source(self.provenance,self.vpk,self.root,self.root/"build",self.root/"stage")
        self.assertEqual(run.call_count,1)

    def test_tamper_binding_and_profile_fail_parameterized(self):
        for label in ("vpk", "unbound", "self", "source_drift", "wrong_binding", "provenance"):
            package = copy.deepcopy(self.package)
            if label == "vpk": package["vpk_sha256"] = "stale"
            if label == "unbound": package["build_binding"] = None
            if label == "self": package["build_binding"]["self_matches_rebuilt_chain"] = False
            if label == "source_drift": package["source_after"] = {"state_sha256":"changed"}
            if label == "wrong_binding": package["build_binding"]["source"] = {"state_sha256":"stale"}
            if label == "provenance": package["staging"]["guest_automatic"] = None
            with self.subTest(label=label), self.assertRaises(ValueError):
                self.verify(expected=self.root/"expected.json",package=package)

    def test_mocked_dirty_receipt_cannot_relax_default(self):
        with self.assertRaisesRegex(ValueError,"explicit"):
            self.verify()

    def test_nonproduction_profile_fails_before_external_verification(self):
        self.provenance["player"] = {}
        with patch("native_room_replay.subprocess.run") as run, self.assertRaisesRegex(ValueError,"production"):
            verify_automatic_source(self.provenance,self.vpk,self.root,self.root/"build",self.root/"stage")
        run.assert_not_called()

    def test_wrong_package_modes_are_rejected_parameterized(self):
        for provenance in ({}, {"guest_automatic":"old250"}, {"guest_automatic":AUTOMATIC_ID,"guest_replay":{"id":"old250"}}):
            with self.subTest(provenance=provenance), self.assertRaises(ValueError):
                verify_automatic_intent(provenance,True)

    def test_manual_mode_refuses_an_automatic_package(self):
        with self.assertRaises(ValueError):
            verify_automatic_intent(self.provenance,False)

    def test_native_verifier_rejects_before_state_creation_or_install(self):
        provenance = self.provenance | {"revision":"synthetic","tracked_changes":True}
        with zipfile.ZipFile(self.vpk,"w") as archive:
            archive.writestr("assets/native-room/provenance.json",json.dumps(provenance))
        output = self.root/".audit/native-room-vita/output"
        arguments = ["smoke", "--guest-automatic", "--state",str(self.root/"state"),"--output",str(output),
                     "--vpk",str(self.vpk),"--source-root",str(self.root),"--build",str(self.root/"build"),"--staging",str(self.root/"staging")]
        with patch("sys.argv",arguments), patch("smoke_native_room.REPO_ROOT",self.root), \
             patch("smoke_native_room.prepare") as prepare, patch("smoke_native_room.launch_command") as launch, \
             patch("smoke_native_room.verify_automatic_source",side_effect=ValueError("stale native source/artifact")), \
             self.assertRaisesRegex(ValueError,"stale native"):
            smoke_main()
        prepare.assert_not_called()
        launch.assert_not_called()
        self.assertFalse((self.root/"state").exists())

    def test_old_or_wrong_capture_binding_fails_before_state_or_install_parameterized(self):
        provenance = self.provenance | {"revision":"synthetic","tracked_changes":True}
        with zipfile.ZipFile(self.vpk,"w") as archive:
            archive.writestr("assets/native-room/provenance.json",json.dumps(provenance))
        for policy in (None,"spawn","wall_jump","climb"):
            with self.subTest(policy=policy):
                output = self.root/".audit/native-room-vita"/str(policy)
                arguments = ["smoke","--guest-automatic","--state",str(self.root/"state"),"--output",str(output),
                             "--vpk",str(self.vpk),"--source-root",str(self.root),"--build",str(self.root/"build"),"--staging",str(self.root/"stage")]
                pin = {"package":{"vpk_sha256":hashlib.sha256(self.vpk.read_bytes()).hexdigest(),
                                   "build_binding":{} if policy is None else {"capture_policy":policy}}}
                with patch("sys.argv",arguments), patch("smoke_native_room.REPO_ROOT",self.root), \
                     patch("smoke_native_room.launcher_kind",return_value="linuxdeploy"), \
                     patch("smoke_native_room.prepare",side_effect=AssertionError("Reject before profile preparation")) as prepare, \
                     patch("smoke_native_room.launch_command") as launch, \
                     patch("smoke_native_room.verify_automatic_source",return_value=pin), \
                     self.assertRaisesRegex(ValueError,"capture policy"):
                    smoke_main()
                prepare.assert_not_called()
                launch.assert_not_called()
                self.assertFalse((self.root/"state").exists())


class AutomaticFeedbackTests(unittest.TestCase):
    def run_pipeline(self, final_identity=None):
        directory = ROOT / ".audit/native-room-vita/automatic-wrapper-tests"
        directory.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory) as temporary:
            root = Path(temporary)
            output, native, state = root/"output", root/"native", root/"expected.json"
            commands = {}
            def execute(arguments, **options):
                label = Path(options["stdout"].name).stem
                commands[label] = arguments
                if label == "package": options["stdout"].write(b'{"vpk_sha256":"synthetic"}')
                return SimpleNamespace(returncode=0)
            arguments = ["feedback", "--output",str(output),"--guest-automatic","--source-root",str(native),
                         "--expected-source-state",str(state),"--textured","--visual-dir",str(root/"visuals"),"--player-dir",str(root/"player")]
            identity = {"identity":{"base_head":"synthetic","changes":[" M native.cpp"]}}
            failure = None
            with patch("sys.argv",arguments), patch("feedback_native_room.native_source_identity",side_effect=[identity,final_identity or identity]) as verify, \
                 patch("feedback_native_room.source_state",return_value=("synthetic",[" M native.cpp"])), \
                 patch("feedback_native_room.subprocess.run",side_effect=execute):
                try:
                    feedback_main()
                except RuntimeError as error:
                    failure = error
            feedback = json.loads((output/"feedback.json").read_text())
            self.assertEqual(verify.call_count,2)
            for label in ("stage","package","runtime"):
                self.assertIn("--expected-source-state",commands[label])
            for label in ("stage","runtime"):
                self.assertIn("--guest-automatic",commands[label])
                self.assertNotIn("--guest-replay",commands[label])
            self.assertIn("-DCELESTE_ROOM_GUEST_AUTOMATIC=ON",commands["configure"])
            self.assertIn("-DCELESTE_ROOM_GUEST_REPLAY=OFF",commands["configure"])
            self.assertIn("-DCELESTE_EXPECTED_SOURCE_STATE="+str(state),commands["configure"])
            self.assertEqual(commands["configure"][2:4],[str(native),"-B"])
            self.assertIn(str(native/"scripts/verify_native_room_vpk.py"),commands["package"])
            self.assertIn(str(ROOT/"scripts/smoke_native_room.py"),commands["runtime"])
            return feedback, failure

    def test_mocked_feedback_prepares_native_commands_and_pins_complete_identity(self):
        feedback, failure = self.run_pipeline()
        self.assertIsNone(failure)
        self.assertEqual(feedback["source_before"],feedback["source_after"])
        self.assertEqual(feedback["capture_policy"],"initial_respawn")

    def test_same_head_and_dirty_paths_cannot_hide_complete_identity_drift(self):
        feedback, failure = self.run_pipeline({"identity":{"base_head":"synthetic","changes":[" M native.cpp"],"sha256":"changed-bytes"}})
        self.assertIsInstance(failure,RuntimeError)
        self.assertFalse(feedback["stages"]["full_completion"])
        self.assertIn("Complete native",feedback["errors"][-1]["message"])


class NativeSourceBridgeTests(unittest.TestCase):
    def test_delegates_complete_identity_to_selected_native_implementation(self):
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as temporary:
            source = Path(temporary)
            scripts = source/"scripts"
            scripts.mkdir()
            (scripts/"native_room_revision.py").write_text(
                "def validate_source_state(expected):\n"
                "    if expected != {'synthetic_expected': True}:\n"
                "        raise ValueError('synthetic strict default rejects dirty source')\n"
                "    return {'base_head': 'synthetic', 'sha256': 'complete-synthetic-identity'}\n")
            state = source/"expected.json"
            state.write_text('{"synthetic_expected": true}\n')
            selected = native_source_identity(source,state)
            self.assertEqual(selected["identity"]["sha256"],"complete-synthetic-identity")
            self.assertEqual(selected["expected_manifest_sha256"],hashlib.sha256(state.read_bytes()).hexdigest())

    def test_native_identity_error_has_no_silent_dirty_fallback(self):
        error = subprocess.CalledProcessError(1,["synthetic-native-identity"],stderr="exact source changed")
        with patch("native_room_replay.subprocess.run",side_effect=error) as run, self.assertRaisesRegex(ValueError,"exact source changed"):
            native_source_identity(Path("unused"))
        self.assertEqual(run.call_count,1)


if __name__ == "__main__":
    unittest.main()
