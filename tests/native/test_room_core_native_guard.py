import json
import hashlib
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from check_native_oracle import ROOT, oracle_environment
from prepare_player_room_core_oracle import build, CANONICAL_EVIDENCE
from prepare_room_visuals import MEMBERS
from room_core_frontier import SDK

PRIVATE = ROOT / '.audit/native-player-death-respawn'
DECLARATIONS = (46, 49, 52, 54, 56, 59, 61, 63, 65, 66, 71, 74, 75, 77, 78, 80, 81, 83, 85, 87, 89, 91)
PRE_FIX_ORACLE = PRIVATE / '54581b570fbf67c11f6662d31364ef535dba2916/review/oracle/bin/Release/net8.0/Oracle.dll'
CELESTE_EXE = ROOT / '.audit/ilspy/inputs/Celeste.exe'
FNA_DLL = ROOT / '.audit/ilspy/inputs/FNA.dll'


@unittest.skipUnless(SDK.is_file() and (PRIVATE / 'source-synced-6b-01/provenance.json').is_file()
    and (PRIVATE / 'room-core-probe-91/provenance.json').is_file()
    and (PRIVATE / 'room-core-declarations-extra-01/provenance.json').is_file() and (ROOT / 'game/celeste-linux.zip').is_file(),
    'Pinned private RoomCore declarations or game archive unavailable')
class RoomCoreNativeGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        injection = ('LD_PRELOAD', 'LD_AUDIT', 'DOTNET_STARTUP_HOOKS', 'DOTNET_ADDITIONAL_DEPS',
            'CORECLR_ENABLE_PROFILING', 'COR_ENABLE_PROFILING')
        if any(os.environ.get(name) not in (None, '', '0') for name in injection):
            raise RuntimeError('Native guard diagnostic requires an uninjected fresh runtime process')
        cls.output = PRIVATE / ('native-guard-test-' + uuid.uuid4().hex)
        cls.lifecycle_rows = {}
        cls.contract_rows = {}
        cls.compilation = build(PRIVATE / 'source-synced-6b-01',
            PRIVATE / 'room-core-probe-42', cls.output,
            declarations_source=[PRIVATE / f'room-core-probe-{number}' for number in DECLARATIONS] + [PRIVATE / 'room-core-platform-declarations-01', PRIVATE / 'room-core-declarations-extra-01', PRIVATE / 'room-core-root-fmod-02'])

    def execute_case(self, name):
        result = subprocess.run([str(SDK), str(self.output / 'bin/Release/net8.0/Oracle.dll'), name,
            str(ROOT / '.audit/ilspy/inputs/Celeste.exe')], cwd=ROOT, env=oracle_environment(SDK), text=True, capture_output=True)
        (self.output / (name + '.stdout')).write_text(result.stdout)
        (self.output / (name + '.stderr')).write_text(result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def audit_native_abi(self, generated, name):
        report = self.output / (name + '.json')
        result = subprocess.run([str(SDK), str(self.output / 'bin/Release/net8.0/Oracle.dll'),
            'native-abi-metadata-audit', str(generated), str(report), str(CELESTE_EXE), str(FNA_DLL), '1094'],
            cwd=ROOT, env=oracle_environment(SDK), text=True, capture_output=True)
        (self.output / (name + '.log')).write_text(result.stdout + result.stderr)
        self.assertTrue(report.is_file(), result.stdout + result.stderr)
        return result, json.loads(report.read_text())

    def test_pinned_native_import_retains_original_metadata_and_no_managed_body(self):
        result = self.execute_case('native-abi-identity')
        self.assertEqual(result['status'], 'pinned-native-abi-identity-preserved')
        self.assertEqual(result['nativeAttempts'], [])

    def test_actual_pinned_fmod_import_is_stopped_by_the_assembly_local_resolver(self):
        result = self.execute_case('native-abi-negative')
        self.assertEqual(result['status'], 'expected-native-abi-guard-attempt-not-room-core-coverage')
        self.assertEqual([attempt['Library'] for attempt in result['nativeAttempts']], ['fmod_SDL'])
        self.assertEqual(result['nativeAttempts'][0]['Assembly'], result['assembly'])
        self.assertTrue(result['nativeGuardInstalled'])
        self.assertEqual(result['mappingsBefore'], [])
        self.assertEqual(result['mappingsAfter'], [])

    def test_duplicate_resolver_installation_fails_without_overwriting_the_guard(self):
        result = self.execute_case('native-abi-duplicate')
        self.assertEqual(result['status'], 'duplicate-resolver-registration-rejected')
        self.assertEqual(result['nativeAttempts'], [])

    def test_original_settings_and_platform_initializer_use_the_declared_linux_fixture(self):
        result = self.execute_case('platform-fixture-settings')
        self.assertFalse(result['settings']['isGGP'])
        self.assertEqual(result['platformReads'], [{'Profile': 'pc-linux', 'Platform': 'Linux'}])
        self.assertTrue(result['settings']['rngUnchanged'])
        self.assertTrue(result['settings']['clocksUnchanged'])
        self.assertEqual(result['nativeAttempts'], [])
        self.assertEqual(result['mappingsBefore'], [])
        self.assertEqual(result['mappingsAfter'], [])

    def test_unsupported_platform_fixture_profile_is_rejected(self):
        result = self.execute_case('platform-fixture-unsupported')
        self.assertEqual(result['status'], 'unsupported-platform-profile-rejected')
        self.assertEqual(result['platformReads'], [])
        self.assertEqual(result['nativeAttempts'], [])

    def test_manifest_separates_the_platform_fixture_from_unchanged_source(self):
        manifest = json.loads((self.output / 'source-manifest.json').read_text())
        fixture = manifest['managed_platform_fixtures'][0]
        self.assertEqual(fixture['Original']['Sha256'], '2d269f2c750dd882d9b233e66422d06b38ab9b3d11ed77aed537bfbfd78fcafe')
        self.assertEqual(fixture['OriginalBodySha256'], '87ceb960ed5b2f65cbbbd38d1ce60396c2845de54ea639fd97276d651830ecfa')
        self.assertEqual(fixture['Profile'], 'pc-linux')
        self.assertEqual(fixture['ReferencePlatform'], 'Linux')
        self.assertEqual(fixture['ProviderSha256'], hashlib.sha256((ROOT / fixture['Provider']).read_bytes()).hexdigest())
        self.assertFalse(any(entry['Name'] == 'SDL_GetPlatform' for entry in manifest['executable_members']))
        self.assertTrue(any(entry['Name'] == 'IsGGP' and entry['Kind'] == 'initializer' for entry in manifest['executable_members']))
        self.assertTrue(any(entry['Name'] == 'Settings' and entry['Kind'] == 'constructor' for entry in manifest['executable_members']))

    def test_internal_sdl_platform_import_stays_guarded(self):
        result = self.execute_case('platform-fixture-native-negative')
        self.assertEqual([attempt['Library'] for attempt in result['nativeAttempts']], ['SDL2'])
        self.assertEqual(result['platformReads'], [])

    def test_other_sdl_native_import_is_not_allowed_by_the_platform_fixture(self):
        result = self.execute_case('platform-fixture-other-native-negative')
        self.assertEqual([attempt['Library'] for attempt in result['nativeAttempts']], ['SDL2'])
        self.assertEqual(result['platformReads'], [])

    def test_source_bootstrap_passes_settings_with_separately_recorded_platform_input(self):
        trace = self.output / 'execution-prefix.jsonl'
        result = subprocess.run([str(SDK), str(self.output / 'bin/Release/net8.0/Oracle.dll'),
            'room-core-execute', str(trace)], cwd=ROOT, env=oracle_environment(SDK), text=True, capture_output=True)
        (self.output / 'execution-prefix.stdout').write_text(result.stdout)
        (self.output / 'execution-prefix.stderr').write_text(result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(trace.is_file(), result.stdout + result.stderr)
        rows = [json.loads(line) for line in trace.read_text().splitlines()]
        self.assertIn({'event': 'enter', 'member': 'Monocle.Tracker.Initialize'}, rows)
        self.assertIn({'event': 'return', 'member': 'Celeste.Settings.constructor'}, rows)
        self.assertEqual(rows[-1]['event'], 'completed')
        self.assertEqual(rows[-1]['status'], 'respawn14-normal0-one-live-tick')
        self.assertEqual(rows[-1]['nativeAttempts'], 0)
        self.assertEqual(rows[0]['nativeMappingsBefore'], [])
        self.assertEqual(rows[-1]['nativeMappingsAfter'], [])
        self.assertEqual({read['Profile'] for read in rows[-1]['platformReads']}, {'pc-linux'})
        self.assertEqual({read['Platform'] for read in rows[-1]['platformReads']}, {'Linux'})

    def test_real_level_ticks_transition_respawn14_to_normal0_and_execute_one_live_tick(self):
        trace = self.output / 'respawn-live-tick.jsonl'
        result = subprocess.run([str(SDK), str(self.output / 'bin/Release/net8.0/Oracle.dll'),
            'room-core-execute', str(trace)], cwd=ROOT, env=oracle_environment(SDK), text=True, capture_output=True)
        (self.output / 'respawn-live-tick.stderr').write_text(result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rows = [json.loads(line) for line in trace.read_text().splitlines()]
        loaded = next(row for row in rows if row['event'] == 'caller-load-level-return')
        normal = next(row for row in rows if row['event'] == 'caller-normal0')
        live = next(row for row in rows if row['event'] == 'caller-live-tick')
        self.assertEqual(loaded['state'], 14)
        self.assertEqual(normal['tick'], 35)
        self.assertEqual(live['tick'], 36)
        self.assertEqual(live['state'], 0)
        self.assertFalse(live['dead'])
        self.assertEqual(normal['state'], 0)
        self.assertGreater(normal['scale'][0], 1.0)
        self.assertLess(normal['scale'][1], 1.0)
        self.assertIsNone(live['wipe'])
        self.assertGreater(live['rawTimeActive'], normal['rawTimeActive'])
        self.assertIn({'event': 'enter', 'member': 'Celeste.Level.LoadLevel(Respawn)'}, rows)
        self.assertIn({'event': 'return', 'member': 'Celeste.Level.LoadLevel(Respawn)'}, rows)
        self.assertEqual(rows[-1]['normalTick'], normal['tick'])
        self.assertEqual(rows[-1]['liveTick'], live['tick'])

    def test_source_global_tile_bake_grounds_natural_spawn_and_retains_on_controlled_reload(self):
        pins = ROOT / '.audit/native-player-death-respawn/tile-content-pins-01'
        self.assertTrue((pins / 'Graphics/ForegroundTiles.xml').is_file())
        self.assertTrue((pins / 'Graphics/BackgroundTiles.xml').is_file())
        trace = self.output / 'ground-query.jsonl'
        result = subprocess.run([str(SDK), str(self.output / 'bin/Release/net8.0/Oracle.dll'),
            'room-core-ground-query', str(trace), str(pins)], cwd=ROOT, env=oracle_environment(SDK), text=True, capture_output=True)
        (self.output / 'ground-query.stderr').write_text(result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rows = [json.loads(line) for line in trace.read_text().splitlines()]
        content = next(row for row in rows if row['event'] == 'caller-tile-content')
        bake = next(row for row in rows if row['event'] == 'caller-global-bake')
        first = next(row for row in rows if row['event'] == 'caller-ground-normal0' and row['phase'] == 'first')
        reload_ground = next(row for row in rows if row['event'] == 'caller-ground-normal0' and row['phase'] == 'reload')
        retention = next(row for row in rows if row['event'] == 'caller-controlled-reload')
        completed = rows[-1]
        self.assertEqual(content['foregroundTilesets'], 24)
        self.assertEqual(content['backgroundTilesets'], 15)
        self.assertEqual(content['atlasMissing'], 0)
        self.assertEqual(content['overlays'], 0)
        self.assertEqual(bake['bakeCount'], 1)
        self.assertEqual(bake['mapBounds'], [-64, -64, 448, 308])
        self.assertEqual(bake['tileBounds'], [-8, -8, 56, 39])
        self.assertEqual(bake['position'], [-64, -64])
        self.assertTrue(bake['solidTagGlobal'])
        self.assertTrue(bake['bgTagGlobal'])
        self.assertEqual(bake['mapLoadSeed'], 553)
        self.assertGreater(bake['fgTileAssignments'], 0)
        self.assertGreater(bake['bgTileAssignments'], 0)
        self.assertEqual(first['position'], [19, 144])
        self.assertTrue(first['onGroundField'])
        self.assertTrue(first['onGroundQuery'])
        self.assertTrue(first['onSafeGround'])
        self.assertGreater(first['jumpGraceTimer'], 0)
        self.assertTrue(first['collisionIsSolidTiles'])
        self.assertEqual(first['gridCells'], [True, True, True, True])
        self.assertEqual(first['worldFloor'], [0, 144])
        self.assertEqual(first['solidsRow'], '4331')
        self.assertEqual(retention['solidTilesBefore'], bake['solidTiles'])
        self.assertEqual(retention['solidTilesAfter'], bake['solidTiles'])
        self.assertEqual(retention['bgTilesBefore'], bake['bgTiles'])
        self.assertEqual(retention['bgTilesAfter'], bake['bgTiles'])
        self.assertEqual(retention['solidsDataBefore'], bake['solidsDataSha'])
        self.assertEqual(retention['solidsDataAfter'], bake['solidsDataSha'])
        self.assertEqual(retention['bakeCount'], 1)
        self.assertEqual(reload_ground['position'], [19, 144])
        self.assertTrue(reload_ground['onGroundQuery'])
        self.assertTrue(reload_ground['collisionIsSolidTiles'])
        self.assertEqual(completed['status'], 'source-ground-query-and-controlled-reload-retention')
        self.assertEqual(completed['familiesClosed'], 0)
        self.assertEqual(completed['nativeAttempts'], 0)
        self.assertEqual(completed['nativeMappingsAfter'], [])

    def execute_natural_lifecycle(self, mode):
        if mode in self.lifecycle_rows:
            return self.lifecycle_rows[mode]
        trace = self.output / f'natural-lifecycle-{mode}.jsonl'
        result = subprocess.run([str(SDK), str(self.output / 'bin/Release/net8.0/Oracle.dll'),
            'room-core-natural-lifecycle', mode, str(trace), str(PRIVATE / 'tile-content-pins-01')],
            cwd=ROOT, env=oracle_environment(SDK), text=True, capture_output=True)
        (self.output / f'natural-lifecycle-{mode}.stderr').write_text(result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rows = [json.loads(line) for line in trace.read_text().splitlines()]
        self.lifecycle_rows[mode] = rows
        return rows

    def execute_source_contract(self, mode='repeat'):
        if mode in self.contract_rows:
            return self.contract_rows[mode]
        trace = self.output / f'source-contract-{mode}.jsonl'
        result = subprocess.run([str(SDK), str(self.output / 'bin/Release/net8.0/Oracle.dll'),
            'room-core-source-contract', mode, str(trace), str(PRIVATE / 'tile-content-pins-01')],
            cwd=ROOT, env=oracle_environment(SDK), text=True, capture_output=True)
        (self.output / f'source-contract-{mode}.stderr').write_text(result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rows = [json.loads(line) for line in trace.read_text().splitlines()]
        self.contract_rows[mode] = rows
        return rows

    def test_integrated_source_render_runs_live_respawn_corpse_effect_and_wipe_during_freeze(self):
        rows = self.execute_source_contract()
        renders = [row for row in rows if row['event'] == 'contract-render']
        self.assertEqual(len(renders), 365)
        self.assertEqual({row['phase'] for row in renders}, {'respawn14', 'live', 'corpse', 'death-effect'})
        self.assertTrue(all(row['rngBefore'] == row['rngAfter'] for row in renders))
        self.assertTrue(all(row['updateStateBefore'] == row['updateStateAfter'] for row in renders))
        frozen = [row for row in renders if row['freezeBeforeUpdate']]
        self.assertEqual(len(frozen), 6)
        self.assertTrue(all(row['draws'] for row in frozen))
        self.assertEqual(len([row for row in frozen if row['freezeAfterUpdate'] == 0]), 2)
        self.assertTrue(all(len(row['draws']) == 40 for row in renders if row['phase'] in ('respawn14', 'death-effect')))
        self.assertTrue(any(row['wipeVertices'] for row in renders))
        self.assertEqual(rows[-1]['completedLifecycleFamilies'], 0)
        self.assertTrue(rows[-1]['renderingExecuted'])
        self.assertEqual(rows[-1]['nativeAttempts'], 0)
        self.assertEqual(rows[-1]['nativeMappingsAfter'], [])

    def test_integrated_source_callbacks_observe_original_delegates_once_per_lifecycle(self):
        rows = self.execute_source_contract()
        callbacks = [row for row in rows if row['event'] == 'contract-callback']
        tween = [row for row in callbacks if row['callback'] == 'respawn-tween']
        reloads = [row for row in callbacks if row['callback'] == 'wipe-reload']
        self.assertEqual(len(tween), 3)
        self.assertEqual(len(reloads), 2)
        for row in tween:
            self.assertEqual(row['stateBefore'], 14)
            self.assertEqual(row['stateAfter'], 0)
            self.assertEqual(row['scaleAfter'], [1.5, .5])
            self.assertEqual(row['invocations'], 1)
            self.assertEqual(row['normalBegin'], 'NormalBegin')
            self.assertEqual(row['maxFall'], 160)
        self.assertTrue(all(row['invocations'] == 1 and row['playerBefore'] != row['playerAfter'] for row in reloads))
        additions = [row for row in rows if row['event'] == 'contract-player-added']
        self.assertEqual(len(additions), 3)
        self.assertTrue(all(row['state'] == 14 and row['startHairCalled'] and row['componentsOwned'] for row in additions))
        for row in additions:
            self.assertEqual(row['previousState'], 0)
            self.assertEqual(row['pendingAwake'], 0)
            self.assertEqual(row['awakeImplementation'], 'Monocle.Entity')
            self.assertEqual({component['entityAwake'] for component in row['components']}, {'Monocle.Component'})
            self.assertEqual({component['entityAdded'] for component in row['components']}, {'Monocle.Component', 'Monocle.StateMachine'})
        deferred = [row for row in rows if row['event'] == 'contract-corpse-commit']
        self.assertEqual(len(deferred), 2)
        self.assertTrue(all(row['pendingBefore'] == 1 and row['committedAfter'] == 1 for row in deferred))

    def test_integrated_deferred_ownership_and_end_guard_have_one_actual_death_wipe_per_corpse(self):
        rows = self.execute_source_contract()
        queued = [row for row in rows if row['event'] == 'contract-deferred-corpse']
        self.assertEqual(len(queued), 2)
        for row in queued:
            self.assertEqual(row['pendingCorpses'], 1)
            self.assertEqual(row['committedCorpses'], 0)
            self.assertIsNone(row['corpseScene'])
            self.assertTrue(row['playerStillListed'] and row['Dead'])
            self.assertEqual(row['hairOwner'], row['corpse'])
            self.assertEqual(row['spriteOwner'], row['corpse'])
            self.assertEqual(row['lightOwner'], row['corpse'])
        wipes = [row for row in rows if row['event'] == 'contract-wipe-created' and not row['WipeIn']]
        self.assertEqual(len(wipes), 2)
        self.assertEqual(len({row['wipe'] for row in wipes}), 2)
        self.assertTrue(all(row['corpseFinished'] == [True] and row['sourceCallback'] == 'Reload' for row in wipes))

    def test_integrated_source_rng_phase_is_observed_at_recording_random_leaf(self):
        rows = self.execute_source_contract()
        rng = [row for row in rows if row['event'] == 'contract-rng']
        self.assertTrue(rng)
        shake = [row for row in rng if row['operation'] == 'Next' and row['stack'][:1] == ['Celeste.Level.Update']]
        self.assertTrue(shake)
        self.assertTrue(all(len(row['hair']) == 1 and row['hair'][0]['Active'] and row['hair'][0]['entityActive'] for row in shake))
        self.assertTrue(all(row['hairHeadMatchesPostUpdate'] for row in shake))
        self.assertTrue(all(row['postUpdateHooks'] == 0 for row in shake))
        self.assertTrue(all(not row['duringRender'] and not row['freezeBeforeUpdate'] for row in rng))
        for frame in [row for row in rows if row['event'] == 'natural-frame' and row['sceneRan']]:
            frame_rng = [row for row in rng if row['tick'] == frame['tick']]
            self.assertTrue(frame_rng)
            self.assertEqual(frame_rng[0]['operation'], 'NextDouble')
            self.assertTrue(frame_rng[0]['levelUpdate'])
            self.assertIn(frame_rng[0]['stack'][0], ('Monocle.Calc.NextFloat', 'Celeste.Level.Update'))

    def test_integrated_original_sprite_geometry_matches_recorded_draw_arguments(self):
        rows = self.execute_source_contract()
        for row in rows:
            if row['event'] != 'contract-render':
                continue
            for draw in row['draws']:
                cx, cy, width, height = draw['clip']
                texture_width, texture_height = draw['textureSize']
                sine, cosine = math.sin(draw['Rotation']), math.cos(draw['Rotation'])
                for index, vertex in enumerate(draw['vertices']):
                    x = ((index & 1) * width - draw['origin'][0]) * draw['scale'][0]
                    y = ((index >> 1) * height - draw['origin'][1]) * draw['scale'][1]
                    self.assertAlmostEqual(vertex['position'][0], draw['position'][0] + cosine * x - sine * y, delta=.001)
                    self.assertAlmostEqual(vertex['position'][1], draw['position'][1] + sine * x + cosine * y, delta=.001)
                    self.assertEqual(vertex['position'][2], 0)
                    uv_index = index ^ draw['effects']
                    self.assertAlmostEqual(vertex['uv'][0], (cx + (uv_index & 1) * width) / texture_width, delta=1e-6)
                    self.assertAlmostEqual(vertex['uv'][1], (cy + (uv_index >> 1) * height) / texture_height, delta=1e-6)
                    self.assertEqual(vertex['color'], draw['color'])

    def test_integrated_respawn_and_corpse_effect_math_uses_live_ease_and_center(self):
        rows = self.execute_source_contract()
        effects = [row for row in rows if row['event'] == 'contract-render' and row['phase'] in ('respawn14', 'death-effect')]
        for row in effects:
            ease = row['introEase'] if row['phase'] == 'respawn14' else row['effectPercent']
            origin = [a + b for a, b in zip(row['center'], row['deadOffset'])] if row['phase'] == 'respawn14' else row['effectOrigin']
            scale = .5 + ease if ease < .5 else 1 - (2 * ease - 1) ** 3
            radius = (1 - (1 - ease) ** 3) * 24
            for index in range(8):
                angle = (index / 8 + ease * .25) * math.tau
                x, y = origin[0] + math.cos(angle) * radius, origin[1] + math.sin(angle) * radius
                color = row['hairColor'] if row['phase'] == 'respawn14' else row['effectColor']
                if math.floor(ease * 10) % 2:
                    color = [255] * 4
                for draw, offset in zip(row['draws'][index * 4:index * 4 + 4], ((-1, 0), (1, 0), (0, -1), (0, 1))):
                    self.assertAlmostEqual(draw['position'][0], x + offset[0], delta=.001)
                    self.assertAlmostEqual(draw['position'][1], y + offset[1], delta=.001)
                    self.assertEqual(draw['color'], [0, 0, 0, 255])
                draw = row['draws'][32 + index]
                self.assertAlmostEqual(draw['position'][0], x, delta=.001)
                self.assertAlmostEqual(draw['position'][1], y, delta=.001)
                self.assertAlmostEqual(draw['scale'][0], scale, delta=1e-5)
                self.assertEqual(draw['color'], color)

    def test_integrated_live_hair_draw_order_and_scale_follow_original_nodes(self):
        rows = self.execute_source_contract()
        live = [row for row in rows if row['event'] == 'contract-render' and row['phase'] == 'live' and row['hasHair']]
        self.assertTrue(live)
        for row in live:
            self.assertFalse(row['hairOutline'])
            count = row['hairCount']
            for index, node in enumerate(row['hairNodes'][:count]):
                scale = .25 + (1 - index / count) * .75
                expected_scale = [(row['hairFacing'] if index == 0 else scale) * abs(row['spriteScale'][0]), scale]
                for draw, offset in zip(row['draws'][index * 4:index * 4 + 4], ((-1, 0), (1, 0), (0, -1), (0, 1))):
                    for axis in range(2):
                        self.assertAlmostEqual(draw['position'][axis], node[axis] + offset[axis], delta=.001)
                        self.assertAlmostEqual(draw['scale'][axis], expected_scale[axis], delta=1e-5)
                fill = row['draws'][count * 4 + count - 1 - index]
                self.assertEqual(fill['position'], node)
                self.assertEqual(fill['color'], row['hairColor'])

    def test_integrated_wipe_geometry_is_original_six_row_math_after_gameplay_draws(self):
        rows = self.execute_source_contract()
        wipes = [row for row in rows if row['event'] == 'contract-render' and row['wipeVertices']]
        self.assertTrue(wipes)
        self.assertEqual({row['wipe']['WipeIn'] for row in wipes}, {True, False})
        for row in wipes:
            self.assertEqual(len(row['wipeVertices']), 1)
            self.assertEqual(row['wipeDraws'], [{'vertexCount': 36,
                'matrix': [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]}])
            vertices = row['wipeVertices'][0]
            self.assertEqual(len(vertices), 36)
            for index in range(6):
                delay = ((1 - index / 6) if row['wipe']['WipeIn'] else index / 6) * .3
                progress = min(1, (row['wipe']['Percent'] - delay) / .7) if row['wipe']['Percent'] > delay else 0
                if row['wipe']['WipeIn']:
                    progress = 1 - progress
                x, y, width, height = -64, -10 + index * 183.33333, 1984 * progress, 183.33333
                expected = ((x, y), (x + width, y), (x, y + height), (x + width, y), (x + width + 64, y + height), (x, y + height))
                for vertex, position in zip(vertices[index * 6:index * 6 + 6], expected):
                    if row['wipe']['WipeIn']:
                        position = (1920 - position[0], 1080 - position[1])
                    for axis in range(2):
                        self.assertAlmostEqual(vertex['position'][axis], position[axis], delta=.001)
                    self.assertEqual(vertex['color'], [0, 0, 0, 255])

    def test_integrated_checkpoint_flag_composes_the_accepted_two_cycle_contract(self):
        rows = self.execute_source_contract('checkpoint-repeat')
        reloads = [row for row in rows if row['event'] == 'natural-reload']
        self.assertEqual(len(reloads), 2)
        for index, reload in enumerate(reloads, 1):
            self.assertEqual(reload['sessionDeaths'], index)
            self.assertGreater(reload['sessionTimeAfter'], reload['sessionTimeAtDeath'])
            self.assertTrue(reload['tilesRetained'] and reload['rngRetained'] and reload['inputRetained'])
        self.assertEqual(len([row for row in rows if row['event'] == 'natural-jump']), 3)
        self.assertTrue(rows[-1]['renderingExecuted'])
        self.assertEqual(rows[-1]['completedLifecycleFamilies'], 0)

    def test_integrated_draw_does_not_allow_the_excluded_gpu_distortion_boundary(self):
        trace = self.output / 'source-contract-gpu-negative.jsonl'
        result = subprocess.run([str(SDK), str(self.output / 'bin/Release/net8.0/Oracle.dll'),
            'room-core-source-contract', 'gpu-negative', str(trace), str(PRIVATE / 'tile-content-pins-01')],
            cwd=ROOT, env=oracle_environment(SDK), text=True, capture_output=True)
        (self.output / 'source-contract-gpu-negative.stderr').write_text(result.stderr)
        self.assertNotEqual(result.returncode, 0)
        rows = [json.loads(line) for line in trace.read_text().splitlines()]
        self.assertEqual(len([row for row in rows if row['event'] == 'contract-render']), 365)
        self.assertIn('distortion boundary', rows[-1]['exception'])
        self.assertEqual(rows[-1]['member'], 'excluded-Distort.Render-after-integrated-repeat')
        self.assertEqual(rows[-1]['nativeAttempts'], [])
        self.assertEqual(rows[-1]['nativeMappingsAfter'], [])
        self.assertFalse(any(row['event'] == 'completed' for row in rows))

    def test_natural_keyboard_jump_hazard_reload_first_action_and_repeat(self):
        rows = self.execute_natural_lifecycle('repeat')
        completed = rows[-1]
        self.assertEqual(completed['status'], 'natural-input-jump-hazard-reload-repeat')
        self.assertEqual(completed['cycles'], 2)
        self.assertEqual(completed['reloads'], 2)
        self.assertEqual(completed['bakeCount'], 1)
        self.assertEqual(completed['completedLifecycleFamilies'], 0)
        self.assertEqual(completed['nativeAttempts'], 0)
        self.assertEqual(completed['nativeMappingsAfter'], [])
        jumps = [row for row in rows if row['event'] == 'natural-jump']
        self.assertEqual(len(jumps), 3)
        for jump in jumps:
            self.assertTrue(jump['groundBefore'])
            self.assertGreater(jump['graceBefore'], 0)
            self.assertGreater(jump['bufferBeforeScene'], 0)
            self.assertEqual(jump['bufferAfterScene'], 0)
            self.assertLess(jump['speed'][1], 0)
            self.assertGreater(jump['totalJumps'], 0)
        deaths = [row for row in rows if row['event'] == 'natural-death']
        self.assertEqual(len(deaths), 2)
        self.assertTrue(all(row['pendingCorpses'] == 1 and row['committedCorpses'] == 0 for row in deaths))
        reloads = [row for row in rows if row['event'] == 'natural-reload']
        self.assertEqual(len(reloads), 2)
        for index, reload in enumerate(reloads, 1):
            self.assertEqual(reload['state'], 14)
            self.assertTrue(reload['corpseRemoved'])
            self.assertTrue(reload['tilesRetained'])
            self.assertTrue(reload['rngRetained'])
            self.assertEqual(reload['sessionDeaths'], 0)
            self.assertEqual(reload['roomDeaths'], index)
            self.assertEqual(reload['saveDeaths'], index)

    def test_natural_death_freeze_buffers_hold_and_release_before_first_resumed_jump(self):
        rows = self.execute_natural_lifecycle('repeat')
        frames = [row for row in rows if row['event'] == 'natural-frame']
        frozen = [row for row in frames if row['freezeBefore']]
        self.assertEqual(len(frozen), 6)
        for frame in frozen:
            self.assertFalse(frame['sceneRan'])
            self.assertEqual(frame['timeBefore'], frame['timeActive'])
            self.assertEqual(frame['rngBefore'], frame['rngCalls'])
            self.assertEqual(frame['presentationBefore'], frame['presentationAfter'])
        first_crossing = frozen[2]
        self.assertTrue(first_crossing['jumpCheck'])
        self.assertTrue(first_crossing['jumpPressedBeforeScene'])
        self.assertFalse(first_crossing['jumpReleased'])
        self.assertEqual(first_crossing['freezeAfter'], 0)
        held = next(row for row in rows if row['event'] == 'natural-held-after-reload')
        self.assertTrue(held['check'])
        self.assertFalse(held['pressed'])
        self.assertLess(held['buffer'], 0)
        self.assertTrue(held['grounded'])
        second_crossing = frozen[5]
        self.assertFalse(second_crossing['jumpCheck'])
        self.assertFalse(second_crossing['jumpPressedBeforeScene'])
        self.assertTrue(second_crossing['jumpReleased'])
        self.assertEqual(second_crossing['bufferBeforeScene'], 0)
        buffered = next(row for row in rows if row['event'] == 'natural-buffer-before-normal')
        self.assertEqual(buffered['stateBefore'], 14)
        self.assertEqual(buffered['stateAfter'], 0)
        self.assertGreater(buffered['buffer'], 0)
        jumps = [row for row in rows if row['event'] == 'natural-jump']
        self.assertEqual(jumps[-1]['tick'], buffered['tick'] + 1)

    def test_natural_checkpoint_repeat_retains_session_time_and_deaths(self):
        rows = self.execute_natural_lifecycle('checkpoint-repeat')
        reloads = [row for row in rows if row['event'] == 'natural-reload']
        self.assertEqual(len(reloads), 2)
        for index, reload in enumerate(reloads, 1):
            self.assertEqual(reload['sessionDeaths'], index)
            self.assertTrue(reload['hitCheckpoint'])
            self.assertGreater(reload['sessionTimeAfter'], reload['sessionTimeAtDeath'])
        self.assertEqual(rows[-1]['cycles'], 2)
        self.assertEqual(rows[-1]['nativeAttempts'], 0)

    def test_natural_corpse_ownership_wipe_callback_and_reconstruction_are_source_owned(self):
        rows = self.execute_natural_lifecycle('repeat')
        deaths = [row for row in rows if row['event'] == 'natural-death']
        for death in deaths:
            self.assertTrue(death['spriteTransferred'])
            self.assertTrue(death['hairTransferred'])
            self.assertTrue(death['lightTransferred'])
            self.assertEqual(death['deathDirection'], [0, -1])
        wipes = [row for row in rows if row['event'] == 'natural-death-wipe']
        self.assertEqual(len(wipes), 2)
        for wipe in wipes:
            self.assertEqual(wipe['wipe']['onCompleteMethod'], 'Reload')
            self.assertEqual(wipe['wipe']['onCompleteTarget'], 'level')
            self.assertFalse(wipe['wipe']['wipeIn'])
        effects = [row for row in rows if row['event'] == 'natural-death-effect']
        self.assertEqual(len(effects), 2)
        self.assertTrue(all(abs(row['duration'] - .834) < 1e-6 for row in effects))
        reloads = [row for row in rows if row['event'] == 'natural-reload']
        for reload in reloads:
            self.assertTrue(reload['hairReconstructed'])
            self.assertTrue(reload['spriteReconstructed'])
            self.assertTrue(reload['inputRetained'])
            self.assertTrue(reload['gridRetained'])
            self.assertEqual(reload['rawHazards'], 5)

    def test_grounded_jump_promotes_only_original_consume_buffer_and_dust_members(self):
        manifest = json.loads((self.output / 'source-manifest.json').read_text())
        for filename, name in (('Monocle.VirtualButton.cs', 'ConsumeBuffer'), ('Celeste.Dust.cs', 'Burst'),
                ('Celeste.Dust.cs', 'BurstFG')):
            entries = [entry for entry in manifest['executable_members']
                if entry['File'].endswith(filename) and entry['Name'] == name]
            self.assertEqual(len(entries), 1)
            entry = entries[0]
            self.assertEqual(hashlib.sha256(Path(entry['File']).read_bytes()[entry['Start']:entry['End']]).hexdigest(), entry['Sha256'])
        self.assertFalse(any(entry['Name'] == 'Load' and entry['File'].endswith('Celeste.ParticleTypes.cs')
            for entry in manifest['executable_members']))
        self.assertEqual(manifest['particle_bootstrap_prefix']['lines_inclusive'], [22, 47])

    def test_natural_live_render_outside_the_declared_recording_scope_stays_fail_closed(self):
        trace = self.output / 'natural-render-boundary.jsonl'
        result = subprocess.run([str(SDK), str(self.output / 'bin/Release/net8.0/Oracle.dll'),
            'room-core-natural-lifecycle', 'render-boundary', str(trace), str(PRIVATE / 'tile-content-pins-01')],
            cwd=ROOT, env=oracle_environment(SDK), text=True, capture_output=True)
        (self.output / 'natural-render-boundary.stderr').write_text(result.stderr)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(trace.is_file(), result.stderr)
        rows = [json.loads(line) for line in trace.read_text().splitlines()]
        self.assertEqual(len([row for row in rows if row['event'] == 'natural-reload']), 2)
        boundary = rows[-1]
        self.assertEqual(boundary['event'], 'boundary')
        self.assertEqual(boundary['member'], 'original-Player.Render-after-natural-repeat')
        self.assertIn('UnsupportedClosure', boundary['exception'])
        self.assertIn('Monocle.Draw.cs:SpriteBatch', boundary['exception'])
        self.assertEqual(boundary['nativeAttempts'], [])
        self.assertEqual(boundary['nativeMappingsAfter'], [])
        self.assertFalse(any(row['event'] == 'completed' for row in rows))

    def test_natural_lifecycle_uses_only_raw_keys_not_player_or_resolved_input_writes(self):
        path = ROOT / 'tests/native/oracle/death/RoomCoreLifecycle.cs'
        self.assertTrue(path.is_file(), 'Natural-input lifecycle driver is missing')
        caller = path.read_text()
        self.assertNotRegex(caller, r'\.(Position|Speed|PositionRemainder|State|Deaths|DeathsInCurrentLevel|TotalDeaths|Value|PreviousValue)\s*=[^=]')
        self.assertNotRegex(caller, r'(jumpGraceTimer|onGround|bufferCounter)\s*=')
        for forbidden in ('.Jump(', '.Die(', '.Respawn(', '.Reload(', 'OnCollide(', 'ConsumeBuffer(',
                'Keyboard.GetState(', 'MInput.Update(', 'UpdateVirtualInputs('):
            self.assertNotIn(forbidden, caller)
        self.assertIn('Input.MoveX.Update()', caller)
        self.assertIn('Input.Jump.Update()', caller)
        self.assertNotIn('Engine.FreezeTimer =', caller)
        self.assertNotIn('.SetValue(', caller)
        self.assertNotIn('.BeforeUpdate(', caller)
        self.assertLess(caller.index('SetEngineTick(1f / 60f)'), caller.index('MInput.Keyboard.PreviousState ='))
        self.assertLess(caller.index('Input.Jump.Update()'), caller.index('driver.Tick()'))

    def test_lifecycle_matrix_composes_accepted_provenance_without_self_closing_families(self):
        manifest = json.loads((self.output / 'source-manifest.json').read_text())
        matrix = manifest['lifecycle_contract_matrix']
        self.assertEqual(set(matrix), {'up', 'left', 'ordering', 'corpse', 'boundaries', 'freeze-input', 'reload', 'cycles'})
        for family in matrix.values():
            self.assertFalse(family['closed'])
            self.assertTrue(family['eligibleForCoordinatorReview'])
            self.assertIn('Coordinator acceptance', family['remaining'])
            self.assertTrue(family['acceptedEvidence'])
            for evidence in family['acceptedEvidence']:
                receipt = Path(evidence['archive'] + '-archive.json')
                self.assertEqual(hashlib.sha256(receipt.read_bytes()).hexdigest(), evidence['receiptSha256'])
                self.assertRegex(evidence['sourceSnapshot'], r'^[0-9a-f]{64}$')
                self.assertTrue(evidence['scenarios'])
        self.assertIn('seeded', matrix['left']['boundedContract'])
        self.assertEqual(matrix['left']['newScenarios'], [])
        self.assertIn('NOT a second callback', matrix['ordering']['boundedContract'])
        self.assertTrue(any(evidence['sourceSnapshot'].startswith('24dd0113') for evidence in matrix['cycles']['acceptedEvidence']))

    def test_bounded_phase_source_witnesses_are_pinned_and_present_unchanged(self):
        manifest = json.loads((self.output / 'source-manifest.json').read_text())
        generated = (self.output / 'Extracted.cs').read_bytes()
        for entry in manifest['bounded_phase_sources']:
            data = Path(entry['source_path']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry['source_sha256'])
            lines = data.splitlines(keepends=True)
            for (first, last), expected in zip(entry['lines_inclusive'], entry['blocks_sha256']):
                block = b''.join(lines[first - 1:last])
                self.assertEqual(hashlib.sha256(block).hexdigest(), expected)
                self.assertIn(block.rstrip(b'\r\n'), generated)
        contract = manifest['bounded_phase_contract']
        self.assertIn('!Dead', contract['repeatedDie'])
        self.assertIn('not a count of unobserved End calls', contract['exactlyOnce'])

    def test_integrated_contract_preserves_all_prior_executable_members_and_native_abi(self):
        manifest = json.loads((self.output / 'source-manifest.json').read_text())
        accepted_path = Path(CANONICAL_EVIDENCE) / 'functional-lifecycle-reviewed-24dd0113/producer/build/source-manifest.json'
        accepted = json.loads(accepted_path.read_text())
        key = lambda entry: (entry['File'], entry['Start'], entry['End'], entry['Sha256'])
        previous = {key(entry) for entry in accepted['executable_members']}
        current = {key(entry) for entry in manifest['executable_members']}
        self.assertTrue(previous <= current)
        promoted = [entry for entry in manifest['executable_members'] if key(entry) not in previous]
        self.assertEqual({(Path(entry['File']).name, entry['Name']) for entry in promoted},
            {('Monocle.Engine.cs', 'Graphics'), ('Microsoft.Xna.Framework.GraphicsDeviceManager.cs', 'GraphicsDevice')})
        self.assertEqual(len(manifest['recording_render_leaves']['original_declarations']), 2)
        for entry in manifest['recording_render_leaves']['original_declarations']:
            data = Path(entry['File']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry['SourceSha256'])
            self.assertEqual(hashlib.sha256(data[entry['Start']:entry['End']]).hexdigest(), entry['Sha256'])
        self.assertEqual(manifest['native_abi_identity']['generatedNativeImports'], 1094)
        self.assertTrue(manifest['native_abi_identity']['allGeneratedNativeBodiesNull'])

    def test_source_render_order_is_pinned_reference_not_a_full_engine_or_gpu_execution_claim(self):
        manifest = json.loads((self.output / 'source-manifest.json').read_text())
        self.assertIn('REFERENCE-ONLY', manifest['bounded_render_order_contract'])
        for entry in manifest['bounded_render_order_sources']:
            data = Path(entry['source_path']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry['source_sha256'])
            lines = data.splitlines(keepends=True)
            for (first, last), expected in zip(entry['lines_inclusive'], entry['blocks_sha256']):
                self.assertEqual(hashlib.sha256(b''.join(lines[first - 1:last])).hexdigest(), expected)
        executable = manifest['executable_members']
        self.assertFalse(any(Path(entry['File']).name == 'Monocle.Engine.cs' and entry['Name'] in ('Draw', 'RenderCore') for entry in executable))
        self.assertFalse(any(Path(entry['File']).name == 'Celeste.Level.cs' and entry['Name'] == 'Render' for entry in executable))

    def test_integrated_probe_never_writes_player_pose_state_or_resolved_input(self):
        caller = (ROOT / 'tests/native/oracle/death/RoomCoreContract.cs').read_text()
        self.assertNotRegex(caller, r'\.(Position|Speed|PositionRemainder|State|Value|PreviousValue)\s*=[^=]')
        for forbidden in ('.Die(', '.Jump(', '.Respawn(', '.Reload(', '.AfterUpdate(', '.EntityAdded(', '.Awake('):
            self.assertNotIn(forbidden, caller)
        self.assertEqual(caller.count('callback(value);'), 1)
        self.assertEqual(caller.count('callback();'), 1)

    def test_natural_repeat_retains_global_clocks_rng_and_at_most_one_corpse(self):
        rows = self.execute_natural_lifecycle('repeat')
        frames = [row for row in rows if row['event'] == 'natural-frame']
        self.assertEqual([row['frameCounter'] for row in frames], list(range(1, len(frames) + 1)))
        self.assertEqual([row['tick'] for row in frames], list(range(len(frames))))
        self.assertTrue(all(a['rngCalls'] <= b['rngCalls'] for a, b in zip(frames, frames[1:])))
        self.assertTrue(all(a['timeActive'] <= b['timeActive'] for a, b in zip(frames, frames[1:])))
        self.assertTrue(all(row['pendingCorpses'] + row['committedCorpses'] <= 1 for row in frames))
        self.assertTrue(all(row['solidsDataRetained'] for row in rows if row['event'] == 'natural-reload'))
        self.assertFalse(any(row['event'] == 'boundary' for row in rows))
        self.assertEqual((self.output / 'natural-lifecycle-repeat.stderr').read_text(), '')

    def test_compiled_native_abi_identity_reproduces_red_then_green(self):
        if not PRE_FIX_ORACLE.is_file():
            self.skipTest('Pinned pre-fix Oracle assembly unavailable')
        red_result, red = self.audit_native_abi(PRE_FIX_ORACLE, 'native-abi-red-545')
        self.assertNotEqual(red_result.returncode, 0)
        self.assertEqual(red['generatedNativeImports'], 1094)
        self.assertEqual(red['originalNativeImports'], 1349)
        self.assertTrue(red['allGeneratedNativeBodiesNull'])
        self.assertEqual(len(red['failures']), 3)
        self.assertEqual({failure['key'] for failure in red['failures']}, {
            'FMOD.System::FMOD_System_SetAdvancedSettings:0:0:2:FMOD.RESULT(IntPtr,FMOD.Studio.ADVANCEDSETTINGS&)',
            'FMOD.System::FMOD_System_GetAdvancedSettings:0:0:2:FMOD.RESULT(IntPtr,FMOD.Studio.ADVANCEDSETTINGS&)',
            'FMOD.System::FMOD_System_SetCallback:0:0:3:FMOD.RESULT(IntPtr,FMOD.Studio.SYSTEM_CALLBACK,FMOD.Studio.SYSTEM_CALLBACK_TYPE)'})
        self.assertEqual({contract['name'] for contract in red['rootContracts'] if not contract['ok']}, {
            'FMOD.ADVANCEDSETTINGS', 'FMOD.SYSTEM_CALLBACK', 'FMOD.SYSTEM_CALLBACK_TYPE', 'FMOD.DSP_RESAMPLER'})

        green_result, green = self.audit_native_abi(self.output / 'bin/Release/net8.0/Oracle.dll', 'native-abi-green')
        self.assertEqual(green_result.returncode, 0, green_result.stdout + green_result.stderr)
        self.assertEqual(green['generatedNativeImports'], 1094)
        self.assertEqual(green['originalNativeImports'], 1349)
        self.assertEqual(green['failures'], [])
        self.assertTrue(green['allGeneratedNativeBodiesNull'])
        self.assertTrue(all(contract['ok'] for contract in green['rootContracts']))
        self.assertEqual({contract['name'] for contract in green['rootContracts']}, {
            'FMOD.ADVANCEDSETTINGS', 'FMOD.SYSTEM_CALLBACK', 'FMOD.SYSTEM_CALLBACK_TYPE', 'FMOD.DSP_RESAMPLER'})
        self.assertEqual(set(green['expectedRootTypes']), {
            'FMOD.ADVANCEDSETTINGS', 'FMOD.SYSTEM_CALLBACK', 'FMOD.SYSTEM_CALLBACK_TYPE'})
        self.assertEqual(len(green['nativeCalls']), 3)
        self.assertEqual(len(green['expectedRootTypes']) + len(green['nativeCalls']), 6)
        for call in green['nativeCallEvidence']:
            self.assertEqual(len(call['generated']), 1)
            self.assertNotIn('FMOD.Studio', call['generated'][0])
        self.assertEqual(green['originals'][0]['sha256'], MEMBERS['Celeste.exe'])
        self.assertEqual(green['originals'][1]['sha256'], MEMBERS['FNA.dll'])
        manifest = json.loads((self.output / 'source-manifest.json').read_text())
        self.assertEqual(manifest['native_abi_identity']['failures'], 0)
        self.assertTrue(all(contract['ok'] for contract in manifest['native_abi_identity']['rootContracts']))
        self.assertEqual({entry['file'] for entry in manifest['native_abi_root_contracts']}, {
            'FMOD.ADVANCEDSETTINGS.cs', 'FMOD.SYSTEM_CALLBACK.cs', 'FMOD.SYSTEM_CALLBACK_TYPE.cs', 'FMOD.DSP_RESAMPLER.cs'})

    def test_manifest_records_audio_boundary_and_no_lifecycle_family_closure(self):
        manifest = json.loads((self.output / 'source-manifest.json').read_text())
        self.assertIn('Declared inert event-description cache', manifest['audio_boundary'])
        result = json.loads((self.output / 'probe-result.json').read_text())
        self.assertEqual(result['status'], 'compiled-bounded-respawn-and-death-roundtrip-not-family-closure')
        self.assertIn('zero of eight families closed', result['claim'])
        self.assertTrue(any(entry['Name'] == 'EventnameByHandle' and entry['Kind'] == 'method'
            for entry in manifest['executable_members']))
        self.assertTrue(any(entry['Name'] == 'Added' and entry['Kind'] == 'method'
            and entry['File'].endswith('Celeste.Spikes.cs') for entry in manifest['executable_members']))
        self.assertEqual({entry['file'] for entry in manifest['death_lifecycle_sources']},
            {'Celeste.PlayerDeadBody.cs', 'Celeste.DeathEffect.cs', 'Celeste.ScreenWipe.cs', 'Celeste.AngledWipe.cs'})
        self.assertEqual(manifest['recording_gpu_boundary']['type'], 'Celeste.Distort')
        self.assertEqual(manifest['gui_meta_sha256'], '884ea39e604e34e3a45b005d164a5249de9a985e58fde7ef730193c47363525b')

    def test_original_die_corpse_wipe_reload_second_respawn_and_one_resumed_tick(self):
        trace = self.output / 'death-respawn-roundtrip.jsonl'
        result = subprocess.run([str(SDK), str(self.output / 'bin/Release/net8.0/Oracle.dll'),
            'room-core-death-respawn', str(trace)], cwd=ROOT, env=oracle_environment(SDK), text=True, capture_output=True)
        (self.output / 'death-respawn.stderr').write_text(result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rows = [json.loads(line) for line in trace.read_text().splitlines()]
        die = next(row for row in rows if row['event'] == 'caller-probe-die')
        bounce = next(row for row in rows if row['event'] == 'caller-corpse-bounce')
        effect = next(row for row in rows if row['event'] == 'caller-corpse-death-effect')
        wipe = next(row for row in rows if row['event'] == 'caller-death-wipe')
        reload = next(row for row in rows if row['event'] == 'caller-reload-second-load')
        normal = next(row for row in rows if row['event'] == 'caller-second-normal0')
        live = next(row for row in rows if row['event'] == 'caller-resumed-live-tick')
        self.assertTrue(die['dead'])
        self.assertFalse(die['collidable'])
        self.assertTrue(die['locked'])
        self.assertTrue(die['corpse'].startswith('PlayerDeadBody'))
        self.assertEqual(die['sessionDeaths'], 1)
        self.assertEqual(die['saveDeaths'], 1)
        self.assertEqual(bounce['animation'], 'deadup')
        self.assertEqual(bounce['tween']['Percent'], 0.0)
        self.assertAlmostEqual(effect['effect']['Duration'], 0.834, places=6)
        self.assertTrue(wipe['wipe']['type'].startswith('AngledWipe'))
        self.assertFalse(wipe['wipe']['wipeIn'])
        self.assertEqual(wipe['wipe']['onCompleteTarget'], 'level')
        self.assertEqual(wipe['wipe']['onCompleteMethod'], 'Reload')
        self.assertNotEqual(reload['previousPlayer'], reload['player'])
        self.assertEqual(reload['state'], 14)
        self.assertEqual(reload['lastIntroType'], 'Respawn')
        self.assertTrue(reload['corpseRemoved'])
        self.assertFalse(reload['corpseInScene'])
        self.assertEqual(reload['position'], [19, 144])
        self.assertTrue(reload['wipe']['wipeIn'])
        self.assertEqual(normal['state'], 0)
        self.assertEqual(normal['position'], [19, 144])
        self.assertEqual(live['state'], 0)
        self.assertFalse(live['dead'])
        self.assertEqual(live['speed'], [0, 15.000001])
        self.assertFalse(live['inputSampled'])
        frozen = [row for row in rows if row['event'] == 'driver-tick' and row['freezeBefore']]
        self.assertEqual(len(frozen), 3)
        self.assertTrue(all(not row['sceneRan'] for row in frozen))
        self.assertEqual(frozen[-1]['freezeAfter'], 0.0)
        resumed = next(row for row in rows if row['event'] == 'driver-tick' and row['tick'] == frozen[-1]['tick'] + 1)
        self.assertTrue(resumed['sceneRan'])
        completed = rows[-1]
        self.assertEqual(completed['status'], 'original-die-corpse-wipe-reload-second-respawn14-normal0-one-resumed-tick')
        self.assertEqual(completed['corpseCreated'], 1)
        self.assertEqual(completed['deathWipes'], 1)
        self.assertEqual(completed['reloads'], 1)
        self.assertEqual(completed['sourceLoadLevelCalls'], 2)
        self.assertEqual(completed['resumedNormalUpdates'], 1)
        self.assertTrue(completed['sameLevelAfterResume'])
        self.assertEqual(completed['nativeAttempts'], 0)
        self.assertEqual(completed['nativeMappingsAfter'], [])
        self.assertEqual(completed['completedLifecycleFamilies'], 0)
        self.assertFalse(completed['hazardOrderingDirectionalCollisionDeathParity'])

    def execute_up_spike(self, scenario):
        trace = self.output / f'up-spike-{scenario}.jsonl'
        result = subprocess.run([str(SDK), str(self.output / 'bin/Release/net8.0/Oracle.dll'),
            'room-core-up-spike', scenario, str(trace)], cwd=ROOT, env=oracle_environment(SDK),
            text=True, capture_output=True)
        (self.output / f'up-spike-{scenario}.stdout').write_text(result.stdout)
        (self.output / f'up-spike-{scenario}.stderr').write_text(result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return [json.loads(line) for line in trace.read_text().splitlines()]

    def execute_input_right(self, name='input-right'):
        trace = self.output / f'{name}.jsonl'
        result = subprocess.run([str(SDK), str(self.output / 'bin/Release/net8.0/Oracle.dll'),
            'room-core-input-right', str(trace)], cwd=ROOT, env=oracle_environment(SDK),
            text=True, capture_output=True)
        (self.output / f'{name}.stdout').write_text(result.stdout)
        (self.output / f'{name}.stderr').write_text(result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return [json.loads(line) for line in trace.read_text().splitlines()]

    def test_static_up_spike_original_oncollide_whole_block_is_executable(self):
        manifest = json.loads((self.output / 'source-manifest.json').read_text())
        source = next(entry for entry in manifest['executable_members']
            if entry['File'].endswith('Celeste.Spikes.cs') and entry['Name'] == 'OnCollide')
        self.assertNotIn(source, manifest['declaration_contracts'])
        original = Path(source['File']).read_bytes()
        block = original[source['Start']:source['End']]
        self.assertEqual(hashlib.sha256(block).hexdigest(), source['Sha256'])
        self.assertIn(b'player.Die(new Vector2(0f, -1f))', block)
        self.assertIn(b'case Directions.Up:', block)

    def test_up_spike_caller_does_not_invoke_die_or_oncollide(self):
        text = (ROOT / 'tests/native/oracle/death/RoomCoreExecution.cs').read_text()
        start = text.index('public static void RunStaticSpike')
        end = text.index('static bool Tick', start)
        caller = text[start:end]
        self.assertNotIn('.Die(', caller)
        self.assertNotIn('OnCollide(', caller)

    def test_static_up_spike_lethal_collision_uses_original_die_and_existing_lifecycle(self):
        rows = self.execute_up_spike('lethal')
        self.assertFalse(any(row['event'] == 'boundary' for row in rows))
        self.assertNotIn('UnsupportedClosure', (self.output / 'up-spike-lethal.stderr').read_text())
        setup = next(row for row in rows if row['event'] == 'caller-up-spike-setup')
        collision = next(row for row in rows if row['event'] == 'caller-up-spike-collision')
        self.assertEqual(setup['scenario'], 'lethal')
        self.assertEqual(setup['spikeDirection'], 'Up')
        self.assertFalse(setup['inputSampled'])
        self.assertTrue(collision['dead'])
        self.assertFalse(collision['collidable'])
        self.assertTrue(collision['locked'])
        self.assertEqual(collision['deathDirection'], [0, -1])
        self.assertTrue(collision['corpse'].startswith('PlayerDeadBody'))
        activated = next(row for row in rows if row['event'] == 'caller-up-spike-corpse')
        self.assertEqual(activated['corpse'], collision['corpse'])
        self.assertEqual(collision['sessionDeaths'], setup['sessionDeaths'] + 1)
        self.assertEqual(collision['saveDeaths'], setup['saveDeaths'] + 1)
        bounce = next(row for row in rows if row['event'] == 'caller-corpse-bounce')
        self.assertEqual(bounce['animation'], 'deadup')
        self.assertAlmostEqual(next(row for row in rows if row['event'] == 'caller-corpse-death-effect')['effect']['Duration'], 0.834, places=6)
        wipe = next(row for row in rows if row['event'] == 'caller-death-wipe')
        self.assertFalse(wipe['wipe']['wipeIn'])
        self.assertEqual(wipe['wipe']['onCompleteMethod'], 'Reload')
        reload = next(row for row in rows if row['event'] == 'caller-reload-second-load')
        self.assertEqual(reload['state'], 14)
        self.assertNotEqual(reload['previousPlayer'], reload['player'])
        second = next(row for row in rows if row['event'] == 'caller-second-normal0')
        self.assertEqual(second['state'], 0)
        live = next(row for row in rows if row['event'] == 'caller-resumed-live-tick')
        self.assertEqual(live['state'], 0)
        self.assertFalse(live['dead'])
        completed = rows[-1]
        self.assertEqual(completed['status'], 'up-spike-lethal-source-collision-death-respawn14-normal0-one-live-tick')
        self.assertEqual(completed['nativeAttempts'], 0)
        self.assertEqual(completed['completedLifecycleFamilies'], 0)
        self.assertFalse(completed['hazardOrderingDirectionalCollisionDeathParity'])

    def test_static_up_spike_nonlethal_collision_stays_alive_without_lifecycle(self):
        rows = self.execute_up_spike('nonlethal')
        self.assertFalse(any(row['event'] == 'boundary' for row in rows))
        self.assertNotIn('UnsupportedClosure', (self.output / 'up-spike-nonlethal.stderr').read_text())
        setup = next(row for row in rows if row['event'] == 'caller-up-spike-setup')
        collision = next(row for row in rows if row['event'] == 'caller-up-spike-collision')
        followup = next(row for row in rows if row['event'] == 'caller-up-spike-followup')
        self.assertEqual(setup['scenario'], 'nonlethal')
        self.assertEqual(setup['spikeDirection'], 'Up')
        self.assertFalse(setup['inputSampled'])
        self.assertFalse(collision['dead'])
        self.assertIsNone(collision['corpse'])
        self.assertIsNone(collision['wipe'])
        self.assertEqual(collision['sessionDeaths'], setup['sessionDeaths'])
        self.assertEqual(collision['saveDeaths'], setup['saveDeaths'])
        self.assertFalse(followup['dead'])
        self.assertIsNone(followup['corpse'])
        self.assertIsNone(followup['wipe'])
        self.assertFalse(any(row['event'] in ('caller-corpse-bounce', 'caller-death-wipe',
            'caller-reload-second-load', 'caller-second-normal0') for row in rows))
        completed = rows[-1]
        self.assertEqual(completed['status'], 'up-spike-nonlethal-source-collision-alive-no-lifecycle')
        self.assertEqual(completed['nativeAttempts'], 0)
        self.assertEqual(completed['completedLifecycleFamilies'], 0)
        self.assertFalse(completed['hazardOrderingDirectionalCollisionDeathParity'])

    def test_static_up_spike_geometry_false_with_velocity_true_stays_alive(self):
        rows = self.execute_up_spike('geometry-nonlethal')
        self.assertFalse(any(row['event'] == 'boundary' for row in rows))
        self.assertNotIn('UnsupportedClosure', (self.output / 'up-spike-geometry-nonlethal.stderr').read_text())
        setup = next(row for row in rows if row['event'] == 'caller-up-spike-setup')
        ticks = [row for row in rows if row['event'] == 'caller-up-spike-geometry-tick']
        self.assertEqual(setup['scenario'], 'geometry-nonlethal')
        self.assertEqual(setup['spikeDirection'], 'Up')
        self.assertFalse(setup['inputSampled'])
        self.assertGreaterEqual(len(ticks), 4)
        cells = [row for row in ticks if row['overlap'] and row['velocityTrue'] and not row['geometryTrue']]
        self.assertTrue(cells)
        self.assertTrue(any(row['speedY'] > 0 for row in cells))
        self.assertTrue(any(row['speedY'] != setup['playerSpeed'][1] for row in cells))
        for row in cells:
            self.assertGreater(row['hurtboxBounds'][3], row['spikeBounds'][3])
            self.assertGreaterEqual(row['speedY'], 0)
            self.assertFalse(row['dead'])
            self.assertIsNone(row['corpse'])
            self.assertIsNone(row['wipe'])
            self.assertEqual(row['sessionDeaths'], setup['sessionDeaths'])
            self.assertEqual(row['saveDeaths'], setup['saveDeaths'])
        self.assertFalse(any(row['event'] in ('caller-corpse-bounce', 'caller-death-wipe',
            'caller-reload-second-load', 'caller-second-normal0') for row in rows))
        completed = rows[-1]
        self.assertEqual(completed['status'], 'up-spike-geometry-nonlethal-source-collision-alive-no-lifecycle')
        self.assertGreaterEqual(completed['observedCells'], 1)
        self.assertEqual(completed['sessionDeaths'], setup['sessionDeaths'])
        self.assertEqual(completed['saveDeaths'], setup['saveDeaths'])
        self.assertEqual(completed['corpseCreated'], 0)
        self.assertEqual(completed['deathWipes'], 0)
        self.assertEqual(completed['reloads'], 0)
        self.assertIn('in-air pose', completed['profileBoundary'])
        self.assertEqual(completed['nativeAttempts'], 0)
        self.assertEqual(completed['nativeMappingsAfter'], [])
        self.assertEqual(completed['completedLifecycleFamilies'], 0)
        self.assertFalse(completed['hazardOrderingDirectionalCollisionDeathParity'])

    def test_static_up_spike_zero_speed_collision_uses_original_die_and_lifecycle(self):
        rows = self.execute_up_spike('zero-lethal')
        self.assertFalse(any(row['event'] == 'boundary' for row in rows))
        self.assertNotIn('UnsupportedClosure', (self.output / 'up-spike-zero-lethal.stderr').read_text())
        setup = next(row for row in rows if row['event'] == 'caller-up-spike-setup')
        gravity_step = next(row for row in rows if row['event'] == 'caller-up-spike-zero-gravity-step')
        calibration = next(row for row in rows if row['event'] == 'caller-up-spike-zero-calibration')
        zero = next(row for row in rows if row['event'] == 'caller-up-spike-zero-setup')
        collision = next(row for row in rows if row['event'] == 'caller-up-spike-collision')
        self.assertEqual(setup['scenario'], 'zero-lethal')
        self.assertEqual(setup['spikeDirection'], 'Up')
        self.assertFalse(setup['inputSampled'])
        self.assertEqual(setup['playerSpeed'], [0, 0])
        self.assertEqual(gravity_step['speedBefore'], [0, 0])
        self.assertEqual(gravity_step['speedAfter'][0], 0)
        self.assertGreater(gravity_step['speedAfter'][1], 0)
        self.assertEqual(gravity_step['gravityStep'], gravity_step['speedAfter'][1])
        self.assertFalse(gravity_step['dead'])
        self.assertLess(calibration['speedBefore'][1], 0)
        self.assertEqual(calibration['speedBefore'][1], -gravity_step['speedAfter'][1])
        self.assertEqual(calibration['speedBefore'][0], 0)
        self.assertEqual(calibration['speedAfter'], [0, 0])
        self.assertFalse(calibration['dead'])
        self.assertFalse(calibration['overlap'])
        self.assertEqual(calibration['sessionDeaths'], setup['sessionDeaths'])
        self.assertEqual(calibration['saveDeaths'], setup['saveDeaths'])
        self.assertLess(zero['preTickSpeedY'], 0)
        self.assertEqual(zero['preTickSpeedY'], calibration['speedBefore'][1])
        self.assertEqual(zero['expectedPostGravitySpeedY'], 0)
        self.assertEqual(zero['gravityStep'], gravity_step['speedAfter'][1])
        self.assertTrue(zero['overlap'])
        self.assertTrue(zero['velocityTrue'])
        self.assertTrue(zero['geometryTrue'])
        self.assertTrue(collision['dead'])
        self.assertFalse(collision['collidable'])
        self.assertTrue(collision['locked'])
        self.assertLess(collision['preTickSpeedY'], 0)
        self.assertEqual(collision['preTickSpeedY'], zero['preTickSpeedY'])
        self.assertEqual(collision['hazardCheckSpeedY'], 0)
        self.assertEqual(collision['position'], zero['position'])
        self.assertTrue(collision['hazardCheckOverlap'])
        self.assertTrue(collision['hazardCheckVelocityTrue'])
        self.assertTrue(collision['hazardCheckGeometryTrue'])
        self.assertEqual(collision['deathDirection'], [0, -1])
        self.assertTrue(collision['corpse'].startswith('PlayerDeadBody'))
        activated = next(row for row in rows if row['event'] == 'caller-up-spike-corpse')
        self.assertEqual(activated['corpse'], collision['corpse'])
        self.assertEqual(collision['sessionDeaths'], setup['sessionDeaths'] + 1)
        self.assertEqual(collision['saveDeaths'], setup['saveDeaths'] + 1)
        bounce = next(row for row in rows if row['event'] == 'caller-corpse-bounce')
        self.assertEqual(bounce['animation'], 'deadup')
        self.assertAlmostEqual(next(row for row in rows if row['event'] == 'caller-corpse-death-effect')['effect']['Duration'], 0.834, places=6)
        wipe = next(row for row in rows if row['event'] == 'caller-death-wipe')
        self.assertFalse(wipe['wipe']['wipeIn'])
        self.assertEqual(wipe['wipe']['onCompleteMethod'], 'Reload')
        reload = next(row for row in rows if row['event'] == 'caller-reload-second-load')
        self.assertEqual(reload['state'], 14)
        self.assertNotEqual(reload['previousPlayer'], reload['player'])
        second = next(row for row in rows if row['event'] == 'caller-second-normal0')
        self.assertEqual(second['state'], 0)
        live = next(row for row in rows if row['event'] == 'caller-resumed-live-tick')
        self.assertEqual(live['state'], 0)
        self.assertFalse(live['dead'])
        completed = rows[-1]
        self.assertEqual(completed['status'], 'up-spike-zero-lethal-source-collision-death-respawn14-normal0-one-live-tick')
        self.assertEqual(completed['preTickSpeedY'], zero['preTickSpeedY'])
        self.assertEqual(completed['hazardCheckSpeedY'], 0)
        self.assertTrue(completed['hazardCheckOverlap'])
        self.assertTrue(completed['hazardCheckGeometryTrue'])
        self.assertTrue(completed['hazardCheckVelocityTrue'])
        self.assertEqual(completed['saveDeaths'], setup['saveDeaths'] + 1)
        self.assertEqual(completed['sourceLoadLevelCalls'], 2)
        self.assertEqual(completed['nativeAttempts'], 0)
        self.assertEqual(completed['nativeMappingsAfter'], [])
        self.assertEqual(completed['completedLifecycleFamilies'], 0)
        self.assertFalse(completed['hazardOrderingDirectionalCollisionDeathParity'])

    def test_static_left_spike_lethal_collision_uses_original_die_and_existing_lifecycle(self):
        manifest = json.loads((self.output / 'source-manifest.json').read_text())
        source = next(entry for entry in manifest['executable_members']
            if entry['File'].endswith('Celeste.Spikes.cs') and entry['Name'] == 'OnCollide')
        block = Path(source['File']).read_bytes()[source['Start']:source['End']]
        self.assertEqual(hashlib.sha256(block).hexdigest(), source['Sha256'])
        self.assertIn(b'case Directions.Left:', block)
        self.assertIn(b'player.Die(new Vector2(-1f, 0f))', block)
        rows = self.execute_up_spike('left-lethal')
        self.assertFalse(any(row['event'] == 'boundary' for row in rows))
        self.assertNotIn('UnsupportedClosure', (self.output / 'up-spike-left-lethal.stderr').read_text())
        setup = next(row for row in rows if row['event'] == 'caller-left-spike-setup')
        seed = next(row for row in rows if row['event'] == 'caller-left-spike-seed')
        check = next(row for row in rows if row['event'] == 'caller-left-spike-check')
        collision = next(row for row in rows if row['event'] == 'caller-left-spike-collision')
        self.assertEqual(setup['scenario'], 'left-lethal')
        self.assertEqual(setup['spikeDirection'], 'Left')
        self.assertEqual(setup['spikeBounds'], [269, 80, 272, 96])
        self.assertFalse(setup['inputSampled'])
        self.assertEqual(seed['position'], [264.5, 96.0])
        self.assertEqual(seed['speed'], [120.0, 0.0])
        self.assertFalse(seed['overlap'])
        self.assertTrue(check['overlap'])
        self.assertGreater(check['positionDelta'][0], 0)
        self.assertEqual(check['speed'], [0.0, 0.0])
        self.assertTrue(check['dead'])
        self.assertFalse(check['collidable'])
        self.assertTrue(check['locked'])
        self.assertTrue(check['corpse'].startswith('PlayerDeadBody'))
        self.assertEqual(check['deathDirection'], [-1.0, 0.0])
        self.assertEqual(check['sessionDeaths'], setup['sessionDeaths'] + 1)
        self.assertEqual(check['saveDeaths'], setup['saveDeaths'] + 1)
        self.assertTrue(collision['dead'])
        self.assertFalse(collision['collidable'])
        self.assertTrue(collision['locked'])
        self.assertEqual(collision['deathDirection'], [-1.0, 0.0])
        self.assertEqual(collision['sessionDeaths'], setup['sessionDeaths'] + 1)
        self.assertEqual(collision['saveDeaths'], setup['saveDeaths'] + 1)
        activated = next(row for row in rows if row['event'] == 'caller-left-spike-corpse')
        self.assertEqual(activated['corpse'], collision['corpse'])
        bounce = next(row for row in rows if row['event'] == 'caller-corpse-bounce')
        self.assertEqual(bounce['animation'], 'deadside')
        self.assertAlmostEqual(next(row for row in rows if row['event'] == 'caller-corpse-death-effect')['effect']['Duration'], 0.834, places=6)
        wipe = next(row for row in rows if row['event'] == 'caller-death-wipe')
        self.assertFalse(wipe['wipe']['wipeIn'])
        self.assertEqual(wipe['wipe']['onCompleteMethod'], 'Reload')
        reload = next(row for row in rows if row['event'] == 'caller-reload-second-load')
        self.assertEqual(reload['state'], 14)
        self.assertNotEqual(reload['previousPlayer'], reload['player'])
        second = next(row for row in rows if row['event'] == 'caller-second-normal0')
        self.assertEqual(second['state'], 0)
        live = next(row for row in rows if row['event'] == 'caller-resumed-live-tick')
        self.assertEqual(live['state'], 0)
        self.assertFalse(live['dead'])
        completed = rows[-1]
        self.assertEqual(completed['status'], 'left-spike-lethal-source-collision-death-respawn14-normal0-one-live-tick')
        self.assertEqual(completed['deathDirection'], [-1.0, 0.0])
        self.assertEqual(completed['sourceLoadLevelCalls'], 2)
        self.assertEqual(completed['nativeAttempts'], 0)
        self.assertEqual(completed['nativeMappingsAfter'], [])
        self.assertEqual(completed['completedLifecycleFamilies'], 0)
        self.assertFalse(completed['hazardOrderingDirectionalCollisionDeathParity'])

    def test_static_left_spike_nonlethal_collision_stays_alive_without_lifecycle(self):
        rows = self.execute_up_spike('left-nonlethal')
        self.assertFalse(any(row['event'] == 'boundary' for row in rows))
        self.assertNotIn('UnsupportedClosure', (self.output / 'up-spike-left-nonlethal.stderr').read_text())
        setup = next(row for row in rows if row['event'] == 'caller-left-spike-setup')
        seed = next(row for row in rows if row['event'] == 'caller-left-spike-seed')
        check = next(row for row in rows if row['event'] == 'caller-left-spike-check')
        followup = next(row for row in rows if row['event'] == 'caller-left-spike-followup')
        self.assertEqual(setup['scenario'], 'left-nonlethal')
        self.assertEqual(setup['spikeDirection'], 'Left')
        self.assertEqual(setup['spikeBounds'], [269, 80, 272, 96])
        self.assertFalse(setup['inputSampled'])
        self.assertEqual(seed['position'], [268.0, 96.0])
        self.assertEqual(seed['speed'], [-100.0, 0.0])
        self.assertTrue(seed['overlap'])
        self.assertTrue(check['overlap'])
        self.assertLess(check['speed'][0], 0)
        self.assertLess(check['positionDelta'][0], 0)
        self.assertFalse(check['dead'])
        self.assertTrue(check['collidable'])
        self.assertFalse(check['locked'])
        self.assertIsNone(check['corpse'])
        self.assertIsNone(check['wipe'])
        self.assertEqual(check['sessionDeaths'], setup['sessionDeaths'])
        self.assertEqual(check['saveDeaths'], setup['saveDeaths'])
        self.assertFalse(followup['dead'])
        self.assertTrue(followup['collidable'])
        self.assertFalse(followup['locked'])
        self.assertIsNone(followup['corpse'])
        self.assertIsNone(followup['wipe'])
        self.assertEqual(followup['sessionDeaths'], setup['sessionDeaths'])
        self.assertEqual(followup['saveDeaths'], setup['saveDeaths'])
        self.assertFalse(any(row['event'] in ('caller-corpse-bounce', 'caller-corpse-death-effect',
            'caller-death-wipe', 'caller-reload-second-load', 'caller-second-normal0') for row in rows))
        completed = rows[-1]
        self.assertEqual(completed['status'], 'left-spike-nonlethal-source-collision-alive-no-lifecycle')
        self.assertEqual(completed['sessionDeaths'], setup['sessionDeaths'])
        self.assertEqual(completed['saveDeaths'], setup['saveDeaths'])
        self.assertEqual(completed['inputSampled'], False)
        self.assertEqual(completed['nativeAttempts'], 0)
        self.assertEqual(completed['nativeMappingsAfter'], [])
        self.assertEqual(completed['completedLifecycleFamilies'], 0)
        self.assertFalse(completed['hazardOrderingDirectionalCollisionDeathParity'])

    def test_static_left_spike_zero_x_is_lethal_uses_original_die_and_lifecycle(self):
        rows = self.execute_up_spike('left-zero-lethal')
        self.assertFalse(any(row['event'] == 'boundary' for row in rows))
        self.assertNotIn('UnsupportedClosure', (self.output / 'up-spike-left-zero-lethal.stderr').read_text())
        setup = next(row for row in rows if row['event'] == 'caller-left-spike-setup')
        calibration = next(row for row in rows if row['event'] == 'caller-left-spike-zero-calibration')
        zero_setup = next(row for row in rows if row['event'] == 'caller-left-spike-zero-setup')
        zero_check = next(row for row in rows if row['event'] == 'caller-left-spike-zero-check')
        seed = next(row for row in rows if row['event'] == 'caller-left-spike-seed')
        check = next(row for row in rows if row['event'] == 'caller-left-spike-check')
        collision = next(row for row in rows if row['event'] == 'caller-left-spike-collision')
        self.assertEqual(setup['scenario'], 'left-zero-lethal')
        self.assertEqual(setup['spikeDirection'], 'Left')
        self.assertEqual(setup['spikeBounds'], [269, 80, 272, 96])
        self.assertFalse(setup['inputSampled'])
        self.assertEqual(seed['position'], [268.0, 96.0])
        self.assertEqual(seed['speed'], [0.0, 0.0])
        self.assertTrue(seed['overlap'])
        self.assertEqual(calibration['speedBefore'], [0, 0])
        self.assertEqual(calibration['speedAfter'][0], 0.0)
        self.assertGreater(calibration['speedAfter'][1], 0.0)
        self.assertEqual(calibration['positionDelta'], [0, 0])
        self.assertEqual(calibration['positionRemainderBefore'][0], calibration['positionRemainderAfter'][0])
        self.assertEqual(calibration['wind'], [0, 0])
        self.assertEqual(calibration['liftSpeed'], [0, 0])
        self.assertEqual(calibration['moveX'], 0)
        self.assertEqual(zero_setup['hazardCheckSpeedX'], 0.0)
        self.assertTrue(zero_setup['overlap'])
        self.assertEqual(zero_setup['position'], [268.0, 96.0])
        self.assertEqual(zero_setup['positionRemainder'][0], 0.0)
        self.assertEqual(zero_setup['wind'], [0, 0])
        self.assertEqual(zero_setup['liftSpeed'], [0, 0])
        self.assertEqual(zero_setup['moveX'], 0)
        self.assertEqual(zero_setup['moveY'], 0)
        self.assertEqual(zero_setup['intervening'], {
            'explodeLaunchBoostTimer': 0, 'wallBoostTimer': 0, 'wallSpeedRetentionTimer': 0,
            'hopWaitX': 0, 'forceMoveXTimer': 0, 'forceMoveX': 0,
            'dashPressed': False, 'jumpCheck': False, 'grabCheck': False,
            'ducking': False, 'holding': None})
        self.assertEqual(zero_check['hazardCheckSpeedX'], 0.0)
        self.assertTrue(zero_check['overlapBefore'])
        self.assertEqual(zero_check['positionDelta'][0], 0.0)
        self.assertEqual(zero_check['positionRemainderBefore'][0], zero_check['positionRemainderAfter'][0])
        self.assertEqual(zero_check['deathDirection'], [-1.0, 0.0])
        self.assertTrue(check['overlap'])
        self.assertEqual(check['speed'], [0.0, 0.0])
        self.assertEqual(check['positionDelta'][0], 0.0)
        self.assertEqual(check['positionRemainderBefore'][0], check['positionRemainderAfter'][0])
        self.assertTrue(check['dead'])
        self.assertFalse(check['collidable'])
        self.assertTrue(check['locked'])
        self.assertTrue(check['corpse'].startswith('PlayerDeadBody'))
        self.assertEqual(check['deathDirection'], [-1.0, 0.0])
        self.assertEqual(check['sessionDeaths'], setup['sessionDeaths'] + 1)
        self.assertEqual(check['saveDeaths'], setup['saveDeaths'] + 1)
        self.assertTrue(collision['dead'])
        self.assertFalse(collision['collidable'])
        self.assertTrue(collision['locked'])
        self.assertEqual(collision['deathDirection'], [-1.0, 0.0])
        self.assertEqual(collision['sessionDeaths'], setup['sessionDeaths'] + 1)
        self.assertEqual(collision['saveDeaths'], setup['saveDeaths'] + 1)
        activated = next(row for row in rows if row['event'] == 'caller-left-spike-corpse')
        self.assertEqual(activated['corpse'], collision['corpse'])
        bounce = next(row for row in rows if row['event'] == 'caller-corpse-bounce')
        self.assertEqual(bounce['animation'], 'deadside')
        self.assertAlmostEqual(next(row for row in rows if row['event'] == 'caller-corpse-death-effect')['effect']['Duration'], 0.834, places=6)
        wipe = next(row for row in rows if row['event'] == 'caller-death-wipe')
        self.assertFalse(wipe['wipe']['wipeIn'])
        self.assertEqual(wipe['wipe']['onCompleteMethod'], 'Reload')
        reload = next(row for row in rows if row['event'] == 'caller-reload-second-load')
        self.assertEqual(reload['state'], 14)
        self.assertNotEqual(reload['previousPlayer'], reload['player'])
        second = next(row for row in rows if row['event'] == 'caller-second-normal0')
        self.assertEqual(second['state'], 0)
        live = next(row for row in rows if row['event'] == 'caller-resumed-live-tick')
        self.assertEqual(live['state'], 0)
        self.assertFalse(live['dead'])
        completed = rows[-1]
        self.assertEqual(completed['status'], 'left-spike-zero-x-lethal-source-collision-death-respawn14-normal0-one-live-tick')
        self.assertEqual(completed['deathDirection'], [-1.0, 0.0])
        self.assertEqual(completed['sourceLoadLevelCalls'], 2)
        self.assertEqual(completed['nativeAttempts'], 0)
        self.assertEqual(completed['nativeMappingsAfter'], [])
        self.assertEqual(completed['completedLifecycleFamilies'], 0)
        self.assertFalse(completed['hazardOrderingDirectionalCollisionDeathParity'])

    def test_static_up_spike_plane_equality_lethal_uses_original_die_and_lifecycle(self):
        rows = self.execute_up_spike('plane-equality-lethal')
        self.assertFalse(any(row['event'] == 'boundary' for row in rows))
        self.assertNotIn('UnsupportedClosure', (self.output / 'up-spike-plane-equality-lethal.stderr').read_text())
        setup = next(row for row in rows if row['event'] == 'caller-up-spike-setup')
        gravity_step = next(row for row in rows if row['event'] == 'caller-up-spike-zero-gravity-step')
        calibration = next(row for row in rows if row['event'] == 'caller-up-spike-zero-calibration')
        plane = next(row for row in rows if row['event'] == 'caller-up-spike-zero-setup')
        plane_check = next(row for row in rows if row['event'] == 'caller-up-spike-plane-check')
        collision = next(row for row in rows if row['event'] == 'caller-up-spike-collision')
        self.assertEqual(setup['scenario'], 'plane-equality-lethal')
        self.assertEqual(setup['spikeDirection'], 'Up')
        self.assertFalse(setup['inputSampled'])
        self.assertEqual(setup['playerSpeed'], [0, 0])
        self.assertEqual(gravity_step['speedBefore'], [0, 0])
        self.assertEqual(gravity_step['speedAfter'][0], 0)
        self.assertGreater(gravity_step['speedAfter'][1], 0)
        self.assertEqual(gravity_step['gravityStep'], gravity_step['speedAfter'][1])
        self.assertEqual(calibration['speedBefore'][1], -gravity_step['speedAfter'][1])
        self.assertEqual(calibration['speedAfter'], [0, 0])
        self.assertFalse(calibration['overlap'])
        self.assertFalse(calibration['dead'])
        self.assertLess(plane['preTickSpeedY'], 0)
        self.assertEqual(plane['preTickSpeedY'], calibration['speedBefore'][1])
        self.assertEqual(plane['expectedPostGravitySpeedY'], 0)
        self.assertTrue(plane['overlap'])
        self.assertTrue(plane['velocityTrue'])
        self.assertTrue(plane['geometryTrue'])
        self.assertEqual(plane_check['hurtboxBottomBefore'], plane_check['spikeBounds'][3])
        self.assertEqual(plane_check['hurtboxBottomAfter'], plane_check['spikeBounds'][3])
        self.assertEqual(plane_check['planeBottomDeltaBefore'], 0)
        self.assertEqual(plane_check['planeBottomDeltaAfter'], 0)
        self.assertEqual(plane_check['hurtboxBottomOffset'], plane_check['hurtboxBottomBefore'] - plane_check['position'][1])
        self.assertTrue(collision['dead'])
        self.assertFalse(collision['collidable'])
        self.assertTrue(collision['locked'])
        self.assertEqual(collision['hazardCheckSpeedY'], 0)
        self.assertTrue(collision['hazardCheckOverlap'])
        self.assertTrue(collision['hazardCheckVelocityTrue'])
        self.assertTrue(collision['hazardCheckGeometryTrue'])
        self.assertEqual(collision['position'], plane_check['position'])
        self.assertEqual(plane_check['position'], plane['position'])
        self.assertEqual(plane_check['positionRemainderAfter'], plane_check['positionRemainderBefore'])
        self.assertEqual(plane_check['hazardCheckSpeedY'], 0)
        self.assertTrue(plane_check['overlap'])
        self.assertTrue(plane_check['velocityTrue'])
        self.assertTrue(plane_check['geometryTrue'])
        self.assertTrue(plane_check['dead'])
        self.assertIn('inferred from safe-pose calibration plus unchanged source order', plane_check['proofLabel'])
        self.assertEqual(collision['deathDirection'], [0, -1])
        self.assertTrue(collision['corpse'].startswith('PlayerDeadBody'))
        self.assertEqual(collision['sessionDeaths'], setup['sessionDeaths'] + 1)
        self.assertEqual(collision['saveDeaths'], setup['saveDeaths'] + 1)
        activated = next(row for row in rows if row['event'] == 'caller-up-spike-corpse')
        self.assertEqual(activated['corpse'], collision['corpse'])
        bounce = next(row for row in rows if row['event'] == 'caller-corpse-bounce')
        self.assertEqual(bounce['animation'], 'deadup')
        self.assertAlmostEqual(next(row for row in rows if row['event'] == 'caller-corpse-death-effect')['effect']['Duration'], 0.834, places=6)
        wipe = next(row for row in rows if row['event'] == 'caller-death-wipe')
        self.assertFalse(wipe['wipe']['wipeIn'])
        self.assertEqual(wipe['wipe']['onCompleteMethod'], 'Reload')
        reload = next(row for row in rows if row['event'] == 'caller-reload-second-load')
        self.assertEqual(reload['state'], 14)
        second = next(row for row in rows if row['event'] == 'caller-second-normal0')
        self.assertEqual(second['state'], 0)
        live = next(row for row in rows if row['event'] == 'caller-resumed-live-tick')
        self.assertEqual(live['state'], 0)
        self.assertFalse(live['dead'])
        completed = rows[-1]
        self.assertEqual(completed['status'], 'up-spike-plane-equality-lethal-source-collision-death-respawn14-normal0-one-live-tick')
        self.assertEqual(completed['hazardCheckSpeedY'], 0)
        self.assertIn('inferred from safe-pose calibration plus unchanged source order', completed['claim'])
        self.assertEqual(completed['sourceLoadLevelCalls'], 2)
        self.assertEqual(completed['nativeAttempts'], 0)
        self.assertEqual(completed['nativeMappingsAfter'], [])
        self.assertEqual(completed['completedLifecycleFamilies'], 0)
        self.assertFalse(completed['hazardOrderingDirectionalCollisionDeathParity'])

    def test_static_simultaneous_fixture_controlled_extra_hazard_single_death(self):
        rows = self.execute_up_spike('simultaneous-fixture-lethal')
        self.assertFalse(any(row['event'] == 'boundary' for row in rows))
        self.assertNotIn('UnsupportedClosure',
            (self.output / 'up-spike-simultaneous-fixture-lethal.stderr').read_text())
        setup = next(row for row in rows if row['event'] == 'caller-simultaneous-hazard-setup')
        fixture_add = next(row for row in rows if row['event'] == 'caller-simultaneous-fixture-add')
        commit = next(row for row in rows if row['event'] == 'caller-simultaneous-fixture-commit')
        gravity = next(row for row in rows if row['event'] == 'caller-simultaneous-hazard-zero-gravity-step')
        calibration = next(row for row in rows if row['event'] == 'caller-simultaneous-hazard-zero-calibration')
        plane = next(row for row in rows if row['event'] == 'caller-simultaneous-hazard-zero-setup')
        seed = next(row for row in rows if row['event'] == 'caller-simultaneous-fixture-seed')
        collision = next(row for row in rows if row['event'] == 'caller-simultaneous-hazard-collision')
        fixture_collision = next(row for row in rows if row['event'] == 'caller-simultaneous-fixture-collision')
        activated = next(row for row in rows if row['event'] == 'caller-simultaneous-hazard-corpse')
        corpse_state = next(row for row in rows if row['event'] == 'caller-simultaneous-corpse-state')
        reload = next(row for row in rows if row['event'] == 'caller-reload-second-load')
        reload_state = next(row for row in rows if row['event'] == 'caller-simultaneous-reload-state')
        second = next(row for row in rows if row['event'] == 'caller-second-normal0')
        live = next(row for row in rows if row['event'] == 'caller-resumed-live-tick')
        raw_geometry = [
            {'direction': 'Up', 'bounds': [40, 165, 80, 168]},
            {'direction': 'Up', 'bounds': [104, 149, 144, 152]},
            {'direction': 'Up', 'bounds': [176, 125, 208, 128]},
            {'direction': 'Up', 'bounds': [208, 157, 232, 160]},
            {'direction': 'Left', 'bounds': [269, 80, 272, 96]}]
        self.assertEqual(setup['scenario'], 'simultaneous-fixture-lethal')
        self.assertEqual(setup['spikeDirection'], 'Up')
        self.assertEqual(setup['spikeBounds'], [40, 165, 80, 168])
        self.assertEqual(setup['playerPosition'], [30, 168])
        self.assertFalse(setup['inputSampled'])
        self.assertEqual(fixture_add['rawHazardCount'], 5)
        self.assertEqual([{'direction': hazard['direction'], 'bounds': hazard['bounds']}
            for hazard in fixture_add['rawHazards']], raw_geometry)
        self.assertEqual(fixture_add['fixture'], {
            'id': 'explicit-fixture-1', 'type': 'Spikes', 'direction': 'Left',
            'position': [64, 155], 'size': 16, 'bounds': [61, 155, 64, 171],
            'constructor': 'Spikes(Vector2(64,155),16,Spikes.Directions.Left,"default")'})
        self.assertFalse(fixture_add['fixtureInEntities'])
        self.assertFalse(fixture_add['fixtureScene'])
        self.assertTrue(fixture_add['fixturePendingCommit'])
        self.assertEqual(fixture_add['rngCallsDeltaBeforeCommit'], 0)
        self.assertFalse(fixture_add['safeOverlap'])
        self.assertEqual(commit['tick'], gravity['tick'])
        self.assertTrue(commit['committed'])
        self.assertTrue(commit['fixtureInEntities'])
        self.assertTrue(commit['fixtureScene'])
        self.assertEqual(commit['fixtureTag'], 0)
        self.assertFalse(commit['fixtureIsGlobal'])
        self.assertEqual(commit['rawHazardCount'], 5)
        self.assertEqual(commit['fixtureCount'], 1)
        self.assertTrue(commit['rawGeometryUnchanged'])
        self.assertTrue(commit['globalEntitiesRetained'])
        self.assertTrue(commit['globalEntities'])
        self.assertEqual(commit['rngCallsAdded'], 2)
        self.assertEqual(commit['rngCallsTickOther'], 1)
        self.assertEqual(commit['rngCallsDelta'], 3)
        self.assertFalse(commit['rngRewound'])
        self.assertEqual(commit['solidTilesIdentityBefore'], commit['solidTilesIdentityAfter'])
        self.assertFalse(commit['solidTilesAvailable'])
        self.assertIn('cannot rebake', commit['tileObservation'])
        self.assertEqual(len(commit['trackedPlayerColliderOrder']), 6)
        first_collider = commit['trackedPlayerColliderOrder'][0]
        last_collider = commit['trackedPlayerColliderOrder'][-1]
        self.assertEqual(first_collider['id'], 'raw-1')
        self.assertEqual(first_collider['direction'], 'Up')
        self.assertEqual(first_collider['bounds'], [40, 165, 80, 168])
        self.assertEqual(last_collider['id'], 'explicit-fixture-1')
        self.assertEqual(last_collider['direction'], 'Left')
        self.assertEqual(last_collider['bounds'], [61, 155, 64, 171])
        self.assertGreater(gravity['speedAfter'][1], 0)
        self.assertFalse(gravity['dead'])
        self.assertEqual(calibration['speedBefore'], [0, -gravity['gravityStep']])
        self.assertEqual(calibration['speedAfter'], [0, 0])
        self.assertEqual(calibration['positionAfter'], [30, 168])
        self.assertFalse(calibration['overlap'])
        self.assertFalse(calibration['dead'])
        self.assertEqual(plane['position'], [60, 170])
        self.assertEqual(plane['hurtboxBounds'], [56, 159, 64, 168])
        self.assertTrue(plane['overlap'])
        self.assertTrue(plane['velocityTrue'])
        self.assertTrue(plane['geometryTrue'])
        self.assertEqual(seed['position'], [60, 170])
        self.assertEqual(seed['hurtboxBounds'], [56, 159, 64, 168])
        self.assertEqual(seed['rawU1']['bounds'], [40, 165, 80, 168])
        self.assertEqual(seed['fixtureBounds'], [61, 155, 64, 171])
        self.assertTrue(seed['overlapsRaw'])
        self.assertTrue(seed['overlapsFixture'])
        self.assertEqual(seed['expectedCheckSpeedX'], 0)
        self.assertEqual(seed['expectedCheckSpeedY'], 0)
        self.assertTrue(seed['rawEligible'])
        self.assertTrue(seed['fixtureEligible'])
        self.assertEqual(seed['firstEligibleId'], 'raw-1')
        self.assertEqual(seed['firstEligibleOrder'], 0)
        self.assertEqual(seed['fixtureOrder'], 5)
        self.assertEqual(len(seed['trackedPlayerColliderOrder']), 6)
        self.assertIn('Player.Update', seed['loopMechanism'])
        self.assertIn('return', seed['loopMechanism'])
        self.assertFalse(seed['callbackInstrumentation'])
        self.assertTrue(collision['dead'])
        self.assertFalse(collision['collidable'])
        self.assertTrue(collision['locked'])
        self.assertEqual(collision['position'], [60, 170])
        self.assertEqual(collision['deathDirection'], [0, -1])
        self.assertTrue(collision['corpse'].startswith('PlayerDeadBody'))
        self.assertEqual(collision['sessionDeaths'], setup['sessionDeaths'] + 1)
        self.assertEqual(collision['saveDeaths'], setup['saveDeaths'] + 1)
        self.assertEqual(fixture_collision['sessionDeaths'], setup['sessionDeaths'] + 1)
        self.assertEqual(fixture_collision['deathsInCurrentLevel'], fixture_collision['deathsInCurrentLevelBefore'] + 1)
        self.assertEqual(fixture_collision['saveDeaths'], setup['saveDeaths'] + 1)
        self.assertEqual(fixture_collision['pendingCorpses'], 1)
        self.assertEqual(fixture_collision['committedCorpses'], 0)
        self.assertEqual(fixture_collision['rawHazardCount'], 5)
        self.assertTrue(fixture_collision['fixturePresent'])
        self.assertTrue(fixture_collision['rawGeometryUnchanged'])
        self.assertEqual(fixture_collision['deathDirection'], [0, -1])
        self.assertEqual(activated['corpse'], collision['corpse'])
        self.assertEqual(corpse_state['corpse'], collision['corpse'])
        self.assertEqual(corpse_state['committedCorpses'], 1)
        self.assertEqual(corpse_state['pendingCorpses'], 0)
        self.assertEqual(corpse_state['maxCorpseCount'], 1)
        bounce = next(row for row in rows if row['event'] == 'caller-corpse-bounce')
        self.assertEqual(bounce['animation'], 'deadup')
        self.assertAlmostEqual(next(row for row in rows if row['event'] == 'caller-corpse-death-effect')
            ['effect']['Duration'], 0.834, places=6)
        wipe = next(row for row in rows if row['event'] == 'caller-death-wipe')
        self.assertFalse(wipe['wipe']['wipeIn'])
        self.assertEqual(wipe['wipe']['onCompleteMethod'], 'Reload')
        self.assertEqual(reload['state'], 14)
        self.assertNotEqual(reload['previousPlayer'], reload['player'])
        self.assertEqual(reload_state['rawHazardCount'], 5)
        self.assertFalse(reload_state['fixturePresent'])
        self.assertIsNone(reload_state['fixtureScene'])
        self.assertFalse(reload_state['fixtureWasGlobal'])
        self.assertTrue(reload_state['rawGeometryUnchanged'])
        self.assertTrue(reload_state['globalEntitiesRetained'])
        self.assertEqual([{'direction': hazard['direction'], 'bounds': hazard['bounds']}
            for hazard in reload_state['rawHazards']], raw_geometry)
        self.assertEqual(reload_state['rngIdentity'], commit['rngIdentity'])
        self.assertGreaterEqual(reload_state['rngCalls'], commit['rngCallsAfterTick'])
        self.assertGreater(reload_state['rawTimeActive'], commit['rawTimeActive'])
        self.assertFalse(reload_state['inputSampled'])
        self.assertEqual(second['state'], 0)
        self.assertEqual(live['state'], 0)
        self.assertFalse(live['dead'])
        self.assertEqual(len([row for row in rows if row['event'] == 'caller-reload-second-load']), 1)
        self.assertEqual(len([row for row in rows if row['event'] == 'caller-second-normal0']), 1)
        completed = rows[-1]
        self.assertEqual(completed['status'],
            'simultaneous-fixture-lethal-source-collision-death-respawn14-normal0-one-live-tick')
        self.assertEqual(completed['sourceLoadLevelCalls'], 2)
        self.assertEqual(completed['corpseCreated'], 1)
        self.assertEqual(completed['deathWipes'], 1)
        self.assertEqual(completed['reloads'], 1)
        self.assertEqual(completed['resumedNormalUpdates'], 1)
        self.assertEqual(completed['explicitFixtureCount'], 1)
        self.assertEqual(completed['rawHazardCount'], 5)
        self.assertTrue(completed['fixtureUnloaded'])
        self.assertFalse(completed['fixtureWasGlobal'])
        self.assertEqual(completed['maxCorpseCount'], 1)
        self.assertGreaterEqual(completed['rngCallsDelta'], commit['rngCallsDelta'])
        self.assertIn('Explicit controlled fixture', completed['claim'])
        self.assertIn('not natural room', completed['claim'])
        self.assertEqual(completed['nativeAttempts'], 0)
        self.assertEqual(completed['nativeMappingsAfter'], [])
        self.assertEqual(completed['completedLifecycleFamilies'], 0)
        self.assertFalse(completed['hazardOrderingDirectionalCollisionDeathParity'])

    def test_input_right_keyboard_axis_members_are_original_executable_bodies(self):
        manifest = json.loads((self.output / 'source-manifest.json').read_text())
        expected = {
            ('Monocle.VirtualIntegerAxis.cs', 'Update'):
                [b'PreviousValue = Value', b'Positive.Axis', b'Value = 1'],
            ('Monocle.Binding.cs', 'Axis'):
                [b'MInput.Keyboard.Check(item)', b'return 1f'],
            ('Microsoft.Xna.Framework.Input.KeyboardState.cs', 'KeyboardState'):
                [b'public KeyboardState(params Keys[] keys)', b'InternalSetKey(key)'],
            ('Microsoft.Xna.Framework.Input.KeyboardState.cs', 'InternalSetKey'):
                [b'keys0 |= num'],
        }
        for (filename, name), tokens in expected.items():
            entries = [entry for entry in manifest['executable_members']
                if entry['File'].endswith(filename) and entry['Name'] == name]
            self.assertEqual(len(entries), 1, (filename, name))
            entry = entries[0]
            block = Path(entry['File']).read_bytes()[entry['Start']:entry['End']]
            self.assertEqual(hashlib.sha256(block).hexdigest(), entry['Sha256'])
            for token in tokens:
                self.assertIn(token, block)

    def test_input_right_caller_declares_only_right_key_and_never_seeds_motion(self):
        text = (ROOT / 'tests/native/oracle/death/RoomCoreExecution.cs').read_text()
        start = text.index('public static void RunInputRight')
        end = text.index('sealed class JumpInputSample', start)
        caller = text[start:end]
        self.assertNotRegex(caller, r'\.(Position|Speed|PositionRemainder|Deaths|DeathsInCurrentLevel|TotalDeaths)\s*=[^=]')
        for token in ('Settings.Instance.Right.Add(Keys.Right)', 'Input.Initialize()',
                'MInput.Keyboard.PreviousState = default(KeyboardState)',
                'MInput.Keyboard.CurrentState = new KeyboardState(Keys.Right)',
                'Input.MoveX.Update()', 'Tick(probe, driver, tick, "source-axis-only")',
                'Settings.Instance.Left', 'fullMInputUpdateExecuted = false'):
            self.assertIn(token, caller)
        self.assertEqual(set(re.findall(r'Keys\.(\w+)', caller)), {'Right'})
        for forbidden in ('Keyboard.GetState(', 'MInput.Update(', 'KeyboardData.Update(',
                'GamePadData.Update(', 'UpdateVirtualInputs(', 'RunStaticSpike', '.Die(', 'OnCollide('):
            self.assertNotIn(forbidden, caller)

    def test_input_right_source_axis_only_moves_natural_spawn_without_caller_seed(self):
        rows = self.execute_input_right()
        self.assertFalse(any(row['event'] == 'boundary' for row in rows))
        self.assertNotIn('UnsupportedClosure', (self.output / 'input-right.stderr').read_text())
        controls = next(row for row in rows if row['event'] == 'caller-input-right-controls')
        load = next(row for row in rows if row['event'] == 'caller-input-right-load')
        normal = next(row for row in rows if row['event'] == 'caller-input-right-normal0')
        neutral = next(row for row in rows if row['event'] == 'caller-input-right-neutral-axis')
        axes = [row for row in rows if row['event'] == 'caller-input-right-axis']
        held = [row for row in rows if row['event'] == 'caller-input-right-held-tick']
        release = next(row for row in rows if row['event'] == 'caller-input-right-release-axis')
        completed = rows[-1]
        self.assertEqual(controls['rightKeyboardBefore'], [])
        self.assertEqual(controls['rightKeyboardAfter'], ['Right'])
        self.assertTrue(controls['added'])
        self.assertEqual(controls['leftKeyboardBefore'], controls['leftKeyboardAfter'])
        self.assertEqual(controls['jumpKeyboardBefore'], controls['jumpKeyboardAfter'])
        self.assertEqual(controls['moveXPositiveKeyboard'], ['Right'])
        self.assertEqual(controls['moveXNegativeKeyboard'], [])
        self.assertEqual(controls['moveXPositiveAltKeyboard'], [])
        self.assertEqual(controls['moveXNegativeAltKeyboard'], [])
        self.assertFalse(controls['inputSampled'])
        self.assertEqual(load['state'], 14)
        self.assertEqual(normal['state'], 0)
        self.assertEqual(normal['position'], load['position'])
        self.assertEqual(normal['speed'], load['speed'])
        self.assertEqual(neutral['value'], 0)
        self.assertFalse(neutral['keyboardRightDown'])
        self.assertGreaterEqual(len(held), 1)
        self.assertLessEqual(len(held), 4)
        self.assertEqual(len(axes), len(held))
        for axis, tick in zip(axes, held):
            self.assertEqual(axis['value'], 1)
            self.assertTrue(axis['keyboardRightDown'])
            self.assertFalse(axis['keyboardPreviousRightDown'])
            self.assertEqual(axis['positiveKeyboard'], ['Right'])
            self.assertEqual(axis['negativeKeyboard'], [])
            self.assertEqual(tick['axisValueBeforeTick'], 1)
            self.assertEqual(tick['preState'], 0)
            self.assertEqual(tick['state'], 0)
            self.assertFalse(tick['dead'])
        first = held[0]
        self.assertGreater(first['postSpeed'][0], 0)
        if first['integerXBefore'] == first['integerXAfter']:
            self.assertNotEqual(first['postRemainder'][0], first['preRemainder'][0])
        self.assertTrue(any(row['integerXAfter'] > row['integerXBefore'] for row in held))
        self.assertGreater(held[-1]['postPosition'][0], load['position'][0])
        self.assertGreater(held[-1]['postPosition'][0], normal['position'][0])
        self.assertEqual(release['value'], 0)
        self.assertEqual(release['previousValue'], 1)
        self.assertFalse(release['keyboardRightDown'])
        self.assertEqual(completed['status'], 'input-right-source-axis-only-natural-respawn-integer-move')
        self.assertEqual(completed['heldTicks'], len(held))
        self.assertEqual(completed['axisValueAtMovement'], 1)
        self.assertEqual(completed['naturalSpawn']['position'], load['position'])
        self.assertEqual(completed['naturalSpawn']['speed'], load['speed'])
        self.assertEqual(completed['stateAfter'], 0)
        self.assertTrue(completed['alive'])
        self.assertEqual(completed['integerXBefore'], int(normal['position'][0]))
        self.assertGreater(completed['integerXAfter'], completed['integerXBefore'])
        self.assertEqual(completed['callerPositionSpeedWrites'], 0)
        self.assertIn('RunInputRight', completed['callerWriteGuard'])
        self.assertTrue(completed['inputSampled'])
        self.assertEqual(completed['inputSamplingProfile'], 'source-axis-only')
        self.assertFalse(completed['fullMInputUpdateExecuted'])
        self.assertFalse(completed['gamepadSampled'])
        self.assertFalse(completed['buttonsSampled'])
        self.assertEqual(completed['nativeAttempts'], 0)
        self.assertEqual(completed['nativeMappingsAfter'], [])
        self.assertEqual(completed['completedLifecycleFamilies'], 0)
        self.assertFalse(completed['hazardOrderingDirectionalCollisionDeathParity'])

    def test_input_right_profile_stays_source_axis_only_without_full_input_engine(self):
        rows = self.execute_input_right('input-right-profile')
        completed = rows[-1]
        self.assertEqual(completed['inputSamplingProfile'], 'source-axis-only')
        self.assertIn('KeyboardState(Keys.Right)', completed['rawFixtureBoundary'])
        self.assertIn('Keyboard.GetState not invoked', completed['rawFixtureBoundary'])
        self.assertFalse(completed['fullMInputUpdateExecuted'])
        self.assertFalse(completed['gamepadSampled'])
        self.assertFalse(completed['buttonsSampled'])
        self.assertIn('not full MInput sampling or physical keyboard', completed['claim'])
        normal = next(row for row in rows if row['event'] == 'caller-input-right-normal0')
        driver_rows = [row for row in rows if row['event'] == 'driver-tick']
        self.assertTrue(driver_rows)
        sampled_driver = [row for row in driver_rows if row['tick'] > normal['tick']]
        self.assertTrue(sampled_driver)
        self.assertTrue(all(row['inputSamplingProfile'] == 'source-axis-only' for row in sampled_driver))
        self.assertTrue(all(row['inputSampled'] for row in sampled_driver))
        self.assertTrue(all(not row['fullMInputUpdateExecuted'] for row in sampled_driver))
        self.assertTrue(all(not row['inputSampled'] for row in driver_rows if row['tick'] <= normal['tick']))
        axis_rows = [row for row in rows if row['event'] in (
            'caller-input-right-axis', 'caller-input-right-neutral-axis', 'caller-input-right-release-axis')]
        self.assertTrue(axis_rows)
        self.assertTrue(all(row['inputSamplingProfile'] == 'source-axis-only' for row in axis_rows))
        self.assertTrue(all(not row['fullMInputUpdateExecuted'] for row in axis_rows))
        self.assertTrue(all(not row['gamepadSampled'] for row in axis_rows))
        self.assertTrue(all(not row['buttonsSampled'] for row in axis_rows))
        self.assertFalse(any(row.get('inputSampled') for row in rows if row['event'] == 'caller-input-right-controls'))

    def execute_input_jump_buffer(self, mode):
        trace = self.output / f'input-jump-buffer-{mode}.jsonl'
        result = subprocess.run([str(SDK), str(self.output / 'bin/Release/net8.0/Oracle.dll'),
            'room-core-input-jump-buffer', mode, str(trace)], cwd=ROOT, env=oracle_environment(SDK),
            text=True, capture_output=True)
        (self.output / f'input-jump-buffer-{mode}.stdout').write_text(result.stdout)
        (self.output / f'input-jump-buffer-{mode}.stderr').write_text(result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return [json.loads(line) for line in trace.read_text().splitlines()]

    def test_input_jump_buffer_button_members_are_original_executable_bodies(self):
        manifest = json.loads((self.output / 'source-manifest.json').read_text())
        expected = {
            ('Monocle.VirtualButton.cs', 'Released'):
                [b'public bool Released', b'MInput.Disabled', b'Binding.Released(GamepadIndex, Threshold)'],
            ('Monocle.VirtualButton.cs', 'Update'):
                [b'public override void Update()', b'bufferCounter -= Engine.DeltaTime',
                 b'Binding.Pressed(GamepadIndex, Threshold)', b'Binding.Check(GamepadIndex, Threshold)',
                 b'bufferCounter = BufferTime'],
            ('Monocle.Binding.cs', 'Released'):
                [b'public bool Released(int gamepadIndex, float threshold)',
                 b'MInput.Keyboard.Released(Keyboard[i])', b'MInput.GamePads[gamepadIndex].Released'],
            ('Monocle.MInput.cs', 'Released'):
                [b'public bool Released(Keys key)', b'!CurrentState.IsKeyDown(key)',
                 b'PreviousState.IsKeyDown(key)'],
        }
        for (filename, name), tokens in expected.items():
            entries = [entry for entry in manifest['executable_members']
                if entry['File'].endswith(filename) and entry['Name'] == name]
            matches = []
            for entry in entries:
                block = Path(entry['File']).read_bytes()[entry['Start']:entry['End']]
                if hashlib.sha256(block).hexdigest() != entry['Sha256']:
                    continue
                if all(token in block for token in tokens):
                    matches.append(entry)
            self.assertEqual(len(matches), 1, (filename, name))

    def test_input_jump_buffer_press_on_zero_crossing_buffers_and_skips_scene(self):
        rows = self.execute_input_jump_buffer('press-on-crossing')
        self.assertFalse(any(row['event'] == 'boundary' for row in rows))
        self.assertNotIn('UnsupportedClosure', (self.output / 'input-jump-buffer-press-on-crossing.stderr').read_text())
        controls = next(row for row in rows if row['event'] == 'caller-input-jump-buffer-controls')
        load = next(row for row in rows if row['event'] == 'caller-input-jump-buffer-load')
        normal = next(row for row in rows if row['event'] == 'caller-input-jump-buffer-normal0')
        freeze = next(row for row in rows if row['event'] == 'caller-input-jump-buffer-freeze')
        frames = [row for row in rows if row['event'] == 'caller-input-jump-buffer-frame']
        crossing = [row for row in frames if row['crossing']]
        completed = rows[-1]
        self.assertEqual(controls['jumpKeyboardBefore'], [])
        self.assertEqual(controls['jumpKeyboardAfter'], ['C'])
        self.assertEqual(controls['jumpControllerBefore'], [])
        self.assertEqual(controls['jumpControllerAfter'], [])
        self.assertTrue(controls['added'])
        self.assertTrue(controls['controllerCleared'])
        self.assertTrue(controls['inputJumpBindingIsSettings'])
        self.assertFalse(controls['defaultKeyboardControlsExecuted'])
        self.assertFalse(controls['inputSampled'])
        self.assertEqual(load['state'], 14)
        self.assertEqual(normal['state'], 0)
        self.assertEqual(normal['position'], load['position'])
        self.assertEqual(normal['speed'], load['speed'])
        self.assertEqual(freeze['mode'], 'press-on-crossing')
        self.assertEqual(freeze['formula'], '1*RawDeltaTime')
        self.assertGreater(freeze['duration'], 0)
        self.assertEqual(len(frames), 2)
        self.assertEqual(len(crossing), 1)
        press = crossing[0]
        self.assertEqual(press['sampleIndex'], 0)
        self.assertGreater(press['freezeBefore'], 0)
        self.assertEqual(press['freezeAfter'], 0.0)
        self.assertFalse(press['sceneRan'])
        self.assertFalse(press['keys']['previousCDown'])
        self.assertTrue(press['keys']['currentCDown'])
        self.assertEqual(press['before']['bufferCounter'], 0.0)
        self.assertTrue(press['afterUpdate']['check'])
        self.assertTrue(press['afterUpdate']['pressed'])
        self.assertFalse(press['afterUpdate']['released'])
        self.assertEqual(press['afterUpdate']['bufferCounter'], press['afterUpdate']['bufferTime'])
        held = frames[1]
        self.assertTrue(held['sceneRan'])
        self.assertEqual(held['freezeBefore'], 0.0)
        self.assertEqual(held['freezeAfter'], 0.0)
        self.assertTrue(held['keys']['previousCDown'])
        self.assertTrue(held['keys']['currentCDown'])
        self.assertTrue(held['afterUpdate']['check'])
        self.assertTrue(held['afterUpdate']['pressed'])
        self.assertFalse(held['afterUpdate']['released'])
        self.assertEqual(held['before']['bufferCounter'], press['afterUpdate']['bufferCounter'])
        self.assertAlmostEqual(held['afterUpdate']['bufferCounter'],
            held['before']['bufferCounter'] - held['enginePhase']['deltaTime'], places=6)
        self.assertEqual(held['afterScene']['bufferCounter'], held['afterUpdate']['bufferCounter'])
        self.assertEqual(held['playerAfterScene']['state'], 0)
        self.assertFalse(held['playerAfterScene']['dead'])
        self.assertEqual(completed['status'], 'input-jump-buffer-press-on-crossing-button-only-no-source-jump')
        self.assertEqual(completed['mode'], 'press-on-crossing')
        self.assertEqual(completed['frozenFrames'], 1)
        self.assertEqual(completed['crossingSampleIndex'], press['sampleIndex'])
        self.assertFalse(completed['actualJump'])
        self.assertFalse(completed['bufferConsumedByScene'])
        self.assertEqual(completed['sampledFrames'], len(frames))
        self.assertTrue(completed['inputSampled'])
        self.assertEqual(completed['inputSamplingProfile'], 'source-button-only')
        self.assertTrue(completed['keyboardButtonSampled'])
        self.assertFalse(completed['fullMInputUpdateExecuted'])
        self.assertFalse(completed['gamepadSampled'])
        self.assertFalse(completed['buttonsSampled'])
        self.assertTrue(completed['controlledEngineFreeze'])
        self.assertEqual(completed['callerPositionSpeedWrites'], 0)
        self.assertEqual(completed['callerFreezeDecrements'], 0)
        self.assertEqual(completed['callerSceneAdvances'], 0)
        self.assertEqual(completed['nativeAttempts'], 0)
        self.assertEqual(completed['nativeMappingsAfter'], [])
        self.assertEqual(completed['completedLifecycleFamilies'], 0)
        self.assertFalse(completed['hazardOrderingDirectionalCollisionDeathParity'])
        self.assertIn('not full MInput', completed['claim'])
        self.assertIn('no actual jump', completed['claim'])

    def test_input_jump_buffer_held_expiry_on_zero_crossing_skips_scene(self):
        rows = self.execute_input_jump_buffer('held-expired-on-crossing')
        self.assertFalse(any(row['event'] == 'boundary' for row in rows))
        self.assertNotIn('UnsupportedClosure', (self.output / 'input-jump-buffer-held-expired-on-crossing.stderr').read_text())
        freeze = next(row for row in rows if row['event'] == 'caller-input-jump-buffer-freeze')
        frames = [row for row in rows if row['event'] == 'caller-input-jump-buffer-frame']
        frozen = [row for row in frames if row['freezeBefore'] > 0]
        crossing = [row for row in frames if row['crossing']]
        completed = rows[-1]
        self.assertEqual(freeze['formula'], '8*RawDeltaTime')
        self.assertGreater(freeze['duration'], 0)
        self.assertLessEqual(len(frozen), 12)
        self.assertGreater(len(frozen), 1)
        self.assertEqual(len(crossing), 1)
        self.assertEqual(crossing[0], frozen[-1])
        press = frozen[0]
        self.assertTrue(press['afterUpdate']['pressed'])
        self.assertEqual(press['afterUpdate']['bufferCounter'], press['afterUpdate']['bufferTime'])
        expired = [row for row in frozen if row['afterUpdate']['bufferCounter'] <= 0]
        self.assertTrue(expired)
        cross = frozen[-1]
        self.assertFalse(cross['sceneRan'])
        self.assertEqual(cross['freezeAfter'], 0.0)
        self.assertTrue(cross['keys']['previousCDown'])
        self.assertTrue(cross['keys']['currentCDown'])
        self.assertTrue(cross['afterUpdate']['check'])
        self.assertFalse(cross['afterUpdate']['pressed'])
        self.assertFalse(cross['afterUpdate']['released'])
        self.assertLessEqual(cross['afterUpdate']['bufferCounter'], 0.0)
        self.assertEqual(cross['afterScene']['bufferCounter'], cross['afterUpdate']['bufferCounter'])
        resumed = frames[frames.index(cross) + 1]
        self.assertTrue(resumed['sceneRan'])
        self.assertEqual(resumed['freezeBefore'], 0.0)
        self.assertTrue(resumed['keys']['currentCDown'])
        self.assertTrue(resumed['afterUpdate']['check'])
        self.assertFalse(resumed['afterUpdate']['pressed'])
        self.assertFalse(resumed['afterUpdate']['released'])
        self.assertEqual(resumed['playerAfterScene']['state'], 0)
        self.assertFalse(resumed['playerAfterScene']['dead'])
        self.assertEqual(completed['status'], 'input-jump-buffer-held-expired-on-crossing-button-only-no-source-jump')
        self.assertEqual(completed['frozenFrames'], len(frozen))
        self.assertEqual(completed['crossingSampleIndex'], cross['sampleIndex'])
        self.assertFalse(completed['actualJump'])
        self.assertFalse(completed['bufferConsumedByScene'])
        self.assertTrue(completed['controlledEngineFreeze'])
        self.assertEqual(completed['nativeAttempts'], 0)
        self.assertEqual(completed['nativeMappingsAfter'], [])
        self.assertEqual(completed['completedLifecycleFamilies'], 0)

    def test_input_jump_buffer_release_on_zero_crossing_clears_and_resumes_neutral(self):
        rows = self.execute_input_jump_buffer('released-on-crossing')
        self.assertFalse(any(row['event'] == 'boundary' for row in rows))
        self.assertNotIn('UnsupportedClosure', (self.output / 'input-jump-buffer-released-on-crossing.stderr').read_text())
        freeze = next(row for row in rows if row['event'] == 'caller-input-jump-buffer-freeze')
        frames = [row for row in rows if row['event'] == 'caller-input-jump-buffer-frame']
        crossing = [row for row in frames if row['crossing']]
        completed = rows[-1]
        self.assertEqual(freeze['formula'], '2*RawDeltaTime')
        self.assertGreater(freeze['duration'], 0)
        self.assertGreaterEqual(len(frames), 3)
        self.assertEqual(len(crossing), 1)
        press = frames[0]
        self.assertFalse(press['sceneRan'])
        self.assertGreater(press['freezeBefore'], 0)
        self.assertTrue(press['keys']['currentCDown'])
        self.assertTrue(press['afterUpdate']['pressed'])
        self.assertEqual(press['afterUpdate']['bufferCounter'], press['afterUpdate']['bufferTime'])
        release = crossing[0]
        self.assertEqual(release['sampleIndex'], 1)
        self.assertFalse(release['sceneRan'])
        self.assertEqual(release['freezeAfter'], 0.0)
        self.assertTrue(release['keys']['previousCDown'])
        self.assertFalse(release['keys']['currentCDown'])
        self.assertFalse(release['afterUpdate']['check'])
        self.assertFalse(release['afterUpdate']['pressed'])
        self.assertTrue(release['afterUpdate']['released'])
        self.assertEqual(release['afterUpdate']['bufferCounter'], 0.0)
        self.assertEqual(release['afterScene']['bufferCounter'], 0.0)
        resumed = frames[2]
        self.assertTrue(resumed['sceneRan'])
        self.assertEqual(resumed['freezeBefore'], 0.0)
        self.assertFalse(resumed['keys']['previousCDown'])
        self.assertFalse(resumed['keys']['currentCDown'])
        self.assertFalse(resumed['afterUpdate']['check'])
        self.assertFalse(resumed['afterUpdate']['pressed'])
        self.assertFalse(resumed['afterUpdate']['released'])
        self.assertEqual(resumed['afterScene']['bufferCounter'], 0.0)
        self.assertEqual(resumed['playerAfterScene']['state'], 0)
        self.assertFalse(resumed['playerAfterScene']['dead'])
        self.assertEqual(completed['status'], 'input-jump-buffer-released-on-crossing-button-only-no-source-jump')
        self.assertTrue(completed['bufferLifecycle']['releaseClearedBuffer'])
        self.assertEqual(completed['frozenFrames'], 2)
        self.assertEqual(completed['crossingSampleIndex'], release['sampleIndex'])
        self.assertFalse(completed['actualJump'])
        self.assertTrue(completed['controlledEngineFreeze'])
        self.assertEqual(completed['callerFreezeDecrements'], 0)
        self.assertEqual(completed['nativeAttempts'], 0)
        self.assertEqual(completed['nativeMappingsAfter'], [])
        self.assertEqual(completed['completedLifecycleFamilies'], 0)

    def test_input_jump_buffer_caller_is_keyboard_only_without_full_input_or_motion_writes(self):
        text = (ROOT / 'tests/native/oracle/death/RoomCoreExecution.cs').read_text()
        start = text.index('static JumpInputSample SampleJumpButton')
        end = text.index('static void WriteDriverTick', start)
        caller = text[start:end]
        self.assertNotRegex(caller, r'\.(Position|Speed|PositionRemainder|Deaths|DeathsInCurrentLevel|TotalDeaths)\s*=[^=]')
        self.assertEqual(len(re.findall(r'Engine\.FreezeTimer\s*=[^=]', caller)), 1)
        self.assertNotIn('Engine.FreezeTimer -=', caller)
        self.assertNotIn('Math.Max(Engine.FreezeTimer', caller)
        for token in ('Settings.Instance.Jump.Add(Keys.C)', 'Input.Jump.Binding.Controller.Clear()',
                'Input.Initialize()', 'Input.Jump.Update()', 'fullMInputUpdateExecuted = false',
                'controlledEngineFreeze = true', 'inputSamplingProfile = "source-button-only"',
                'freezeDuration', 'frozenFrameGuard'):
            self.assertIn(token, caller)
        self.assertEqual(set(re.findall(r'Keys\.(\w+)', caller)), {'C'})
        for forbidden in ('Keyboard.GetState(', 'MInput.Update(', 'KeyboardData.Update(',
                'GamePadData.Update(', 'UpdateVirtualInputs(', 'ConsumeBuffer(', 'SetRepeat(',
                'RunStaticSpike', '.Die(', 'OnCollide('):
            self.assertNotIn(forbidden, caller)
