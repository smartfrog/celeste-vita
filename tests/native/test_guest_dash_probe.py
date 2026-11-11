import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from stage_native_room import asset_pins_text
from native_room_dash_probe import dash_probe_intent, verify_dash_probe_intent


def probe_manifest(enabled):
    manifest = {"revision": "synthetic", "tracked_changes": False, "guest_replay": None,
                "guest_automatic": None, "guest_automatic_fixture": None, "render_style": "animated_player_partial",
                "player": {"bank_sha256": "0"*64},
                "files": {name: {"fnv1a32": 0} for name in ("global.mask", "hazards.txt", "player.txt", "visuals.txt", "decals.txt")}}
    if enabled:
        source = "src/vita/guest_dash_probe.hpp"
        manifest.update(guest_dash_probe="first_room_dash_trails_v1", guest_dash_probe_fixture={
            "id": "first_room_dash_trails_v1", "samples": 360, "exit_frame": 359, "source": source,
            "sha256": hashlib.sha256((ROOT / source).read_bytes()).hexdigest()})
    return manifest


class DashProbeStagingTests(unittest.TestCase):
    def compile_app(self, staged_probe, probe_mode, extra_flags=(), source="src/vita/app.cpp", preprocess=False):
        parent = ROOT / ".audit/native-dash-visual-feedback/matrix-guard-correction-05/tmp"
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as directory:
            (Path(directory) / "asset_pins.hpp").write_text(asset_pins_text(probe_manifest(staged_probe)))
            flags = ["-DCELESTE_ROOM_ANIMATED_PLAYER"] + (["-DCELESTE_ROOM_DASH_PROBE"] if probe_mode else []) + list(extra_flags)
            phase = ["-E", "-P"] if preprocess else ["-fsyntax-only"]
            return subprocess.run(["c++", "-std=c++17", *phase, "-Wall", "-Wextra", "-Wpedantic", "-Werror",
                                   "-I" + directory, "-Isrc/native", "-Isrc/vita", "-Itests/native/vita_stub", *flags, source],
                                  cwd=ROOT, text=True, capture_output=True)

    def test_probe_asset_pins_carry_the_input_header_hash(self):
        manifest = probe_manifest(True)
        self.assertIn(manifest["guest_dash_probe_fixture"]["sha256"], asset_pins_text(manifest))

    def test_probe_cannot_use_production_staging(self):
        result = self.compile_app(False, True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("staging", result.stderr)

    def test_production_cannot_use_probe_staging(self):
        result = self.compile_app(True, False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("staging", result.stderr)

    def test_probe_boot_carries_fixture_hash(self):
        self.assertIn("guest dash probe fixture=%s fixture_sha256=%s", (ROOT / "src/vita/app.cpp").read_text())

    def test_matching_probe_mode_and_staging_compile(self):
        result = self.compile_app(True, True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_probe_native_export_path_compiles_with_full_render_options(self):
        result = self.compile_app(True, True, ["-DCELESTE_ROOM_TEXTURED", "-DCELESTE_ROOM_SPIKE_ART", "-DCELESTE_ROOM_DECALS"],
                                  source="src/vita/draw.cpp")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_probe_requires_animated_player_at_compile_time(self):
        result = self.compile_app(True, True, ["-UCELESTE_ROOM_ANIMATED_PLAYER"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Dash probe requires the animated Player", result.stderr)

    def test_probe_cannot_compile_with_other_guest_modes_parameterized(self):
        for mode in ("CELESTE_ROOM_GUEST_AUTOMATIC", "CELESTE_ROOM_GUEST_REPLAY"):
            with self.subTest(mode=mode):
                result = self.compile_app(True, True, ["-D" + mode])
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("exclusive", result.stderr)

    def test_input_header_identity_and_sequence_are_unchanged(self):
        intent = dash_probe_intent()
        self.assertEqual(intent, {"id": "first_room_dash_trails_v1", "samples": 360, "exit_frame": 359,
                                 "source": "src/vita/guest_dash_probe.hpp",
                                 "sha256": "3d34e2a2335db02f8ee6493eb44068a7bcd4ad7bbf33f414a8ecdc85df50c324"})

    def test_old_asset_pin_outputs_are_byte_identical_parameterized(self):
        from native_room_automatic import automatic_intent
        from native_room_replay import replay_intent
        expected = {"production": "022cc31aceae654a392c7ceff09b15a2d8648f655dda31eebc77741ea8f7d14b",
                    "automatic": "91dbe0da9d8ad899c712c856377fac27113fa4b4f06f04ff28526e47aff461e5",
                    "replay": "55ea1fb9d959014e0d4abd658ac357e479a1c8873e1738da9e1efca7008392e4"}
        for mode, digest in expected.items():
            with self.subTest(mode=mode):
                manifest = probe_manifest(False)
                if mode == "automatic":
                    intent = automatic_intent()
                    manifest.update(guest_automatic=intent["id"], guest_automatic_fixture=intent)
                if mode == "replay":
                    manifest["guest_replay"] = replay_intent()
                self.assertEqual(hashlib.sha256(asset_pins_text(manifest).encode()).hexdigest(), digest)

    def test_probe_intent_and_build_mode_must_agree_parameterized(self):
        for staged, enabled in ((False, True), (True, False)):
            with self.subTest(staged=staged, enabled=enabled), self.assertRaisesRegex(ValueError, "intent"):
                verify_dash_probe_intent(probe_manifest(staged), enabled)

    def test_probe_fixture_fields_are_exact_parameterized(self):
        for field, value in (("sha256", "0"*64), ("samples", 365), ("exit_frame", 364), ("source", "wrong.hpp")):
            with self.subTest(field=field):
                manifest = probe_manifest(True)
                manifest["guest_dash_probe_fixture"][field] = value
                with self.assertRaisesRegex(ValueError, "fixture identity"):
                    verify_dash_probe_intent(manifest, True)

    def test_probe_staging_requires_player_before_reading_inputs(self):
        from stage_native_room import stage
        with self.assertRaisesRegex(ValueError, "animated"):
            stage(Path("unused"), None, None, None, guest_dash_probe=True)

    def test_probe_staging_rejects_other_guest_modes_parameterized(self):
        from stage_native_room import stage
        for other in ("guest_replay", "guest_automatic"):
            with self.subTest(other=other), self.assertRaisesRegex(ValueError, "exclusive"):
                stage(Path("unused"), None, None, None, guest_dash_probe=True, **{other: True})

    def test_probe_long_flag_is_registered_without_staging(self):
        result = subprocess.run([sys.executable, "-B", "scripts/stage_native_room.py", "--guest-dash-probe", "--help"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--guest-dash-probe", result.stdout)

    def test_probe_cannot_claim_automatic_or_replay_intent_parameterized(self):
        for other in ("guest_replay", "guest_automatic"):
            with self.subTest(other=other):
                manifest = probe_manifest(True) | {other: "other-fixture"}
                with self.assertRaisesRegex(ValueError, "exclusive"):
                    verify_dash_probe_intent(manifest, True)

    def test_completion_glue_is_after_teardown_and_successful_log_close(self):
        text = (ROOT / "src/vita/app.cpp").read_text()
        self.assertLess(text.index("    finish_graphics();\n#ifdef CELESTE_ROOM_DASH_PROBE"), text.index("dash_completion.graphics_finished();"))
        self.assertLess(text.index("dash_completion.graphics_finished();"), text.index('log("%s",dash_completion.log_record().c_str());'))
        self.assertLess(text.index('log("%s",dash_completion.log_record().c_str());'), text.index("dash_completion.logged();"))
        self.assertLess(text.index("dash_completion.logged();"), text.index("if (std::fclose(stderr)) status = 2;"))
        self.assertLess(text.index("if (std::fclose(stderr)) status = 2;"), text.index("dash_completion.log_closed();"))
        self.assertLess(text.index("dash_completion.log_closed();"), text.index("dash_completion.closed_receipt()"))
        self.assertIn("if(status==0)", text)

    def test_diagnostic_export_is_probe_only_and_not_a_normal_bundle(self):
        helper = ROOT / "src/vita/guest_dash_probe_diagnostic.hpp"
        self.assertTrue(helper.is_file(), "Missing failed-probe evidence writer")
        text = helper.read_text()
        self.assertIn("-dash-probe-diagnostic.trail.rgba", text)
        self.assertIn("diagnostic_only=1 accepted_frame=0 fresh_export=0 native_probe_checks=0 full_completion=0", text)
        self.assertIn("SCE_O_EXCL", text)
        self.assertNotIn(".ppm.trail.rgba", text)
        draw = (ROOT / "src/vita/draw.cpp").read_text()
        self.assertIn('#ifdef CELESTE_ROOM_DASH_PROBE\n#include "guest_dash_probe_diagnostic.hpp"', draw)
        self.assertIn("write_dash_probe_sweep_read(phase,pixels,revision,frame,stderr)", draw)

    def test_nonprobe_render_path_has_no_diagnostic_writer(self):
        result = self.compile_app(False, False, source="src/vita/draw.cpp", preprocess=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("write_dash_probe_diagnostic", result.stdout)
        self.assertNotIn("diagnostic_sweep", result.stdout)
        self.assertNotIn("-dash-probe-diagnostic.trail.rgba", result.stdout)

    def test_dash_probe_is_instrumented_sweep_without_normal_acceptance(self):
        draw = (ROOT / "src/vita/draw.cpp").read_text()
        self.assertIn("trail_target.diagnostic_sweep(*trails", draw)
        helper = (ROOT / "src/vita/guest_dash_probe_diagnostic.hpp").read_text()
        self.assertIn("instrumented=1 uninstrumented_proof=0", helper)
        self.assertIn("-dash-probe-diagnostic-markers.trail.rgba", helper)
        self.assertIn("-dash-probe-diagnostic-markers.trail.rgb", helper)
        self.assertIn("instrumented=1 uninstrumented_proof=0 diagnostic_sweep=1 acceptance_disabled=1", (ROOT / "src/vita/app.cpp").read_text())


if __name__ == "__main__":
    unittest.main()
