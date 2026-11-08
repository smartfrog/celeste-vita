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


class NativeFeedbackTests(unittest.TestCase):
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
