import hashlib
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import native_room_feedback as feedback
import test_initial_respawn_feedback as initial_feedback


class DashProbeFeedbackTests(unittest.TestCase):
    setUp = initial_feedback.InitialRespawnFeedbackTests.setUp
    set_pixel = initial_feedback.InitialRespawnFeedbackTests.set_pixel

    def prepare_probe(self):
        self.source = self.source.with_name("celeste_native_room-synthetic-dash-probe.ppm")
        self.receipt = Path(str(self.source) + ".txt")
        self.raw_path = Path(str(self.source) + ".trail.rgba")
        self.raw = bytearray(512 * 512 * 4)
        for slot in range(3):
            self.set_raw(slot * 64 + 32, 32, [255] * 4)
        for y in range(452, 468):
            for x in range(452, 476):
                self.set_raw(x, y, [192 if 460 <= x < 468 else 128] * 4)
        for y in range(452, 460):
            for x in range(484, 500):
                self.set_raw(x, y, [255] * 4)
        for y in range(468, 472):
            for x in range(484, 488):
                self.set_raw(x, y, [64] * 4)
        self.metadata.update(path="ux0:data/" + self.source.name, frame=59, capture="dash_trails",
                             trail_depth=1, trail_target_logical_RGBA_bytes=1048576,
                             trail_snapshots="0,0.5,19,140,6,17,23,23;1,0.25,19,120,21,57,80,80;2,0,19,100,51,137,191,191;",
                             trail_probe="diagnostic_rgba_fbo", swatch_single=128, swatch_inner_union=192,
                             swatch_opaque=255, swatch_orientation=64, other_captured_tiles_preserved=1,
                             single_ghost_xy="200,16", between_ghost_xy="240,16;248,16",
                             tint_rgba="51,137,191,191", FBO_RGBA="512x512", raw_rows="GL_bottom_up",
                             probe_fixture="first_room_dash_trails_v1", native_probe_checks=1,
                             probe_fixture_sha256="3d34e2a2335db02f8ee6493eb44068a7bcd4ad7bbf33f414a8ecdc85df50c324")

    def set_raw(self, x, top, color):
        offset = ((511 - top) * 512 + x) * 4
        self.raw[offset:offset + 4] = bytes(color)

    def write_probe(self):
        self.source.write_bytes(b"P6\n960 544\n255\n" + self.pixels)
        self.receipt.write_text("frame_saved " + " ".join(f"{key}={value}" for key, value in self.metadata.items()) + "\n")
        self.raw_path.write_bytes(self.raw)

    def collect(self):
        output = self.output / str(self.output_counter)
        self.output_counter += 1
        output.mkdir()
        return feedback.collect_native_frame(self.root, output, "synthetic", capture="dash_trails",
                                             visual_provenance=self.visuals, player_provenance=self.player,
                                             decal_provenance=self.decals)

    def test_raw_bottom_up_rgba_is_preserved_without_claiming_frame_compositing(self):
        self.prepare_probe()
        self.write_probe()
        frame = self.collect()
        artifact = frame["artifacts"]["native-trail.rgba"]
        self.assertEqual(Path(artifact["path"]).read_bytes(), self.raw)
        self.assertEqual(artifact["sha256"], hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(frame["dash_probe"]["raw_swatch_pixels_checked"], 4096)
        self.assertEqual(frame["dash_probe"]["frame_compositing"], "pending_parent_visual_review")
        self.assertFalse(frame["dash_probe"]["physical_proof"])

    def test_dash_does_not_inherit_initial_respawn_callback_counts(self):
        self.prepare_probe()
        self.metadata.update(loads=3, respawn_callbacks=3, automatic_reloads=2)
        self.write_probe()
        self.assertEqual(self.collect()["capture"], "dash_trails")

    def test_lower_rows_are_recorded_not_required_to_be_black(self):
        self.prepare_probe()
        self.set_pixel(40, 543, [23, 35, 47])
        self.write_probe()
        self.assertFalse(self.collect()["black_letterbox_rows"])

    def test_wrong_receipt_fields_fail_parameterized(self):
        self.prepare_probe()
        for key, value in (("revision", "stale"), ("path", "ux0:data/stale.ppm"), ("capture", "spawn"),
                           ("frame", 0), ("frame", "01"), ("frame", 360), ("state", 14), ("dead", 1),
                           ("other_captured_tiles_preserved", 0), ("raw_rows", "top_down"),
                           ("FBO_RGBA", "256x256"), ("swatch_inner_union", 128), ("trail_depth", 0),
                           ("trail_snapshots", "0,0.5,19,140,6,22,31,31;")):
            with self.subTest(key=key, value=value):
                original = self.metadata[key]
                self.metadata[key] = value
                self.write_probe()
                with self.assertRaises(ValueError):
                    self.collect()
                self.metadata[key] = original

    def test_wrong_raw_size_fails_parameterized(self):
        self.prepare_probe()
        self.write_probe()
        for raw in (self.raw[:-1], self.raw + b"x", bytes(len(self.raw))):
            with self.subTest(size=len(raw)):
                self.raw_path.write_bytes(raw)
                with self.assertRaises(ValueError):
                    self.collect()

    def test_raw_swatch_all_channels_and_regions_fail_parameterized(self):
        self.prepare_probe()
        for x, y in ((454, 454), (462, 454), (486, 454), (486, 470), (448, 448)):
            for channel in range(4):
                with self.subTest(x=x, y=y, channel=channel):
                    offset = ((511 - y) * 512 + x) * 4 + channel
                    original = self.raw[offset]
                    self.raw[offset] = 255 if original == 0 else 0
                    self.write_probe()
                    with self.assertRaises(ValueError):
                        self.collect()
                    self.raw[offset] = original

    def test_top_down_raw_is_not_silently_normalized(self):
        self.prepare_probe()
        self.raw[:] = b"".join(self.raw[y * 2048:(y + 1) * 2048] for y in reversed(range(512)))
        self.write_probe()
        with self.assertRaises(ValueError):
            self.collect()

    def test_quantized_swatch_values_within_one_byte_are_allowed(self):
        self.prepare_probe()
        self.set_raw(454, 454, [127, 128, 129, 129])
        self.metadata["swatch_single"] = 129
        self.write_probe()
        self.assertIsNotNone(self.collect())

    def test_reported_swatch_must_equal_the_actual_exported_alpha(self):
        self.prepare_probe()
        self.metadata["swatch_single"] = 129
        self.write_probe()
        with self.assertRaises(ValueError):
            self.collect()

    def test_closed_receipt_without_raw_fails_not_pending(self):
        self.prepare_probe()
        self.write_probe()
        self.raw_path.unlink()
        with self.assertRaises(ValueError):
            self.collect()

    def test_duplicate_fields_fail(self):
        self.prepare_probe()
        self.write_probe()
        self.receipt.write_text(self.receipt.read_text().rstrip("\n") + " raw_rows=GL_bottom_up\n")
        with self.assertRaises(ValueError):
            self.collect()

    def test_unclosed_receipt_fails(self):
        self.prepare_probe()
        self.write_probe()
        self.receipt.write_text(self.receipt.read_text().rstrip("\n"))
        with self.assertRaises(ValueError):
            self.collect()

    def test_truncated_or_wrong_size_frame_fails_parameterized(self):
        self.prepare_probe()
        self.write_probe()
        original = self.source.read_bytes()
        for data in (original[:-1], original + b"x", original.replace(b"960 544", b"960 543", 1)):
            with self.subTest(size=len(data)):
                self.source.write_bytes(data)
                with self.assertRaises(ValueError):
                    self.collect()

    def test_corrupt_captured_tile_fails(self):
        self.prepare_probe()
        self.set_raw(32, 32, [255, 0, 255, 255])
        self.write_probe()
        with self.assertRaises(ValueError):
            self.collect()

    def test_missing_provenance_cannot_claim_textured_dash_proof_parameterized(self):
        self.prepare_probe()
        self.write_probe()
        for key in ("visual_provenance", "player_provenance", "decal_provenance"):
            arguments = dict(visual_provenance=self.visuals, player_provenance=self.player, decal_provenance=self.decals)
            arguments[key] = None
            with self.subTest(key=key), self.assertRaises(ValueError):
                feedback.collect_native_frame(self.root, self.output, "synthetic", capture="dash_trails", **arguments)

    def test_collection_does_not_establish_current_run_freshness(self):
        self.prepare_probe()
        self.write_probe()
        result = self.collect()["dash_probe"]
        self.assertEqual(result["freshness"], "not_established_by_offline_collection")
        self.assertFalse(result["runtime_completion"])

    def test_existing_artifact_is_never_overwritten(self):
        self.prepare_probe()
        self.write_probe()
        destination = self.output / "0"
        destination.mkdir()
        artifact = destination / "native-trail.rgba"
        artifact.write_bytes(b"prior evidence")
        with self.assertRaises(FileExistsError):
            feedback.collect_native_frame(self.root, destination, "synthetic", capture="dash_trails",
                                          visual_provenance=self.visuals, player_provenance=self.player,
                                          decal_provenance=self.decals)
        self.assertEqual(artifact.read_bytes(), b"prior evidence")


if __name__ == "__main__":
    unittest.main()
