import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import prepare_spring_material_catalog as catalog
from native_room_textures import atlas_metadata


class SpringMaterialCatalogTests(unittest.TestCase):
    def frames(self):
        return {f'owned/spring/{name}':['Gameplay0',index*20,24,6,4,-3,-10,18,20]
                for index,name in enumerate(['00','01','02','03','04','05','white'])}

    def test_one_idle_frame_retains_signed_trim_and_logical_bottom_center(self):
        atlas=self.frames()
        frame=catalog.materials(atlas,{key:tuple(value) for key,value in atlas.items()},'owned/spring/')
        self.assertEqual((frame['key'],frame['offset_x'],frame['offset_y'],frame['frame_width'],frame['frame_height']),
                         ('owned/spring/00',-3,-10,18,20))

    def test_missing_duplicate_or_unknown_family_metadata_parameterized(self):
        for scenario in range(4):
            with self.subTest(scenario=scenario):
                atlas=self.frames();metadata={key:tuple(value) for key,value in atlas.items()}
                if scenario==0:del atlas['owned/spring/05']
                if scenario==1:atlas['owned/spring/06']=atlas['owned/spring/00']
                if scenario==2:del metadata['owned/spring/white']
                if scenario==3:metadata['owned/spring/00']=tuple(atlas['owned/spring/01'])
                with self.assertRaises(ValueError):catalog.materials(atlas,metadata,'owned/spring/')

    def test_range_trim_type_and_schema_reject_parameterized(self):
        for index,value in [(1,4096),(3,0),(5,3),(6,-17),(7,8),(8,0),(1,True)]:
            with self.subTest(index=index,value=value):
                atlas=self.frames();atlas['owned/spring/00'][index]=value
                with self.assertRaises(ValueError):
                    catalog.materials(atlas,{key:tuple(row) for key,row in atlas.items()},'owned/spring/')

    def test_sprite_maximum_logical_dimensions_cannot_silently_change_origin(self):
        atlas=self.frames();atlas['owned/spring/white'][7]=20
        with self.assertRaisesRegex(ValueError,'logical'):
            catalog.materials(atlas,{key:tuple(row) for key,row in atlas.items()},'owned/spring/')

    def test_duplicate_json_key_rejects(self):
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            json.loads('{"owned":1,"owned":2}',object_pairs_hook=catalog.unique_object)

    def test_raw_metadata_duplicate_unknown_trailing_reject_parameterized(self):
        def text(value):return bytes([len(value)])+value.encode()
        entry=text('owned')+struct.pack('<8h',1,2,6,4,-3,-10,18,20)
        header=struct.pack('<i',5)+text('fixture')+struct.pack('<i',0)+struct.pack('<h',1)+text('Gameplay0')
        valid=header+struct.pack('<h',1)+entry
        self.assertEqual(len(atlas_metadata(valid)),1)
        for invalid in (header+struct.pack('<h',2)+entry+entry,valid+text('UNKNOWN'),valid[:-1],valid+b'\0'):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):atlas_metadata(invalid)

    def test_all_input_pin_failures_precede_output_creation(self):
        original={name:('owned '+name).encode() for name in catalog.PINS}
        pins={name:hashlib.sha256(value).hexdigest() for name,value in original.items()}
        for name in pins:
            with self.subTest(name=name):
                inputs=dict(original);inputs[name]+=b'changed'
                with patch.dict(catalog.PINS,pins,clear=True), \
                     patch.object(Path,'read_bytes',lambda path:inputs[path.name]), \
                     patch.object(Path,'exists',return_value=False), patch.object(Path,'mkdir') as mkdir:
                    with self.assertRaisesRegex(ValueError,'input pin changed: '+name):
                        catalog.prepare({key:Path(key) for key in pins},catalog.AUDIT/'owned-pin-negative/catalog.txt')
                    mkdir.assert_not_called()

    def test_missing_or_unknown_input_name_rejects_before_read(self):
        for names in [set(catalog.PINS)-{'spring'},set(catalog.PINS)|{'unknown'}]:
            with self.subTest(names=names),patch.object(Path,'read_bytes') as read:
                with self.assertRaisesRegex(ValueError,'input names'):
                    catalog.prepare({name:Path(name) for name in names},catalog.AUDIT/'owned-shape-negative/catalog.txt')
                read.assert_not_called()

    def test_existing_output_directory_is_never_reused(self):
        with patch.object(Path,'exists',return_value=True),patch.object(Path,'mkdir') as mkdir:
            with self.assertRaisesRegex(ValueError,'fresh'):
                catalog.prepare({name:Path(name) for name in catalog.PINS},catalog.AUDIT/'owned-existing/catalog.txt')
            mkdir.assert_not_called()


if __name__=='__main__':unittest.main()
