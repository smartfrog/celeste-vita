import re
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]


class DirectionalInputSourceContractTests(unittest.TestCase):
    def test_manual_app_uses_standard_analog_and_raw_stick_bytes(self):
        text = (ROOT / "src/vita/app.cpp").read_text()
        self.assertIn("sceCtrlSetSamplingMode(SCE_CTRL_MODE_ANALOG)", text)
        self.assertNotIn("SCE_CTRL_MODE_DIGITAL", text)
        self.assertNotIn("SCE_CTRL_MODE_ANALOG_WIDE", text)
        self.assertIn("sceCtrlPeekBufferPositive(0,&pad,1)", text)
        self.assertIn('"Controller sample failed: "', text)
        self.assertIn("lx = pad.lx;", text)
        self.assertIn("ly = pad.ly;", text)
        self.assertIn("controller.sample_analog({held_buttons, {lx, ly, true}})", text)
        self.assertIn('"input analog frame=%u buttons=%08x valid=1 lx=%u ly=%u move_x=%d move_y=%d aim_x=%d aim_y=%d"', text)

    def test_guest_replay_keeps_the_legacy_controls_path(self):
        text = (ROOT / "src/vita/app.cpp").read_text()
        match = re.search(
            r"#if defined\(CELESTE_ROOM_GUEST_REPLAY\) \|\| defined\(CELESTE_ROOM_GUEST_AUTOMATIC\) \|\| defined\(CELESTE_ROOM_DASH_PROBE\)(.*?)#else\s+unsigned lx = 0(.*?)#endif",
            text, re.S)
        self.assertIsNotNone(match)
        self.assertIn("const auto controls = replay.next(frame);", match.group(1))
        self.assertIn("controller.sample(controls)", match.group(1))
        self.assertNotIn("sample_analog", match.group(1))
        self.assertIn("controller.sample_analog", match.group(2))

    def test_normalization_assumption_and_invalid_contract_are_explicit(self):
        header = (ROOT / "src/core/directional_input.hpp").read_text()
        source = (ROOT / "src/core/directional_input.cpp").read_text()
        self.assertIn("NATIVE VITA FIXTURE ASSUMPTION", header)
        self.assertIn("bool valid = false;", header)
        self.assertIn("/ 128.0f", source)
        self.assertIn("/ 127.0f", source)
        self.assertIn("if (!reading.valid) return {};", source)
        self.assertIn("Nonfinite directional stick", source)


if __name__ == "__main__":
    unittest.main()
