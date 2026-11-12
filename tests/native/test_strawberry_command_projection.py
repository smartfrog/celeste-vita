"""514-frame logical Sprite differential, using the frozen SOURCE trace only as an oracle.

Identity lifetime checks are bounded to this zero-reload route, not generic reload support.
No Bloom/Light rendergraph, GL/GPU, physics, or pixel equivalence is asserted.
"""
import copy
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from prepare_strawberry_material_catalog import AUDIT, ATLAS_SHA, SOURCE_SHA, SPRITES_SHA
from test_spike_command_projection import ROOMS, ROOMS_IDENTITY, float32, require
from test_native_gameplay_draw_projection import (SOURCE_TRACE, SOURCE_IDENTITY, file_identity,
                                                 sample_source, source_keys, native_keys)
from prepare_native_transition_fixture import room_records

CATALOG = Path(os.environ.get('CELESTE_STRAWBERRY_CATALOG', AUDIT / 'descriptor-01/catalog.txt'))
NATIVE = Path(os.environ.get('CELESTE_STRAWBERRY_NATIVE_TRACE', AUDIT / 'proof-01/combined-release.jsonl'))
FRAMES = 514


def read_catalog(path):
    lines = path.read_text().splitlines()
    require(len(lines) == 15 and lines[0] == 'CSTR1', 'Invalid Strawberry catalog shape')
    require(lines[1:4] == [SOURCE_SHA, ATLAS_SHA, SPRITES_SHA], 'Strawberry catalog provenance changed')
    require(lines[4] == 'idle 36' and lines[6] == '8', 'Unsupported Strawberry animation/count')
    sequence = list(map(int, lines[5].split()))
    require(sequence == list(range(7)) * 4 + list(range(8)), 'Strawberry animation sequence changed')
    frames = []
    for index, line in enumerate(lines[7:]):
        fields = line.split()
        require(len(fields) == 11 and fields[0] == str(index), 'Invalid Strawberry catalog frame index')
        x, y, width, height, ox, oy, fw, fh = map(int, fields[2:10])
        require(0 <= x <= 4096-width and 0 <= y <= 4096-height and width > 0 and height > 0,
                'Invalid Strawberry catalog crop')
        require(0 < fw <= 4096 and 0 < fh <= 4096 and abs(ox) <= 4096 and abs(oy) <= 4096,
                'Invalid Strawberry catalog trim/frame')
        require(fields[10] not in [frame['texture'] for frame in frames], 'Duplicate Strawberry catalog key')
        frames.append({'texture': fields[10], 'sheet': fields[1], 'sourceRectangle': [x,y,width,height],
                       'origin': [fw*.5+ox,fh*.5+oy]})
    return frames, sequence


def read_source(path):
    require(file_identity(ROOMS) == ROOMS_IDENTITY, 'Pinned rooms changed')
    authored = [(room['name'], obj) for room in room_records(json.loads(ROOMS.read_text()))
                for obj in room['objects'] if obj[0] == 'strawberry']
    require(len(authored) == 1 and authored[0][0] == '2' and authored[0][1][1:4] == [11,336,-144],
            'Pinned authored Strawberry facts changed')
    ticks, current, entities = {}, None, {}
    with path.open() as stream:
        for line in stream:
            if line.startswith('{"event":"draw-state"'):
                row = json.loads(line)
                if row['phase'] != 'before-draw': continue
                current = row['tick']
                if current >= FRAMES: break
                entities = {value['id']: value for value in row['state']['entities']}
                ticks[current] = []
            elif line.startswith('{"event":"draw-command"') and '"Strawberry"' in line:
                row = json.loads(line)
                require(row['tick'] == current, 'SOURCE command phase/tick changed')
                owner = entities[row['owner']['entity']]
                require(owner['type'] == 'Strawberry' and owner['position'] == authored[0][1][2:4],
                        'SOURCE Strawberry does not bind pinned authored position')
                sprites = [component['id'] for component in owner['components'] if component['type'] == 'Sprite']
                require(sprites == [row['owner']['component']] and row['owner']['componentType'] == 'Sprite',
                        'SOURCE Strawberry command is not the actual Sprite component')
                ticks[current].append(dict(row, room='2', authoredId=11))
    require(sorted(ticks) == list(range(FRAMES)), 'Incomplete SOURCE route')
    require(all(len(ticks[tick]) == int(tick >= 374) for tick in ticks), 'SOURCE Strawberry lifetime changed')
    return ticks


def read_native(path):
    native = {'rosters': {}, 'dispatches': {}, 'commands': {tick: [] for tick in range(FRAMES)}, 'states': {}}
    names = {'draw-owner-roster': 'rosters', 'draw-owner-dispatch': 'dispatches'}
    with path.open() as stream:
        for line in stream:
            if not line.startswith(('{"event":"draw-owner-', '{"event":"strawberry-command"', '{"event":"phase"')): continue
            row = json.loads(line)
            if row['event'] in names:
                destination = native[names[row['event']]]
                require(row['tick'] not in destination, 'Duplicate native roster/dispatch tick')
                destination[row['tick']] = row
            elif row['event'] == 'strawberry-command': native['commands'][row['tick']].append(row)
            elif row['phase'] == 'after-frame': native['states'][row['tick']] = row['state']
    require(all(sorted(native[key]) == list(range(FRAMES)) for key in native), 'Incomplete native route')
    return native


def validate_bindings(native):
    identities, semantic_ids = {}, {}
    for tick in range(FRAMES):
        live = native['rosters'][tick]['live']
        by_id = {owner['identity']: owner for owner in live}
        require(len(by_id) == len(live), 'Aliased native roster identity')
        dispatch = native['dispatches'][tick]['order']
        require(dispatch == [owner['identity'] for owner in live if owner['visible'] and not owner['hudExcluded']],
                'Native dispatch differs from whole roster')
        expected = [identity for identity in dispatch if by_id[identity]['kind'] == 'Strawberry']
        commands = native['commands'][tick]
        require([command['ownerIdentity'] for command in commands] == expected, 'Strawberry command owner/dispatch mismatch')
        for index, command in enumerate(commands):
            owner = by_id[command['ownerIdentity']]
            key = owner['room'], owner['authoredId']
            require(command['index'] == index and (command['room'],command['authoredId']) == key and command['piece'] == 0,
                    'Strawberry command semantic binding/piece mismatch')
            identity = owner['identity']
            require(identities.setdefault(identity,key) == key, 'Strawberry identity changed semantic owner')
            require(semantic_ids.setdefault(key,identity) == identity, 'Strawberry identity changed during zero-reload lifetime')


def compare_tick(tick, expected, actual, frames, sequence):
    require(len(actual) == len(expected), f'tick {tick}: Strawberry command count')
    for wanted, command in zip(expected,actual):
        for field in ('room','authoredId','sheet','sourceRectangle','color','effects','dimensions','finiteGeometry','verticesFloat32Bits'):
            require(command[field] == wanted[field], f'tick {tick}: Strawberry {field}')
        for field in ('position','origin','scale'):
            require(list(map(float32,command[field])) == list(map(float32,wanted[field])), f'tick {tick}: Strawberry {field}')
        require(float32(command['rotation']) == float32(wanted['rotation']), f'tick {tick}: Strawberry rotation')
        require(command['animation'] == 'idle' and 0 <= command['animationFrame'] < 35, 'Unsupported Strawberry animation branch')
        texture_index = sequence[command['animationFrame']]
        require(command['textureFrame'] == texture_index, 'Animation index confused with texture index')
        frame = frames[texture_index]
        require(all(command[field] == frame[field] for field in ('texture','sheet','sourceRectangle','origin')),
                'Strawberry material frame mapping mismatch')


class StrawberryCommandProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not NATIVE.exists() and 'CELESTE_STRAWBERRY_NATIVE_TRACE' not in os.environ:
            raise unittest.SkipTest('Requires private Strawberry native projection evidence')
        require(file_identity(SOURCE_TRACE) == SOURCE_IDENTITY, 'Frozen SOURCE trace changed')
        cls.frames, cls.sequence = read_catalog(CATALOG)
        cls.source = read_source(SOURCE_TRACE)
        cls.source_rosters = sample_source(SOURCE_TRACE)
        cls.native = read_native(NATIVE)

    def test_all_514_frames_140_commands_match_every_source_field(self):
        for tick in range(FRAMES):compare_tick(tick,self.source[tick],self.native['commands'][tick],self.frames,self.sequence)
        self.assertEqual(sum(map(len,self.native['commands'].values())),140)

    def test_whole_owner_order_and_actual_native_binding(self):
        validate_bindings(self.native)
        for tick in range(FRAMES):self.assertEqual(native_keys(self.native['rosters'][tick]),source_keys(tick,self.source_rosters[tick]))

    def test_frozen_load_and_first_update_edges(self):
        for tick in range(374,414):
            command = self.native['commands'][tick][0]
            self.assertEqual((command['animationFrame'],command['textureFrame'],command['position']),(0,0,[336,-144]))
        self.assertNotEqual(self.native['commands'][414][0]['position'],[336,-144])

    def test_animation_index_differs_from_texture_index(self):
        command = next(row for rows in self.native['commands'].values() for row in rows if row['animationFrame'] == 8)
        self.assertEqual(command['textureFrame'],1)
        changed = copy.deepcopy(command);changed['textureFrame'] = 8
        with self.assertRaisesRegex(ValueError,'texture index'):
            compare_tick(command['tick'],self.source[command['tick']],[changed],self.frames,self.sequence)

    def test_commands_use_actual_native_visual_state(self):
        for tick in range(374,FRAMES):
            command = self.native['commands'][tick][0]
            entities = self.native['states'][tick]['entities']
            berry = next(entity for entity in entities if entity['id'] == command['ownerIdentity'])
            self.assertEqual((berry['kind'],berry['room'],berry['authoredId']),('strawberry','2',11))
            self.assertEqual(command['animationFrame'],berry['spriteFrame'])
            if tick <= 413:self.assertEqual((berry['spriteTimer'],berry['wobble']),(0,0))

    def test_known_strawberry_and_spring_identity_swap_rejects(self):
        changed = copy.deepcopy(self.native)
        live = changed['rosters'][414]['live']
        berry = next(owner for owner in live if owner['kind'] == 'Strawberry' and owner['authoredId'] == 11)
        spring = next(owner for owner in live if owner['kind'] == 'Spring' and owner['authoredId'] == 12)
        berry_id,spring_id = berry['identity'],spring['identity']
        self.assertNotEqual(berry_id,spring_id)
        command = changed['commands'][414][0]
        self.assertEqual(command['ownerIdentity'],berry_id)
        berry['identity'],spring['identity'] = spring_id,berry_id
        changed['dispatches'][414]['order'] = [spring_id if identity == berry_id else berry_id if identity == spring_id else identity
                                               for identity in changed['dispatches'][414]['order']]
        command['ownerIdentity'] = spring_id
        self.assertEqual((berry['identity'],spring['identity']),(spring_id,berry_id))
        self.assertNotEqual(berry['identity'],spring['identity'])
        with self.assertRaisesRegex(ValueError,'lifetime'):validate_bindings(changed)

    def test_unknown_identity_rejects(self):
        changed = copy.deepcopy(self.native);changed['commands'][414][0]['ownerIdentity'] = 999999999
        with self.assertRaisesRegex(ValueError,'owner/dispatch'):validate_bindings(changed)

    def test_alias_identity_rejects(self):
        changed = copy.deepcopy(self.native);live = changed['rosters'][414]['live'];live[-1]['identity'] = live[0]['identity']
        with self.assertRaisesRegex(ValueError,'Aliased'):validate_bindings(changed)

    def test_lifetime_identity_tamper_rejects(self):
        changed = copy.deepcopy(self.native)
        owner = next(owner for owner in changed['rosters'][414]['live'] if owner['kind'] == 'Strawberry')
        previous = owner['identity'];owner['identity'] = 999999999
        changed['dispatches'][414]['order'] = [owner['identity'] if identity == previous else identity for identity in changed['dispatches'][414]['order']]
        changed['commands'][414][0]['ownerIdentity'] = owner['identity']
        with self.assertRaisesRegex(ValueError,'lifetime'):validate_bindings(changed)

    def test_geometry_clip_and_phase_negatives_parameterized(self):
        for field,value in [('position',[336,-144]),('sourceRectangle',[0,0,10,13]),('origin',[9,8]),('verticesFloat32Bits',[])]:
            with self.subTest(field=field):
                changed = copy.deepcopy(self.native['commands'][414]);changed[0][field] = value
                self.assertNotEqual(changed,self.native['commands'][414])
                with self.assertRaisesRegex(ValueError,field):compare_tick(414,self.source[414],changed,self.frames,self.sequence)


if __name__ == '__main__':unittest.main()
