import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from native_material_pack import pack_crops, verify_pin, write_new
from native_room_textures import blit_extruded, plan_rectangles
import prepare_gameplay_material_pack as completion


class MaterialPackTests(unittest.TestCase):
    def test_determinism_ignores_input_order(self):
        crops = {'synthetic/a': (3, 2, bytes(range(24))),
                 'synthetic/b': (2, 3, bytes(range(24)))}
        self.assertEqual(pack_crops(crops), pack_crops(dict(reversed(list(crops.items())))))

    def test_every_border_pixel_is_extruded_without_changing_rgba(self):
        rgba = bytes(range(24))
        pages, layout = pack_crops({'synthetic/a': (3, 2, rgba)})
        page, x, y = layout['synthetic/a']
        for dy in range(-1, 3):
            for dx in range(-1, 4):
                with self.subTest(dx=dx, dy=dy):
                    start = ((y + dy) * 128 + x + dx) * 4
                    source = (min(1, max(0, dy)) * 3 + min(2, max(0, dx))) * 4
                    self.assertEqual(pages[page][start:start + 4], rgba[source:source + 4])

    def test_dry_run_stops_at_page_budget(self):
        with self.assertRaisesRegex(ValueError, 'page budget'):
            plan_rectangles({f'synthetic/{i}': (126, 126) for i in range(3)}, 128, 128, 2)

    def test_short_or_oversized_pixels_rejected(self):
        for size in (15, 17):
            with self.subTest(size=size), self.assertRaises(ValueError):
                pack_crops({'synthetic/a': (2, 2, bytes(size))})

    def test_invalid_rectangle_rejected_parameterized(self):
        for shape in ((0, 1), (-1, 1), (127, 1), (1, 127), (2**63, 1)):
            with self.subTest(shape=shape), self.assertRaises(ValueError):
                plan_rectangles({'synthetic/a': shape}, 128, 128, 2)

    def test_pin_failure_precedes_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'synthetic.bin'
            source.write_bytes(b'changed')
            output = root / 'output'
            with self.assertRaisesRegex(ValueError, 'pin'):
                verify_pin({'path': str(source), 'bytes': 7, 'sha256': hashlib.sha256(b'original').hexdigest()})
                write_new(output, b'not reached')
            self.assertFalse(output.exists())

    def test_output_is_exclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.bin'
            write_new(path, b'first')
            with self.assertRaises(FileExistsError):
                write_new(path, b'second')
            self.assertEqual(path.read_bytes(), b'first')

    def test_generator_rejects_changed_profile_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root / 'profile.json'
            profile.write_bytes(b'{}')
            with patch.object(completion, 'AUDIT', root), self.assertRaisesRegex(ValueError, 'pin'):
                completion.prepare(profile, '0' * 64, root / 'new-output')
            self.assertFalse((root / 'new-output').exists())

    def test_two_full_rectangles_get_two_bounded_pages(self):
        pixels = bytes([3, 2, 1, 127]) * (126 * 126)
        pages, layout = pack_crops({'synthetic/a': (126, 126, pixels), 'synthetic/b': (126, 126, pixels)})
        self.assertEqual([len(page) for page in pages], [65536, 65536])
        self.assertEqual(layout, {'synthetic/a': (0, 1, 1), 'synthetic/b': (1, 1, 1)})

    def test_invalid_blit_fails_without_resizing_page(self):
        page = bytearray(16 * 16 * 4)
        before = bytes(page)
        with self.assertRaises(ValueError):
            blit_extruded(page, 16, 16, bytes(16), 2, 2, 15, 1)
        self.assertEqual(bytes(page), before)


if __name__ == '__main__':
    unittest.main()
