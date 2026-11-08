import json
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


@unittest.skipUnless(SDK.is_file() and (PRIVATE / 'room-core-probe-91/provenance.json').is_file(),
    'Pinned private RoomCore declarations unavailable')
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
            declarations_source=[PRIVATE / f'room-core-probe-{number}' for number in DECLARATIONS])

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

    def test_source_bootstrap_stops_at_the_preserved_platform_initializer(self):
        trace = self.output / 'execution-prefix.jsonl'
        result = subprocess.run([str(SDK), str(self.output / 'bin/Release/net8.0/Oracle.dll'),
            'room-core-execute', str(trace)], cwd=ROOT, env=oracle_environment(SDK), text=True, capture_output=True)
        (self.output / 'execution-prefix.stdout').write_text(result.stdout)
        (self.output / 'execution-prefix.stderr').write_text(result.stderr)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(trace.is_file(), result.stdout + result.stderr)
        rows = [json.loads(line) for line in trace.read_text().splitlines()]
        self.assertIn({'event': 'enter', 'member': 'Monocle.Tracker.Initialize'}, rows)
        self.assertEqual(rows[-1]['event'], 'boundary')
        self.assertFalse(rows[-1]['loadLevelEntered'])
        self.assertIn('SDL2.SDL.INTERNAL_SDL_GetPlatform()', rows[-1]['exception'])
        self.assertIn('Celeste.Celeste..cctor()', rows[-1]['exception'])
        self.assertEqual([attempt['Library'] for attempt in rows[-1]['nativeAttempts']], ['SDL2'])
        self.assertEqual(rows[0]['nativeMappingsBefore'], [])
        self.assertEqual(rows[-1]['nativeMappingsAtBoundary'], [])
