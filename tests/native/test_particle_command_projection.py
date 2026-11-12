"""Frozen SOURCE oracle only; production commands must come from native birth events."""
import json
import copy
import math
import os
import struct
from pathlib import Path
import unittest

from test_native_gameplay_draw_projection import SOURCE_TRACE, SOURCE_IDENTITY, file_identity
from test_spike_command_projection import float32, require

AUDIT = Path('/home/fred/projects/celeste-vita/.audit/native-particle-command-projection-01')
NATIVE = Path(os.environ.get('CELESTE_PARTICLE_NATIVE_TRACE', AUDIT / 'proof-01/native.jsonl'))


def source_commands():
    commands = {tick: [] for tick in range(514)}
    with SOURCE_TRACE.open() as stream:
        for line in stream:
            if line.startswith('{"event":"draw-command"') and '"ParticleSystem"' in line:
                row = json.loads(line)
                require(row['owner']['entity'] == 'ParticleSystem#41' and row['owner']['depth'] == -8000,
                        'Unsupported SOURCE particle owner')
                commands[row['tick']].append(row)
    return commands


def source_first_emission_events():
    events = []
    with SOURCE_TRACE.open() as stream:
        for line in stream:
            if line.startswith('{"event":"rng"'):
                row = json.loads(line)
                if row['tick'] > 83: break
                if row['tick'] in (82,83): events.append(row)
    return events


def native_commands(path):
    commands = {tick: [] for tick in range(514)}
    with path.open() as stream:
        for line in stream:
            if line.startswith('{"event":"particle-command"'):
                row = json.loads(line)
                commands[row['tick']].append(row)
    return commands


def native_observations(path):
    rows = {'births': {}, 'rosters': {}, 'dispatches': {}, 'states': {}, 'rng': {}}
    events = {'particle-birth': 'births', 'draw-owner-roster': 'rosters',
              'draw-owner-dispatch': 'dispatches', 'rng': 'rng'}
    with path.open() as stream:
        for line in stream:
            if not line.startswith(('{"event":"particle-birth"', '{"event":"draw-owner-',
                                    '{"event":"phase"', '{"event":"rng"')):
                continue
            row = json.loads(line)
            if row['event'] == 'phase' and row['phase'] == 'after-frame':
                rows['states'][row['tick']] = row['state']
            elif row['event'] in events:
                destination = rows[events[row['event']]]
                if row['event'] in ('particle-birth', 'rng'):
                    destination.setdefault(row['tick'], []).append(row)
                else:
                    require(row['tick'] not in destination, 'Duplicate particle owner observation')
                    destination[row['tick']] = row
    return rows


def validate_bindings(commands, observations):
    births, owner_identity, next_slot = {}, None, 0
    for tick in range(514):
        live = observations['rosters'][tick]['live']
        by_id = {owner['identity']: owner for owner in live}
        require(len(by_id) == len(live), 'Aliased native owner')
        owners = [owner for owner in live if owner['kind'] == 'ParticleSystem' and owner['sortDepthBand'] == -8000]
        require(len(owners) == 1, 'Missing or duplicate Level.Particles owner')
        owner = owners[0]
        if owner_identity is None: owner_identity = owner['identity']
        require(owner['identity'] == owner_identity and owner['room'] == '', 'Particle owner lifetime changed')
        require(owner_identity in observations['dispatches'][tick]['order'], 'Particle owner not dispatched')
        for birth in observations['births'].get(tick, []):
            slot = birth['slot']
            require(slot == next_slot % 400 and birth['generation'] == next_slot // 400 + 1,
                    'Particle birth slot/generation/order')
            require(birth['type'] == 'Dust', 'Unsupported particle birth type')
            births[slot] = birth
            next_slot += 1
        previous_slot = -1
        for index, command in enumerate(commands[tick]):
            require(command['ownerIdentity'] == owner_identity and command['owner'] == 'Level.Particles'
                    and command['depth'] == -8000, 'Particle command owner binding')
            slot = command['slot']
            require(command['index'] == index and slot > previous_slot, 'Particle slot draw order')
            previous_slot = slot
            require(slot in births, 'Particle command missing birth')
            birth = births[slot]
            require(command['generation'] == birth['generation'], 'Particle command generation')
            require(float32(command['startLife']) == float32(birth['life']) and
                    float32(command['startSize']) == float32(birth['size']), 'Particle lifetime/start state')
            require(0 < command['life'] <= command['startLife'], 'Particle lifetime')
            require(command['position'] == [math.trunc(value) for value in command['visualPosition']],
                    'Particle position truncation')


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def detached_source_samples(seed):
    values = [0]*56
    value, following = 161803398-abs(seed), 1
    values[55] = value
    for index in range(1,55):
        at = 21*index % 55
        values[at] = following
        following = (value-following) % 2147483647
        value = values[at]
    for _ in range(4):
        for index in range(1,56):
            values[index] = (values[index]-values[1+(index+30) % 55]) % 2147483647
    index, partner = 0, 21
    while True:
        index, partner = index % 55+1, partner % 55+1
        value = values[index]-values[partner]
        if value == 2147483647: value -= 1
        if value < 0: value += 2147483647
        values[index] = value
        yield value * 4.656612875245797e-10


def compare_tick(tick, expected, actual):
    require(len(expected) == len(actual), f'tick {tick}: particle count {len(actual)} != {len(expected)}')
    for index, (wanted, command) in enumerate(zip(expected, actual)):
        for field in ('sheet', 'sourceRectangle', 'color', 'effects', 'dimensions', 'finiteGeometry', 'verticesFloat32Bits'):
            require(wanted[field] == command[field], f'tick {tick} particle {index}: {field}')
        for field in ('position', 'origin', 'scale'):
            require(list(map(float32, wanted[field])) == list(map(float32, command[field])),
                    f'tick {tick} particle {index}: {field}')
        require(float32(wanted['rotation']) == float32(command['rotation']), f'tick {tick} particle {index}: rotation')


class ParticleCommandProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not NATIVE.exists() and 'CELESTE_PARTICLE_NATIVE_TRACE' not in os.environ:
            raise unittest.SkipTest('Requires private native particle proof')
        require(file_identity(SOURCE_TRACE) == SOURCE_IDENTITY, 'Frozen SOURCE trace changed')
        cls.source = source_commands()
        cls.native = native_commands(NATIVE)
        cls.observations = native_observations(NATIVE)

    def test_first_four_births_tick83_match_every_field_and_geometry(self):
        self.assertEqual(len(self.source[83]), 4)
        compare_tick(83, self.source[83], self.native[83])

    def test_transition_end_clears_outgoing_particles_at_tick413(self):
        self.assertEqual(len(self.source[412]), 4)
        self.assertEqual(self.source[413], [])
        compare_tick(413, self.source[413], self.native[413])

    def test_all514_frames_1235_commands_every_field_and_xyzuv_word(self):
        for tick in range(514):
            compare_tick(tick, self.source[tick], self.native[tick])
        self.assertEqual(sum(map(len, self.native.values())), 1235)
        self.assertEqual(sum(bool(commands) for commands in self.native.values()), 245)
        self.assertEqual(max(map(len, self.native.values())), 12)

    def test_actual_persistent_owner_slot_generation_and_birth_binding(self):
        validate_bindings(self.native, self.observations)

    def test_first_emission_nine_sample_groups_and_glitch_order(self):
        self.assertEqual(self.observations['states'][82]['rng']['calls'], 83)
        events = self.observations['rng'][83]
        self.assertEqual([(event['calls'], event['operation']) for event in events],
                         [(call, 'NextDouble') for call in range(84,121)])
        self.assertEqual([birth['slot'] for birth in self.observations['births'][83]], [0,1,2,3])
        source = source_first_emission_events()
        self.assertEqual([(row['tick'], row['Calls'], row['operation']) for row in source],
                         [(82,83,'NextDouble')]+[(83,call,'NextDouble') for call in range(84,121)])
        self.assertTrue(all(row['random'] == 'TracedRandom#48' and row['phase'] == 'before-update' for row in source))

    def test_initial_birth_full_state_from_detached_seed1_arithmetic_only_in_test(self):
        samples = detached_source_samples(1)
        for _ in range(84): next(samples)
        pi, direction = f32(math.pi), f32(-f32(math.pi)/2)
        range_angle = f32(direction-f32(pi/2))
        rx, ry = abs(f32(f32(math.cos(range_angle))*4)), abs(f32(f32(math.sin(range_angle))*4))
        for birth in self.observations['births'][83]:
            sx, sy, texture, size, angle, speed, life, rotation, spin = [next(samples) for _ in range(9)]
            offset_x = f32(-rx+f32(f32(sx)*f32(rx-(-rx))))
            offset_y = f32(-ry+f32(f32(sy)*f32(ry-(-ry))))
            position = [f32(35+offset_x), f32(144+offset_y)]
            initial_size = f32(f32(f32(.7)-f32(f32(.2)*.5))+f32(f32(size)*f32(.2)))
            initial_angle = f32(f32(direction-f32(.5/2))+f32(f32(angle)*.5))
            magnitude = f32(5+f32(f32(speed)*10))
            velocity = [f32(f32(math.cos(initial_angle))*magnitude), f32(f32(math.sin(initial_angle))*magnitude)]
            initial_life = f32(f32(.3)+f32(f32(life)*f32(f32(.5)-f32(.3))))
            initial_rotation = f32(f32(f32(rotation)*pi)*2)
            self.assertEqual(birth['textureFrame'], int(texture*4))
            for field, expected in [('position',position), ('speed',velocity)]:
                self.assertEqual(list(map(float32,birth[field])), list(map(float32,expected)))
            for field, expected in [('size',initial_size), ('life',initial_life), ('rotation',initial_rotation), ('spin',f32(f32(spin)*0))]:
                self.assertEqual(float32(birth[field]), float32(expected), field)

    def test_transition_freezes_life_and_motion_but_keeps_drawing(self):
        frozen = self.native[374]
        self.assertEqual(len(frozen), 4)
        for tick in range(375,413):
            for before, after in zip(frozen, self.native[tick]):
                for field in ('life','visualPosition','speed','scale','rotation','slot','generation'):
                    self.assertEqual(before[field], after[field], (tick,field))

    def test_binding_negatives_parameterized(self):
        for mutation in ('owner','generation','order','missingbirth','lifetime','alias'):
            with self.subTest(mutation=mutation):
                commands, observations = copy.deepcopy(self.native), copy.deepcopy(self.observations)
                if mutation == 'owner': commands[83][0]['ownerIdentity'] += 1
                if mutation == 'generation': commands[83][0]['generation'] += 1
                if mutation == 'order': commands[83].reverse()
                if mutation == 'missingbirth': observations['births'][83] = []
                if mutation == 'lifetime': commands[83][0]['startLife'] += .1
                if mutation == 'alias': observations['rosters'][83]['live'].append(observations['rosters'][83]['live'][0])
                with self.assertRaises(ValueError): validate_bindings(commands, observations)

    def test_material_and_geometry_negatives_parameterized(self):
        for field, value in [('rotation',0), ('scale',[1,1]), ('color',[255,255,255,0]),
                             ('position',[32,143]), ('origin',[3,4]), ('sourceRectangle',[0,0,1,1]),
                             ('verticesFloat32Bits',[])]:
            with self.subTest(field=field):
                commands = copy.deepcopy(self.native[83]); commands[0][field] = value
                with self.assertRaisesRegex(ValueError, field): compare_tick(83,self.source[83],commands)


if __name__ == '__main__':
    unittest.main()
