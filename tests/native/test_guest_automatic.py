import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from native_room_replay import automatic_inputs, verify_automatic_guest, completion_receipt
import test_guest_replay
from smoke_native_room import main as smoke_main
from feedback_native_room import main as feedback_main


def automatic_fixture():
    return dict(id="first_room_auto_death_v2", samples=365, exit_frame=364,
                source="src/vita/guest_automatic_replay.hpp", sha256="e"*64)


def completed_automatic_log():
    rows = ["Celeste native room DIAGNOSTIC boot revision=synthetic fixed_step=1/60",
            f"guest automatic fixture=first_room_auto_death_v2 fixture_sha256={automatic_fixture()['sha256']} input_source=scripted_guest_controls samples=365 exit_frame=364 physical_controller_verified=false host_input_injected=false",
            "capture policy=initial_respawn",
            "assets ready", "frame ready",
            "frame_saved path=ux0:data/celeste_native_room-synthetic.ppm width=960 height=544 frame=36 capture=initial_respawn"]
    for frame, controls in enumerate(automatic_inputs()):
        reloads = int(frame >= 164) + int(frame >= 326)
        deaths = int(frame >= 63) + int(frame >= 227)
        dead = int(63 <= frame < 164 or 227 <= frame < 326)
        state = 14 if frame < 35 or 164 <= frame < 199 or 326 <= frame < 361 else 0
        jumps = int(frame >= 36) + int(frame >= 200) + int(frame >= 362)
        values = dict(fixture="first_room_auto_death_v2", frame=frame, **controls,
                      state=state, dead=dead, reloads=reloads, room_deaths=deaths, save_deaths=deaths, jumps=jumps)
        rows.append("guest_automatic " + " ".join(f"{key}={value}" for key, value in values.items()))
    rows += ["clean exit frame=364 x=19 y=144 dead=0 resets=0 state=0",
             "guest_automatic_complete fixture=first_room_auto_death_v2 samples=365 exit_frame=364 reloads=2 room_deaths=2 save_deaths=2 jumps=3 full_completion=1"]
    return "\n".join(rows) + "\n"


class AutomaticGuestTests(unittest.TestCase):
    def test_source_derived_input_only_sequence_includes_nonstepping_exit(self):
        inputs = automatic_inputs()
        self.assertEqual(len(inputs), 365)
        self.assertEqual(inputs[36], dict(x=1, y=0, jump=1, reset=0, exit=0))
        self.assertEqual(inputs[363], dict(x=1, y=0, jump=1, reset=0, exit=0))
        self.assertEqual(inputs[364], dict(x=0, y=0, jump=0, reset=0, exit=1))

    def test_two_automatic_cycles_are_recomputed_from_samples(self):
        proof = verify_automatic_guest(completed_automatic_log(), "synthetic", "first_room_auto_death_v2", automatic_fixture())
        self.assertEqual((proof["samples"], proof["reloads"], proof["deaths"], proof["jumps"]), (365, 2, 2, 3))
        self.assertEqual(len(proof["respawn_normal_frames"]), 3)

    def test_closed_receipt_has_distinct_automatic_fixture(self):
        self.assertIn("fixture=first_room_auto_death_v2 status=0\n", completion_receipt("synthetic", automatic=True))

    def test_suspicious_or_incomplete_samples_fail_parameterized(self):
        text = completed_automatic_log()
        sample = next(line for line in text.splitlines() if line.startswith("guest_automatic fixture=") and " frame=36 " in line)
        mutations = {
            "missing": text.replace(sample + "\n", ""),
            "duplicate": text.replace(sample, sample + "\n" + sample),
            "out_of_order": text.replace(" frame=36 ", " frame=37 "),
            "wrong_input": text.replace("frame=36 x=1", "frame=36 x=0"),
            "manual": text.replace("frame=36 x=1 y=0 jump=1 reset=0", "frame=36 x=1 y=0 jump=1 reset=1"),
            "wrong_fixture": text.replace("first_room_auto_death_v2", "first_room_climb_dash_v1"),
            "truncated": text.rstrip("\n"),
            "missing_end": text[:text.index("guest_automatic_complete")],
            "false_end": text.replace("full_completion=1", "full_completion=0"),
            "counter_lie": text.replace("reloads=2 room_deaths=2 save_deaths=2 jumps=3 full_completion", "reloads=3 room_deaths=2 save_deaths=2 jumps=3 full_completion"),
            "no_intro": text.replace("state=14", "state=0"),
            "no_deaths": text.replace("dead=1", "dead=0"),
            "no_jumps": text.replace("jumps=3", "jumps=2"),
            "exit_step": text.replace("frame=364 x=0 y=0 jump=0 reset=0 exit=1 state=0 dead=0 reloads=2 room_deaths=2 save_deaths=2 jumps=3", "frame=364 x=0 y=0 jump=0 reset=0 exit=1 state=0 dead=1 reloads=2 room_deaths=3 save_deaths=3 jumps=3"),
            "manual_event": text + "manual reset frame=364\n",
            "fatal": text + "FATAL: failed\n",
            "wrong_revision": text.replace("revision=synthetic", "revision=stale"),
            "duplicate_key": text.replace("frame=36 x=1", "frame=36 frame=36 x=1"),
            "counter_decrease": text.replace("frame=201 x=1 y=0 jump=0 reset=0 exit=0 state=0 dead=0 reloads=1", "frame=201 x=1 y=0 jump=0 reset=0 exit=0 state=0 dead=0 reloads=0"),
            "duplicate_end": text + text[text.index("guest_automatic_complete"):],
            "manual_buttons": text + "input frame=5 reset=1 exit=0\n",
            "jump_while_dead": text.replace("frame=64 x=0 y=0 jump=0 reset=0 exit=0 state=0 dead=1 reloads=0 room_deaths=1 save_deaths=1 jumps=1", "frame=64 x=0 y=0 jump=0 reset=0 exit=0 state=0 dead=1 reloads=0 room_deaths=1 save_deaths=1 jumps=2"),
            "wrong_header": text.replace("fixture_sha256="+"e"*64,"fixture_sha256="+"d"*64),
            "missing_input_source": text.replace("input_source=scripted_guest_controls","input_source=physical"),
            "negative_zero": text.replace("frame=0 x=0 y=0 jump=0", "frame=0 x=-0 y=0 jump=0"),
            "triangle_buttons": text + "input frame=1 buttons=00001000 reset=0 exit=0\n",
        }
        for label, mutated in mutations.items():
            with self.subTest(label=label), self.assertRaises(ValueError):
                verify_automatic_guest(mutated, "synthetic", "first_room_auto_death_v2", automatic_fixture())


class AutomaticBoundaryTests(unittest.TestCase):
    run_scenario = test_guest_replay.ReplayHostBoundaryTests.run_scenario

    def test_mocked_automatic_runtime_reuses_guest_only_isolation_and_receipts(self):
        feedback, _ = self.run_scenario("complete", automatic=True)
        self.assertTrue(feedback["stages"]["full_completion"])
        self.assertEqual(feedback["guest_automatic_observed"]["samples"], 365)
        self.assertEqual(feedback["requested_scope"], "guest_automatic_smoke")

    def test_mocked_automatic_failures_remain_partial_parameterized(self):
        for mode in ("timeout", "no_frame", "skip_existing", "unclosed_frame", "bad_receipt", "missing_events", "guest_failure", "source_drift", "source_verify_failure", "config_mutation"):
            with self.subTest(mode=mode):
                feedback, _ = self.run_scenario(mode, automatic=True)
                self.assertFalse(feedback["stages"]["full_completion"])

    def test_mocked_automatic_host_exit_is_binding_parameterized(self):
        for mode, status in (("host_failure", 133), ("host_timeout", None)):
            with self.subTest(mode=mode):
                feedback, _ = self.run_scenario(mode, host_exit_code=status, automatic=True)
                self.assertTrue(feedback["stages"]["clean_exit"])
                self.assertFalse(feedback["stages"]["full_completion"])

    def test_invalid_modes_fail_before_side_effects_parameterized(self):
        for main, required in ((smoke_main, ["--state", "unused", "--vpk", "unused"]), (feedback_main, [])):
            for invalid in (("--guest-automatic", "--guest-replay"), ("--guest-automatic", "--after-climb"),
                            ("--guest-automatic", "--frame-only"), ("--expected-source-state", "unused")):
                with self.subTest(main=main.__module__, invalid=invalid), patch("sys.argv", ["test", "--output", "unused", *required, *invalid]), \
                     patch("pathlib.Path.mkdir", side_effect=AssertionError("No state/output for invalid modes")), \
                     self.assertRaises(SystemExit):
                    main()


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


if __name__ == "__main__":
    unittest.main()
