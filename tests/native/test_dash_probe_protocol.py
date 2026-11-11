import contextlib
import hashlib
import io
import tempfile
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import native_room_replay as replay
from smoke_native_room import main as smoke_main
from native_room_dash_runtime import dash_probe_completion_receipt
import test_dash_probe_runtime as dash_runtime


class DashProbeProtocolTests(unittest.TestCase):
    def test_intent_hash_pins_header_bytes_without_claiming_a_guest_receipt(self):
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as temporary:
            root = Path(temporary)
            header = root / "src/vita/guest_dash_probe.hpp"
            header.parent.mkdir(parents=True)
            header.write_bytes(b"synthetic input-only fixture header\n")
            intent = replay.dash_probe_intent(root)
            self.assertEqual(intent, dict(id="first_room_dash_trails_v1", samples=360, exit_frame=359,
                                         source="src/vita/guest_dash_probe.hpp",
                                         sha256=hashlib.sha256(header.read_bytes()).hexdigest()))

    def test_input_only_contract_keeps_all_360_samples_and_up_dash_at_40(self):
        samples = replay.dash_probe_inputs()
        self.assertEqual(len(samples), 360)
        for frame, sample in enumerate(samples):
            with self.subTest(frame=frame):
                self.assertEqual(sample, dict(x=0, y=-int(40 <= frame < 60), jump=0,
                                             dash=int(frame == 40), reset=0, exit=int(frame == 359)))

    def test_invalid_dash_mode_stops_before_package_state_config_or_launch(self):
        arguments = ["smoke", "--guest-dash-probe", "--after-climb", "--state", "not-created", "--output", "not-created",
                     "--vpk", "not-read.vpk", "--source-root", "not-read", "--build", "not-read", "--staging", "not-read"]
        with patch("sys.argv", arguments), patch("smoke_native_room.prepare") as prepare, \
             patch("smoke_native_room.launch_command") as launch, patch("smoke_native_room.zipfile.ZipFile") as package, \
             contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            smoke_main()
        prepare.assert_not_called()
        launch.assert_not_called()
        package.assert_not_called()

    def test_cli_rejects_other_modes_or_missing_binding_parameterized(self):
        required = ["--source-root", "source", "--build", "build", "--staging", "staging"]
        base = ["smoke", "--guest-dash-probe", "--state", "state", "--output", "output", "--vpk", "package"]
        for extra in (["--guest-automatic"], ["--guest-replay"], ["--frame-only"], ["--after-climb"], ["--after-wall-jump"], []):
            with self.subTest(extra=extra), patch("sys.argv", base + (required + extra if extra else [])), \
                 contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                smoke_main()

    def test_dash_completion_cannot_be_mislabeled_as_old_365_or_250(self):
        self.assertNotIn("dash_trails", replay.completion_receipt("synthetic", automatic=True))
        self.assertNotIn("dash_trails", replay.completion_receipt("synthetic"))
        receipt = dash_probe_completion_receipt('synthetic',dash_runtime.probe_fixture())
        self.assertIn('capture=dash_trails',receipt)
        self.assertNotEqual(receipt,replay.completion_receipt('synthetic',automatic=True))


if __name__ == "__main__":
    unittest.main()
