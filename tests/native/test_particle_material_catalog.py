import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import prepare_particle_material_catalog as catalog


class ParticleMaterialCatalogTests(unittest.TestCase):
    def atlas(self):
        return {f'synthetic/dust{index}': ['Synthetic', index*10, 10, 5, 6, -2, -1, 8, 8]
                for index in range(4)}

    def source(self):
        keys = ', '.join(f'GFX.Game["synthetic/dust{index}"]' for index in range(4))
        return 'Chooser<MTexture> sourceChooser = new Chooser<MTexture>(' + keys + ');'

    def test_four_frames_keep_original_center_and_source_chooser_order(self):
        frames = catalog.materials(self.atlas(), self.source())
        self.assertEqual([frame['key'] for frame in frames], [f'synthetic/dust{i}' for i in range(4)])
        self.assertTrue(all(frame['frame_width'] == frame['frame_height'] == 8 for frame in frames))

    def test_missing_frame_rejects(self):
        atlas = self.atlas(); del atlas['synthetic/dust3']
        with self.assertRaisesRegex(ValueError, 'missing'):
            catalog.materials(atlas, self.source())

    def test_unknown_original_frame_rejects(self):
        atlas = self.atlas(); atlas['synthetic/dust0'][7] = 10
        with self.assertRaisesRegex(ValueError, 'original center'):
            catalog.materials(atlas, self.source())

    def test_invalid_source_chooser_parameterized(self):
        for source in ['', self.source().replace('dust3', 'dust2'), self.source().replace('sourceChooser', 'sourceChooser2')]:
            with self.subTest(source=source), self.assertRaises(ValueError):
                catalog.materials(self.atlas(), source)

    def test_invalid_atlas_bounds_parameterized(self):
        for index, value in [(1,4096), (3,0), (5,-4097), (7,0)]:
            with self.subTest(index=index):
                atlas = self.atlas(); atlas['synthetic/dust0'][index] = value
                with self.assertRaises(ValueError):
                    catalog.materials(atlas, self.source())

    def test_duplicate_atlas_key_rejects(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            json.loads('{"key":1,"key":2}', object_pairs_hook=catalog.unique_object)

    def test_input_pin_failure_precedes_any_output_parameterized(self):
        for target in range(2):
            with self.subTest(target=target):
                pins = [catalog.ATLAS_SHA, catalog.SOURCE_SHA]; pins[target] = '0'*64
                with patch.object(catalog, 'file_identity', side_effect=[{'sha256': pin} for pin in pins]), \
                     patch.object(Path, 'exists', return_value=False), patch.object(Path, 'mkdir') as mkdir:
                    with self.assertRaisesRegex(ValueError, 'Pinned Dust'):
                        catalog.prepare(Path('atlas'), Path('source'), catalog.AUDIT / 'synthetic-negative/catalog.txt')
                    mkdir.assert_not_called()

    def test_nonprivate_output_rejects_without_reading_inputs(self):
        with patch.object(catalog, 'file_identity') as read:
            with self.assertRaisesRegex(ValueError, 'private'):
                catalog.prepare(Path('atlas'), Path('source'), Path('/public/catalog.txt'))
            read.assert_not_called()

    def test_existing_destination_rejects_without_reading_inputs(self):
        with patch.object(Path, 'exists', return_value=True), patch.object(catalog, 'file_identity') as read:
            with self.assertRaisesRegex(ValueError, 'exclusive'):
                catalog.prepare(Path('atlas'), Path('source'), catalog.AUDIT / 'existing/catalog.txt')
            read.assert_not_called()


if __name__ == '__main__':
    unittest.main()
