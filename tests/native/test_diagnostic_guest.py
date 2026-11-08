from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0,str(Path(__file__).resolve().parents[2] / "scripts"))
from smoke_native_room import verify_guest, verify_wall_jump_guest, verify_keyboard_mapping, KEYBOARD_MAPPING


def completed_log():
    return """Celeste native room DIAGNOSTIC boot revision=synthetic fixed_step=1/60 manual_reset=Triangle
assets ready
frame ready frame=0 x=19 y=144 vx=0.000 vy=0.000 ground=0 dead=0 resets=0
input frame=3 buttons=00004000 x=0 y=0 cross_held=1 cross_pressed=1 reset=0 exit=0
frame frame=4 x=19 y=142 vx=0.000 vy=-105.000 ground=1 dead=0 resets=0
input frame=12 buttons=00000000 x=0 y=0 cross_held=0 cross_pressed=0 reset=0 exit=0
input frame=60 buttons=00008010 x=0 y=-1 cross_held=0 cross_pressed=0 reset=0 exit=0 square_held=1 square_pressed=1
dash transition frame=61 from=0 to=2 freeze=0.050000001 dashes=0
freeze transition frame=65 from=1 to=0 state=2
dash launch frame=66 state=2 dir_x=0.000000 dir_y=-1.000000 vx=0.000 vy=-240.000
dash transition frame=78 from=2 to=0 freeze=0.000000000 dashes=0
input frame=80 buttons=00000020 x=1 y=0 cross_held=0 cross_pressed=0 reset=0 exit=0
death frame=110 x=50 y=160 vx=0.000 vy=0.000 ground=0 dead=1 resets=0
manual reset frame=120 x=19 y=144 vx=0.000 vy=0.000 ground=0 dead=0 resets=1
clean exit frame=130 x=19 y=144 vx=0.000 vy=0.000 ground=1 dead=0 resets=1
"""


def wall_jump_log():
    return ("jump frame=6 x=15 y=134 vx=130.000 vy=-105.000 ground=0 dead=0 resets=0 state=0 "
            "move_x=-1 force_x=1 force_timer=0.159999996 var_timer=0.200000003 jump_buffer=0.000000000 jump_kind=WallJump\n"
            "wall forced frame=7 x=17 y=132 move_x=1 force_x=1 force_timer=0.143333331 jump_kind=WallJump\n")


class CompletedGuestTests(unittest.TestCase):
    def test_actual_wall_jump_and_subsequent_forced_motion_are_required(self):
        self.assertEqual(verify_wall_jump_guest(wall_jump_log())["jump_frame"],6)

    def test_false_wall_jump_proof_is_rejected_parameterized(self):
        for old,new in (("vx=130.000","vx=90.000"),("var_timer=0.200000003","var_timer=0.000000000"),
                        ("jump_buffer=0.000000000","jump_buffer=0.080000000"),("move_x=1","move_x=-1"),
                        ("wall forced frame=7 x=17","wall forced frame=7 x=15"),("jump_kind=WallJump","jump_kind=Jump")):
            with self.subTest(old=old):
                with self.assertRaises(ValueError):
                    verify_wall_jump_guest(wall_jump_log().replace(old,new))

    def test_changed_square_mapping_is_rejected(self):
        text = "".join(f"keyboard-button-{button}: {key}\n" for button, key in KEYBOARD_MAPPING.items())
        with self.assertRaisesRegex(ValueError, "square"):
            verify_keyboard_mapping(text.replace("square: KeyZ", "square: KeyX"))

    def test_completed_diagnostic_proof_is_accepted(self):
        self.assertEqual(len(verify_guest(completed_log(),"synthetic")),13)

    def test_missing_or_false_proof_parameterized(self):
        for old,new in (("revision=synthetic","revision=stale"),("death frame=110","frame frame=110"),
                        ("vy=-105.000","vy=0.000"),("manual reset frame=120 x=19","manual reset frame=120 x=20"),
                         ("clean exit frame=130 x=19","clean exit frame=130 x=20"),
                         (" x=1 y=0 "," x=0 y=0 "), ("from=0 to=2", "from=0 to=0"),
                         ("vy=-240.000", "vy=0.000"), ("from=2 to=0", "from=2 to=2"),
                         ("square_held=1 square_pressed=1", "square_held=1 square_pressed=0")):
            with self.subTest(old=old):
                with self.assertRaises(ValueError):
                    verify_guest(completed_log().replace(old,new),"synthetic")
