import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"scripts"))
import prepare_strawberry_material_catalog as catalog


class StrawberryMaterialCatalogTests(unittest.TestCase):
    def sprite(self):
        return ET.fromstring('<Sprites><strawberry path="synthetic/" start="idle"><Center/>'
                             '<Loop id="idle" path="frame" delay=".1" '
                             'frames="0-6,0-6,0-6,0-6,0-7"/></strawberry></Sprites>')

    def atlas(self):
        return {f"synthetic/frame{index:02}":["Synthetic",index*20,10,10,12,-4,-1,18,16]
                for index in range(8)}

    def test_animation_index_maps_to_eight_texture_frames(self):
        frames, sequence = catalog.materials(self.atlas(),self.sprite())
        self.assertEqual(sequence,list(range(7))*4+list(range(8)))
        self.assertEqual(len(frames),8)
        self.assertEqual(frames[sequence[8]]["key"],"synthetic/frame01")

    def test_missing_texture_frame_rejects(self):
        atlas=self.atlas();del atlas["synthetic/frame07"]
        with self.assertRaisesRegex(ValueError,"missing"):
            catalog.materials(atlas,self.sprite())

    def test_invalid_frame_metadata_parameterized(self):
        for index,value in [(1,4096),(3,0),(5,-4097),(7,0)]:
            with self.subTest(index=index):
                atlas=self.atlas();atlas["synthetic/frame00"][index]=value
                with self.assertRaises(ValueError):catalog.materials(atlas,self.sprite())

    def test_unsupported_animation_parameterized(self):
        for name,value in [("id","flap"),("frames","0-8"),("delay",".2")]:
            with self.subTest(name=name):
                sprite=self.sprite();sprite.find('strawberry/Loop').set(name,value)
                with self.assertRaises(ValueError):catalog.materials(self.atlas(),sprite)

    def test_duplicate_animation_rejects(self):
        sprite=self.sprite();sprite.find('strawberry').append(sprite.find('strawberry/Loop'))
        with self.assertRaises(ValueError):catalog.materials(self.atlas(),sprite)

    def test_duplicate_json_key_rejects(self):
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            json.loads('{"a":1,"a":2}',object_pairs_hook=catalog.unique_object)

    def test_input_pin_failure_precedes_any_output_parameterized(self):
        for target in range(3):
            with self.subTest(target=target):
                pins = [catalog.ATLAS_SHA,catalog.SPRITES_SHA,catalog.SOURCE_SHA]
                pins[target] = '0'*64
                with patch.object(catalog,'file_identity',side_effect=[{'sha256':pin} for pin in pins]), \
                     patch.object(Path,'exists',return_value=False), patch.object(Path,'mkdir') as mkdir:
                    with self.assertRaisesRegex(ValueError,'Pinned Strawberry'):
                        catalog.prepare(Path('atlas'),Path('sprites'),Path('source'),catalog.AUDIT/'synthetic-pin-negative/catalog.txt')
                    mkdir.assert_not_called()


if __name__ == '__main__':unittest.main()
