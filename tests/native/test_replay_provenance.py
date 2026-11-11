import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / "scripts"))
from native_room_replay import harness_fingerprint, replay_intent, verify_replay_source
from smoke_native_room import main as smoke_main


class ReplaySourceProvenanceTests(unittest.TestCase):
    def setUp(self):
        directory = ROOT / ".audit/native-room-vita/replay-provenance-tests"
        directory.mkdir(parents=True,exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=directory)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "guest-source"
        (self.repo / "src/vita").mkdir(parents=True)
        shutil.copyfile(ROOT / "src/vita/guest_replay.hpp",self.repo / "src/vita/guest_replay.hpp")
        (self.repo / ".gitignore").write_text(".audit/\n")
        self.git("init","-q")
        self.git("add",".")
        self.git("-c","user.name=Synthetic","-c","user.email=synthetic@example.invalid","commit","-qm","Synthetic guest source")
        self.revision = self.git("rev-parse","HEAD").strip()

    def git(self,*arguments):
        return subprocess.check_output(["git","-C",str(self.repo),*arguments],text=True,stderr=subprocess.STDOUT)

    def provenance(self,**overrides):
        return {"revision":self.revision,"tracked_changes":False,"guest_replay":replay_intent(self.repo)} | overrides

    def test_clean_exact_source_and_fixture_are_accepted(self):
        selected = verify_replay_source(self.provenance(),self.repo,host_root=ROOT)
        self.assertEqual(selected["source_checkout"],str(self.repo.resolve()))
        self.assertEqual(selected["source_revision"],self.revision)
        self.assertTrue(selected["source_clean"])
        self.assertEqual(selected["fixture"],replay_intent(self.repo))
        self.assertEqual(selected["host_harness"]["root"],str(ROOT))
        self.assertEqual(selected["host_harness"]["fingerprint_sha256"],harness_fingerprint(ROOT))

    def test_wrong_source_revision_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"exact VPK source revision"):
            verify_replay_source(self.provenance(revision="0"*40),self.repo,host_root=ROOT)

    def test_missing_source_checkout_is_rejected(self):
        with self.assertRaisesRegex(FileNotFoundError,"Missing replay source checkout"):
            verify_replay_source(self.provenance(),self.root / "absent",host_root=ROOT)

    def test_dirty_host_harness_is_recorded_without_relaxing_source(self):
        host_changes = [" M scripts/smoke_native_room.py"]
        with patch("native_room_replay.source_state",side_effect=[(self.revision,[]),("host-revision",host_changes)]):
            selected = verify_replay_source(self.provenance(),self.repo,host_root=ROOT)
        self.assertEqual(selected["source_revision"],self.revision)
        self.assertTrue(selected["source_clean"])
        self.assertEqual(selected["host_harness"]["revision"],"host-revision")
        self.assertEqual(selected["host_harness"]["changes"],host_changes)

    def test_dirty_source_checkout_is_rejected(self):
        (self.repo / "untracked.txt").write_text("dirty\n")
        with self.assertRaisesRegex(ValueError,"not clean"):
            verify_replay_source(self.provenance(),self.repo,host_root=ROOT)

    def test_source_fixture_mismatch_is_rejected(self):
        original = replay_intent(self.repo)
        fixture = self.repo / "src/vita/guest_replay.hpp"
        fixture.write_text(fixture.read_text()+"// synthetic change\n")
        self.git("add",str(fixture))
        self.git("-c","user.name=Synthetic","-c","user.email=synthetic@example.invalid","commit","-qm","Change fixture")
        revision = self.git("rev-parse","HEAD").strip()
        with self.assertRaisesRegex(ValueError,"fixture"):
            verify_replay_source({"revision":revision,"tracked_changes":False,"guest_replay":original},
                                 self.repo,host_root=ROOT)


class ReplaySourceGateTests(unittest.TestCase):
    def setUp(self):
        directory = ROOT / ".audit/native-room-vita/replay-gate-tests"
        directory.mkdir(parents=True,exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=directory)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "guest-source"
        (self.source / "src/vita").mkdir(parents=True)
        shutil.copyfile(ROOT / "src/vita/guest_replay.hpp",self.source / "src/vita/guest_replay.hpp")
        self.git("init","-q")
        self.git("add",".")
        self.git("-c","user.name=Synthetic","-c","user.email=synthetic@example.invalid","commit","-qm","Synthetic guest source")
        self.revision = self.git("rev-parse","HEAD").strip()
        self.state = self.root / "state"
        self.output = self.root / "output"
        self.vpk = self.root / "replay.vpk"

    def git(self,*arguments):
        return subprocess.check_output(["git","-C",str(self.source),*arguments],text=True,stderr=subprocess.STDOUT)

    def provenance(self,**overrides):
        return {"revision":self.revision,"tracked_changes":False,"guest_replay":replay_intent(self.source)} | overrides

    def assert_blocked(self,provenance,message):
        with zipfile.ZipFile(self.vpk,"w") as package:
            package.writestr("assets/native-room/provenance.json",json.dumps(provenance))
        arguments = ["smoke_native_room.py","--guest-replay","--after-climb","--state",str(self.state),
                     "--output",str(self.output),"--vpk",str(self.vpk),"--source-checkout",str(self.source)]
        with patch("sys.argv",arguments), patch("smoke_native_room.prepare") as prepare, \
             patch("smoke_native_room.launch_command") as launch, \
             patch("smoke_native_room.X11",side_effect=AssertionError("No X11 in replay")), \
             patch("smoke_native_room.C.CDLL",side_effect=AssertionError("No ctypes in replay")):
            with self.assertRaisesRegex(ValueError,message):
                smoke_main()
        prepare.assert_not_called()
        launch.assert_not_called()
        self.assertFalse(self.state.exists())

    def test_wrong_revision_is_rejected_before_state_creation_or_launch(self):
        self.assert_blocked(self.provenance(revision="0"*40),"exact VPK source revision")

    def test_dirty_source_is_rejected_before_state_creation_or_launch(self):
        (self.source / "untracked.txt").write_text("dirty\n")
        self.assert_blocked(self.provenance(),"not clean")

    def test_fixture_mismatch_is_rejected_before_state_creation_or_launch(self):
        original = replay_intent(self.source)
        fixture = self.source / "src/vita/guest_replay.hpp"
        fixture.write_text(fixture.read_text()+"// synthetic change\n")
        self.git("add",str(fixture))
        self.git("-c","user.name=Synthetic","-c","user.email=synthetic@example.invalid","commit","-qm","Change fixture")
        revision = self.git("rev-parse","HEAD").strip()
        self.assert_blocked({"revision":revision,"tracked_changes":False,"guest_replay":original},"fixture")


if __name__ == "__main__":
    unittest.main()
