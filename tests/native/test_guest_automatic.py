import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))


class AutomaticIntentTests(unittest.TestCase):
    def test_intent_pins_the_separate_input_header(self):
        from native_room_automatic import automatic_intent
        intent = automatic_intent()
        self.assertEqual(intent["id"], "first_room_auto_death_v2")
        self.assertEqual(intent["samples"], 365)
        self.assertEqual(intent["exit_frame"], 364)
        self.assertEqual(intent["sha256"], hashlib.sha256((ROOT / intent["source"]).read_bytes()).hexdigest())

    def test_legacy_and_automatic_modes_are_exclusive(self):
        from native_room_automatic import automatic_intent, verify_automatic_intent
        intent = automatic_intent()
        with self.assertRaisesRegex(ValueError, "exclusive"):
            verify_automatic_intent({"guest_automatic": intent["id"], "guest_automatic_fixture": intent,
                                     "guest_replay": {"id": "first_room_climb_dash_v1"}}, True)

    def test_automatic_header_hash_cannot_be_edited(self):
        from native_room_automatic import automatic_intent, verify_automatic_intent
        intent = automatic_intent() | {"sha256": "0"*64}
        with self.assertRaisesRegex(ValueError, "fixture"):
            verify_automatic_intent({"guest_automatic": intent["id"], "guest_automatic_fixture": intent}, True)

    def test_old_manual_provenance_remains_compatible(self):
        from native_room_automatic import verify_automatic_intent
        verify_automatic_intent({}, False)

    def test_missing_fixture_pin_is_rejected(self):
        from native_room_automatic import verify_automatic_intent
        with self.assertRaisesRegex(ValueError, "fixture"):
            verify_automatic_intent({"guest_automatic": "first_room_auto_death_v2"}, True)

    def test_automatic_id_is_not_a_boolean_or_arbitrary_label_parameterized(self):
        from native_room_automatic import verify_automatic_intent
        for value in (False, True, "", "legacy"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "fixture ID"):
                verify_automatic_intent({"guest_automatic": value}, bool(value))

    def test_staging_rejects_dual_guest_modes_before_reading_inputs(self):
        from stage_native_room import stage
        with self.assertRaisesRegex(ValueError, "exclusive"):
            stage(Path("unused"), None, None, None, guest_replay=True, guest_automatic=True)

    def test_automatic_staging_requires_player_assets(self):
        from stage_native_room import stage
        with self.assertRaisesRegex(ValueError, "animated"):
            stage(Path("unused"), None, None, None, guest_automatic=True)

    def test_stager_uses_the_agreed_long_flag_not_guest_auto(self):
        result = subprocess.run([sys.executable, "-B", "scripts/stage_native_room.py", "--guest-auto"],
                                cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("unrecognized arguments: --guest-auto", result.stderr)


class SessionProfileTests(unittest.TestCase):
    def compile_profile(self, flags, automatic):
        source = '#include "session_profile.hpp"\nstatic_assert(celeste::diagnostic::automatic_session_profile == ' + str(automatic).lower() + ');\n'
        return subprocess.run(["c++", "-std=c++17", "-fsyntax-only", "-x", "c++", "-Isrc/native", "-Isrc/vita", *flags, "-"],
                              input=source, text=True, capture_output=True, cwd=ROOT)

    def test_production_and_automatic_select_the_same_constructor_parameterized(self):
        for flags in (["-DCELESTE_ROOM_ANIMATED_PLAYER"], ["-DCELESTE_ROOM_ANIMATED_PLAYER", "-DCELESTE_ROOM_GUEST_AUTOMATIC"]):
            with self.subTest(flags=flags):
                result = self.compile_profile(flags, True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_legacy_mode_retains_manual_constructor(self):
        result = self.compile_profile(["-DCELESTE_ROOM_ANIMATED_PLAYER", "-DCELESTE_ROOM_GUEST_REPLAY"], False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_automatic_requires_animated_player(self):
        result = self.compile_profile(["-DCELESTE_ROOM_GUEST_AUTOMATIC"], False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("animated", result.stderr)

    def test_dual_fixture_modes_are_rejected(self):
        result = self.compile_profile(["-DCELESTE_ROOM_ANIMATED_PLAYER", "-DCELESTE_ROOM_GUEST_AUTOMATIC", "-DCELESTE_ROOM_GUEST_REPLAY"], False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exclusive", result.stderr)


class ApplicationModeTests(unittest.TestCase):
    def compile_app(self, automatic, flags, source="src/vita/app.cpp"):
        from native_room_automatic import automatic_intent
        from stage_native_room import asset_pins_text
        parent = ROOT / ".audit/native-player-death-respawn/automatic-followup"
        parent.mkdir(parents=True, exist_ok=True)
        intent = automatic_intent() if automatic else None
        manifest = {"revision": "synthetic", "tracked_changes": False, "guest_replay": None,
                    "guest_automatic": intent["id"] if intent else None, "guest_automatic_fixture": intent,
                    "player": {"bank_sha256": "0"*64},
                    "files": {name: {"fnv1a32": 0} for name in ["global.mask", "hazards.txt", "player.txt", "visuals.txt", "decals.txt"]}}
        if "-DCELESTE_ROOM_GUEST_REPLAY" in flags:
            from native_room_replay import replay_intent
            manifest["guest_replay"] = replay_intent()
        with tempfile.TemporaryDirectory(dir=parent) as directory:
            (Path(directory) / "asset_pins.hpp").write_text(asset_pins_text(manifest))
            return subprocess.run(["c++", "-std=c++17", "-fsyntax-only", "-Wall", "-Wextra", "-Wpedantic", "-Werror",
                                   "-I" + directory, "-Isrc/native", "-Isrc/vita", "-Itests/native/vita_stub", *flags, source],
                                  text=True, capture_output=True, cwd=ROOT)

    def test_application_compiles_in_separate_modes_parameterized(self):
        for automatic, flags in [(False, []), (False, ["-DCELESTE_ROOM_ANIMATED_PLAYER"]),
                                 (False, ["-DCELESTE_ROOM_ANIMATED_PLAYER", "-DCELESTE_ROOM_GUEST_REPLAY"]),
                                 (True, ["-DCELESTE_ROOM_ANIMATED_PLAYER", "-DCELESTE_ROOM_GUEST_AUTOMATIC"])]:
            with self.subTest(flags=flags):
                result = self.compile_app(automatic, flags)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_production_cannot_compile_with_automatic_staging(self):
        result = self.compile_app(True, ["-DCELESTE_ROOM_ANIMATED_PLAYER"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot use automatic guest staging", result.stderr)

    def test_receipt_glue_compiles_with_explicit_and_default_policies_parameterized(self):
        for automatic, flags in [(False, []), (False, ["-DCELESTE_ROOM_ANIMATED_PLAYER"]),
                                 (False, ["-DCELESTE_ROOM_ANIMATED_PLAYER", "-DCELESTE_ROOM_GUEST_REPLAY", "-DCELESTE_ROOM_CAPTURE_AFTER_CLIMB"]),
                                 (False, ["-DCELESTE_ROOM_CAPTURE_AFTER_WALL_JUMP"]),
                                 (True, ["-DCELESTE_ROOM_ANIMATED_PLAYER", "-DCELESTE_ROOM_GUEST_AUTOMATIC", "-DCELESTE_ROOM_SPIKE_ART", "-DCELESTE_ROOM_DECALS"])]:
            with self.subTest(flags=flags):
                result = self.compile_app(automatic, flags, source="src/vita/draw.cpp")
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_automatic_cannot_compile_with_production_staging(self):
        result = self.compile_app(False, ["-DCELESTE_ROOM_ANIMATED_PLAYER", "-DCELESTE_ROOM_GUEST_AUTOMATIC"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires matching staging", result.stderr)
