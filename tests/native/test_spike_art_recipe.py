import struct
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from native_room_feedback import validate_spike_art_pixels
from prepare_spike_art import FAMILIES, INPUT_SHA, MAP_SHA, float32, parse_visual_text, verify_piece


def bits(value):
    return struct.pack(">f", value).hex()


def hitbox_piece():
    return {"direction": "up", "hazard": 0, "index": 0, "texture": "danger/spikes/default_up00",
            "clip": [30, 176, 7, 6],
            "position_bits": [bits(44), bits(169)], "origin_bits": [bits(4), bits(6)],
            "scale_bits": [bits(1), bits(1)], "rotation_bits": bits(0),
            "vertices_bits": [bits(40), bits(163), bits(47), bits(163), bits(40), bits(169), bits(47), bits(169)],
            "texcoords_bits": [bits(30/4096), bits(176/4096), bits(37/4096), bits(176/4096),
                               bits(30/4096), bits(182/4096), bits(37/4096), bits(182/4096)],
            "x": 40, "y": 163, "width": 7, "height": 6}


class SpikeArtRecipeTests(unittest.TestCase):
    def test_source_piece_resolves_from_justify_and_draw_offset(self):
        hazards = [{"direction": "up", "position": [40, 168], "size": 40}]
        piece = verify_piece(hitbox_piece(), hazards, FAMILIES)
        self.assertEqual((piece["x"], piece["y"], piece["width"], piece["height"]), (40, 163, 7, 6))
        self.assertEqual(float32(hitbox_piece()["position_bits"][0]), 44.0)

    def test_source_piece_rejects_shifted_or_wrong_size_geometry(self):
        hazards = [{"direction": "up", "position": [40, 168], "size": 40}]
        for key, value in (("x", 41), ("y", 162), ("width", 6), ("direction", "left")):
            piece = hitbox_piece()
            piece[key] = value
            with self.assertRaises(ValueError):
                verify_piece(piece, hazards, FAMILIES)

    def test_six_texture_visual_protocol_is_exact(self):
        profile = "64 128 48 120 0 0 48 120 00000000"
        text = "CSRV1\n" + INPUT_SHA + "\n" + MAP_SHA + "\n6\n" + (profile + "\n") * 6 + "0\n"
        self.assertEqual(parse_visual_text(text), ([profile] * 6, []))
        with self.assertRaises(ValueError):
            parse_visual_text(text.replace("CSRV1", "CSRV2"))

    def test_native_spike_probes_require_both_orientations_and_occlusion(self):
        visuals = {"spike_content_probes": [
                       {"kind": "visible_source_spike", "direction": "up", "screen_pixel": [0, 0], "expected_rgb": [1, 2, 3]},
                       {"kind": "foreground_occludes_spike", "direction": "left", "screen_pixel": [1, 0], "expected_rgb": [4, 5, 6]}],
                   "piece_visibility": [{"visible_opaque_texels": 1, "occluded_opaque_texels": 1}]}
        pixels = bytearray(960 * 544 * 3)
        pixels[0:6] = bytes([1, 2, 3, 4, 5, 6])
        result = validate_spike_art_pixels(bytes(pixels), visuals)
        self.assertEqual(result["pieces"], 1)

        pixels[0] = 9
        with self.assertRaises(ValueError):
            validate_spike_art_pixels(bytes(pixels), visuals)
        visuals["spike_content_probes"] = visuals["spike_content_probes"][:1]
        with self.assertRaises(ValueError):
            validate_spike_art_pixels(bytes(pixels), visuals)


if __name__ == "__main__":
    unittest.main()
