import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / "scripts"))
from native_room_feedback import collect_native_frame, native_capture_policy, RENDER_STAGE
import test_guest_replay


class InitialRespawnFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir="/tmp/opencode")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "ux0/data/celeste_native_room-synthetic.ppm"
        self.source.parent.mkdir(parents=True)
        self.receipt = Path(str(self.source)+".txt")
        self.output = self.root / "output"
        self.output.mkdir()
        self.output_counter = 0
        oracle = self.root / "synthetic-source-bank"
        oracle.mkdir()
        bank = json.dumps({"animations":[{"id":"idle","frames":["characters/player/idle00"]}]}).encode()
        (oracle / "bank.json").write_bytes(bank)
        self.player = {"source_oracle":str(oracle),"bank_sha256":hashlib.sha256(bank).hexdigest(),
                       "submitted_player_rgba_bytes":32768,"death_animation_extension":True}
        self.visuals = {"draw_counts":{"B":1,"F":1},"alpha_probe":None,
                        "spawn_content_probes":[{"texture":0,"screen_pixel":[4,4],"expected_rgb":[21,30,40]}],
                        "spike_textures":["synthetic-up","synthetic-left"],
                        "spike_content_probes":[
                            {"direction":"up","kind":"visible_source_spike","screen_pixel":[8,8],"expected_rgb":[1,2,3]},
                            {"direction":"left","kind":"foreground_occludes_spike","screen_pixel":[9,8],"expected_rgb":[4,5,6]}],
                        "piece_visibility":[{"visible_opaque_texels":1,"occluded_opaque_texels":1} for _ in range(19)]}
        self.decals = {"classification":{"static":22,"banner_omitted":7},"content_probes":[
            {"kind":kind,"screen_pixel":[20+i,20],"expected_rgb":[40+i,50,60]}
            for i,kind in enumerate(("visible_static_bg_positive","visible_static_bg_flip_horizontal",
                                     "visible_static_bg_flip_vertical","visible_static_fg"))]}
        self.pixels = bytearray(960*544*3)
        for i in range(24):
            self.set_pixel(100+i,10,[i+1,i+2,i+3])
        for probe in self.visuals["spawn_content_probes"]+self.visuals["spike_content_probes"]+self.decals["content_probes"]:
            self.set_pixel(*probe["screen_pixel"],probe["expected_rgb"])
        self.set_pixel(58,408,[172,50,50])
        self.metadata = dict(path="ux0:data/celeste_native_room-synthetic.ppm",revision="synthetic",width=960,height=544,
                             stage=RENDER_STAGE,format="P6_RGB_top_down",frame=36,x=19,y=144,vx=0,vy=0,
                             ground=1,dead=0,resets=0,state=0,capture="initial_respawn",lifecycle="source_first_room",phase="live",
                             automatic_reloads=0,loads=1,respawn_callbacks=1,wipe_callbacks=0,
                             pending_corpses=0,committed_corpses=0,wipe_active=0,legacy_manual_replay="false",
                             render_style="animated_player_partial",camera="0,0",body_draws=1,bg_draws=1,fg_draws=1,
                             diagnostic_spike_markers=0,physical_spikes=5,draw_pieces=19,diagnostic_red_markers=0,spike_art="source_static_19",
                             static_decals=22,bg_decals=20,fg_decals=2,animated_omitted=7,decal_art="source_static_decal_cut",decal_page_bytes=32768,
                             submitted_rgba_bytes=232448,alpha="premultiplied_ONE_ONE_MINUS_SRC_ALPHA",body_pose="source_animated_with_simulated_hair",
                             hair_simulated=1,hair_count=4,hair_outline="black_16_draws",diagnostic_rng_seed=0,
                             original_startup_rng_parity="false",source_phase="level_after_update_then_render",animation="idle",body_frame=0,
                             source_texture="characters/player/idle00",hair_nodes="19,135;19,135;19,135;19,135;",hair_color="172,50,50,255")

    def set_pixel(self,x,y,color):
        self.pixels[(y*960+x)*3:(y*960+x+1)*3] = bytes(color)

    def write_frame(self):
        self.source.write_bytes(b"P6\n960 544\n255\n"+self.pixels)
        self.receipt.write_text("frame_saved "+" ".join(f"{key}={value}" for key,value in self.metadata.items())+"\n")

    def collect(self,output=None,**overrides):
        if output is None:
            output = self.output / str(self.output_counter)
            self.output_counter += 1
            output.mkdir()
        arguments = dict(capture="initial_respawn",visual_provenance=self.visuals,player_provenance=self.player,decal_provenance=self.decals)
        arguments.update(overrides)
        return collect_native_frame(self.root,output,"synthetic",**arguments)

    def test_first_live_initial_capture_retains_full_pixel_and_bank_checks(self):
        self.write_frame()
        frame = self.collect()
        self.assertEqual(frame["capture"],"initial_respawn")
        self.assertEqual(frame["frame_state"]["frame"],36)
        self.assertTrue(frame["black_letterbox_rows"])
        self.assertEqual(frame["textured_content"]["animated_player"]["texture"],"characters/player/idle00")
        self.assertEqual(len(frame["textured_content"]["spike_probes"]["probes"]),2)
        self.assertEqual(len(frame["textured_content"]["decal_probes"]["probes"]),4)

    def test_capture_absence_is_pending_not_a_startup_failure(self):
        self.assertIsNone(self.collect())

    def test_positive_app_frame_is_not_hardcoded_parameterized(self):
        for frame in (1,17,120):
            with self.subTest(frame=frame):
                self.metadata["frame"] = frame
                self.write_frame()
                self.assertEqual(self.collect()["frame_state"]["frame"],frame)

    def test_unclosed_export_without_receipt_is_pending(self):
        self.source.write_bytes(b"P6\n960 544\n255\n"+self.pixels)
        self.assertIsNone(self.collect())

    def test_receipt_without_image_is_pending(self):
        self.receipt.write_text("frame_saved partial\n")
        self.assertIsNone(self.collect())

    def test_wrong_policy_state_or_initial_counters_fail_parameterized(self):
        for key,value in (("capture","spawn"),("frame",0),("frame","01"),("frame",-1),("frame","nan"),
                          ("revision","stale"),("path","ux0:data/stale.ppm"),("state",14),("dead",1),("resets",1),
                          ("lifecycle","legacy_manual"),("phase","corpse"),("phase","respawn14"),("automatic_reloads",2),
                          ("loads",2),("respawn_callbacks",3),("wipe_callbacks",2),("pending_corpses",1),
                          ("committed_corpses",1),("wipe_active",1),("legacy_manual_replay","true"),("body_draws",0),
                          ("render_style","debug"),("alpha","disabled"),("source_texture","wrong"),("hair_nodes","nan,135;"*4)):
            with self.subTest(key=key,value=value):
                original = self.metadata[key]
                self.metadata[key] = value
                self.write_frame()
                with self.assertRaises(ValueError):
                    self.collect()
                self.metadata[key] = original

    def test_each_initial_lifecycle_field_is_required_parameterized(self):
        for key in ("capture","lifecycle","phase","automatic_reloads","loads","respawn_callbacks","wipe_callbacks",
                    "pending_corpses","committed_corpses","wipe_active","legacy_manual_replay"):
            with self.subTest(key=key):
                original = self.metadata.pop(key)
                self.write_frame()
                with self.assertRaises(ValueError):
                    self.collect()
                self.metadata[key] = original

    def test_profile_provenance_is_required_parameterized(self):
        self.write_frame()
        for overrides in ({"visual_provenance":None},{"player_provenance":None},
                          {"player_provenance":self.player | {"death_animation_extension":False}},
                          {"player_provenance":self.player | {"bank_sha256":"0"*64}}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.collect(**overrides)

    def test_relabeled_black_pixels_fail_even_with_forged_live_receipt(self):
        self.pixels[:] = bytes(len(self.pixels))
        self.write_frame()
        with self.assertRaisesRegex(ValueError,"color diversity"):
            self.collect()

    def test_wrong_room_spike_decal_or_player_pixels_fail_parameterized(self):
        for x,y in ((4,4),(8,8),(20,20),(58,408)):
            with self.subTest(pixel=(x,y)):
                original = self.pixels[(y*960+x)*3:(y*960+x+1)*3]
                self.set_pixel(x,y,[0,0,0])
                self.write_frame()
                with self.assertRaises(ValueError):
                    self.collect()
                self.set_pixel(x,y,original)

    def test_partial_closed_receipt_fails(self):
        self.write_frame()
        self.receipt.write_text(self.receipt.read_text().rstrip("\n"))
        with self.assertRaises(ValueError):
            self.collect()

    def test_partial_pixel_payload_fails(self):
        self.write_frame()
        self.source.write_bytes(self.source.read_bytes()[:-1])
        with self.assertRaisesRegex(ValueError,"pixel length"):
            self.collect()

    def test_duplicate_initial_counter_fails(self):
        self.write_frame()
        self.receipt.write_text(self.receipt.read_text().rstrip("\n")+" loads=1\n")
        with self.assertRaises(ValueError):
            self.collect()

    def test_exclusive_artifact_preservation_remains_binding(self):
        self.write_frame()
        self.collect(self.output)
        with self.assertRaises(FileExistsError):
            self.collect(self.output)


class CapturePolicyTests(unittest.TestCase):
    def test_conflicting_capture_overrides_fail(self):
        with self.assertRaises(ValueError):
            native_capture_policy(True,False,True,True)

    def test_profile_and_existing_overrides_select_explicit_policies_parameterized(self):
        for animated,replay,wall,climb,expected in (
                (False,False,False,False,"spawn"),(True,False,False,False,"initial_respawn"),
                (True,True,False,False,"spawn"),(True,False,True,False,"wall_jump"),
                (True,False,False,True,"climb"),(True,True,False,True,"climb")):
            with self.subTest(animated=animated,replay=replay,wall=wall,climb=climb):
                self.assertEqual(native_capture_policy(animated,replay,wall,climb),expected)


class InitialRespawnHostTests(unittest.TestCase):
    setUp = InitialRespawnFeedbackTests.setUp
    set_pixel = InitialRespawnFeedbackTests.set_pixel
    run_scenario = test_guest_replay.ReplayHostBoundaryTests.run_scenario

    def frame_fixture(self,**overrides):
        metadata = self.metadata | overrides
        return {"ppm":b"P6\n960 544\n255\n"+self.pixels,
                "receipt":"frame_saved "+" ".join(f"{key}={value}" for key,value in metadata.items())+"\n",
                "provenance":{"render_style":"animated_player_partial","visuals":self.visuals,"player":self.player,"decals":self.decals}}

    def test_ready_zero_can_precede_closed_meaningful_native_capture(self):
        feedback, _ = self.run_scenario("deferred_frame",automatic=True,frame_fixture=self.frame_fixture())
        self.assertTrue(feedback["stages"]["full_completion"])
        self.assertEqual(feedback["capture_policy"],"initial_respawn")
        self.assertEqual(feedback["frame"]["capture"],"initial_respawn")
        self.assertEqual(feedback["frame"]["frame_state"]["frame"],36)

    def test_late_capture_cannot_counterfeit_first_observed_normal(self):
        feedback, _ = self.run_scenario("wrong_capture_frame",automatic=True,frame_fixture=self.frame_fixture(frame=37))
        self.assertTrue(feedback["stages"]["native_image"])
        self.assertFalse(feedback["stages"]["full_completion"])
        self.assertIn("first observed Normal",feedback["errors"][0]["message"])

    def test_forged_success_logs_cannot_promote_black_or_intro_image_parameterized(self):
        for black in (False,True):
            with self.subTest(black=black):
                fixture = self.frame_fixture() if black else self.frame_fixture(frame=0,capture="spawn",state=14,body_draws=0)
                if black:
                    fixture["ppm"] = b"P6\n960 544\n255\n"+bytes(960*544*3)
                feedback, order = self.run_scenario("invalid_native_frame",automatic=True,frame_fixture=fixture)
                self.assertFalse(feedback["stages"]["full_completion"])
                self.assertEqual(order,["installer","runtime"])


if __name__ == "__main__":
    unittest.main()
