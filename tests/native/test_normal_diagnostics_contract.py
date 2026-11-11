from pathlib import Path
import subprocess
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]


class NormalDiagnosticsContractTests(unittest.TestCase):
    def test_only_normal_initial_respawn_enables_run_diagnostics_parameterized(self):
        cases = [([], False), (["CELESTE_ROOM_ANIMATED_PLAYER"], True)]
        for mode in ("CELESTE_ROOM_GUEST_AUTOMATIC", "CELESTE_ROOM_GUEST_REPLAY", "CELESTE_ROOM_DASH_PROBE",
                     "CELESTE_ROOM_CAPTURE_AFTER_CLIMB", "CELESTE_ROOM_CAPTURE_AFTER_WALL_JUMP"):
            cases.append((["CELESTE_ROOM_ANIMATED_PLAYER", mode], False))
        for flags, enabled in cases:
            with self.subTest(flags=flags):
                source = '#include "capture_policy.hpp"\nstatic_assert(celeste::diagnostic::normal_initial_respawn_profile == ' + str(enabled).lower() + ');\n'
                result = subprocess.run(["c++", "-std=c++17", "-fsyntax-only", "-x", "c++", "-Isrc/native", "-Isrc/vita",
                                         *["-D" + flag for flag in flags], "-"], input=source, text=True, capture_output=True, cwd=ROOT)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_calibration_precedes_room_graphics_session_and_controls(self):
        source = (ROOT / "src/vita/app.cpp").read_text().split("void run() {", 1)[1]
        calibration = source.index("calibrate_platform_clock()")
        for construction in ("Room room(", "initialize_graphics()", "make_session(", "Controller controller;"):
            self.assertLess(calibration, source.index(construction))

    def test_runtime_uses_no_sleep_and_metrics_core_has_no_io_dependencies(self):
        app = (ROOT / "src/vita/app.cpp").read_text()
        loop = app.split("while (!session.exiting()) {", 1)[1]
        self.assertNotIn("DelayThread", loop)
        self.assertNotIn("sleep", loop)
        core = (ROOT / "src/vita/frame_metrics.hpp").read_text()
        for forbidden in ("fopen", "fflush", "sceIo", "std::vector", "std::string ", "new ", "processmgr.h"):
            self.assertNotIn(forbidden, core)

    def test_interception_flag_precedes_interval_and_never_changes_controller_input(self):
        source = (ROOT / "src/vita/app.cpp").read_text()
        self.assertIn("frame_metrics.begin_frame(process_now_us(),{},(buttons&SCE_CTRL_INTERCEPTED)!=0)", source)
        self.assertLess(source.index("controller.sample_analog({held_buttons, {lx, ly, true}})"), source.index("frame_metrics.begin_frame("))
        self.assertNotIn("sceCtrlSetButtonIntercept", source)
        self.assertNotIn("_sceAppMgrGetAppState", source)


if __name__ == "__main__":
    unittest.main()
