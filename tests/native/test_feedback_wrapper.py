import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / "scripts"))
from feedback_native_room import main


class FeedbackWrapperTests(unittest.TestCase):
    def run_completed_pipeline(self, final_state, runtime_exit=0):
        directory = ROOT / ".audit/native-room-vita/wrapper-correction-tests"
        directory.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory) as temporary:
            output = Path(temporary) / "synthetic-feedback"
            calls = {}
            def execute(arguments, **options):
                label = Path(options["stdout"].name).stem
                calls[label] = options.get("timeout")
                if label == "package":
                    options["stdout"].write(b'{"vpk_sha256":"synthetic-vpk"}')
                if label == "runtime":
                    path = output / "feedback.json"
                    feedback = json.loads(path.read_text())
                    feedback["stages"] = {key:True for key in feedback["stages"]}
                    feedback["artifacts"] = {"native-frame.png":{"path":"synthetic-closed-guest-frame.png","sha256":"synthetic-frame"}}
                    path.write_text(json.dumps(feedback))
                return SimpleNamespace(returncode=runtime_exit if label == "runtime" else 0)
            failure = None
            with patch("sys.argv",["feedback_native_room.py","--output",str(output)]), \
                 patch("feedback_native_room.source_state",side_effect=[("synthetic",[]),final_state]), \
                 patch("feedback_native_room.subprocess.run",side_effect=execute):
                try:
                    main()
                except Exception as error:
                    failure = error
            return json.loads((output / "feedback.json").read_text()), failure, calls

    def assert_source_failure_preserves_completed_stages(self, final_state):
        feedback, failure, calls = self.run_completed_pipeline(final_state)
        self.assertIsInstance(failure,RuntimeError)
        self.assertTrue(feedback["errors"])
        self.assertFalse(feedback["stages"]["full_completion"])
        self.assertTrue(all(value for key,value in feedback["stages"].items() if key != "full_completion"))
        self.assertEqual(feedback["artifacts"]["native-frame.png"]["sha256"],"synthetic-frame")
        self.assertIn("source_after",feedback)
        return feedback

    def test_runtime_has_no_outer_force_kill_timeout(self):
        feedback, failure, calls = self.run_completed_pipeline(("synthetic",[]))
        self.assertIsNone(failure)
        self.assertIsNone(calls["runtime"])
        self.assertEqual({label:value for label,value in calls.items() if label != "runtime"},
                         {"stage":600,"configure":600,"build":600,"package":600})

    def test_same_head_with_dirty_final_source_records_failure(self):
        feedback = self.assert_source_failure_preserves_completed_stages(("synthetic",[" M src/input.cpp"]))
        self.assertEqual(feedback["source_after"]["changes"],[" M src/input.cpp"])

    def test_changed_final_head_records_failure(self):
        feedback = self.assert_source_failure_preserves_completed_stages(("changed",[]))
        self.assertEqual(feedback["source_after"]["revision"],"changed")

    def test_final_git_query_failure_cannot_leave_all_pass_feedback(self):
        feedback = self.assert_source_failure_preserves_completed_stages(subprocess.CalledProcessError(128,["git","status"]))
        self.assertIn("error",feedback["source_after"])

    def test_nonzero_runtime_preserves_guest_proof_but_clears_overall_completion(self):
        feedback, failure, calls = self.run_completed_pipeline(("synthetic",[]),runtime_exit=1)
        self.assertIsInstance(failure,RuntimeError)
        self.assertTrue(feedback["errors"])
        self.assertTrue(feedback["stages"]["input"])
        self.assertTrue(feedback["stages"]["clean_exit"])
        self.assertFalse(feedback["stages"]["full_completion"])
