import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from check_native_oracle import ROOT, oracle_environment
from prepare_player_room_core_oracle import build
from room_core_frontier import SDK

PRIVATE = ROOT / '.audit/native-player-death-respawn'
DECLARATIONS = (46, 49, 52, 54, 56, 59, 61, 63, 65, 66, 71, 74, 75, 77, 78, 80, 81, 83, 85, 87, 89, 91)


@unittest.skipUnless(SDK.is_file() and (PRIVATE / 'room-core-probe-91/provenance.json').is_file()
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
        cls.compilation = build(PRIVATE / '5ffd25a49f1e12c6549aa34648308f41f42361e8/source',
            PRIVATE / 'room-core-probe-42', cls.output,
            declarations_source=[PRIVATE / f'room-core-probe-{number}' for number in DECLARATIONS] + [PRIVATE / 'room-core-platform-declarations-01', PRIVATE / 'room-core-declarations-extra-01'])

    def execute_case(self, name):
        result = subprocess.run([str(SDK), str(self.output / 'bin/Release/net8.0/Oracle.dll'), name,
            str(ROOT / '.audit/ilspy/inputs/Celeste.exe')], cwd=ROOT, env=oracle_environment(SDK), text=True, capture_output=True)
        (self.output / (name + '.stdout')).write_text(result.stdout)
        (self.output / (name + '.stderr')).write_text(result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

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
