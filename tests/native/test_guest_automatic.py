from pathlib import Path
import sys
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


if __name__ == "__main__":
    unittest.main()
