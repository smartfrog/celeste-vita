import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / 'scripts'))
import native_room_replay as replay
from native_room_dash_runtime import verify_dash_probe_guest, dash_probe_completion_receipt
import test_dash_probe_feedback as dash_feedback
import test_guest_replay as guest_replay


def probe_fixture():
    return dict(id='first_room_dash_trails_v1', samples=360, exit_frame=359,
                source='src/vita/guest_dash_probe.hpp', sha256='3d34e2a2335db02f8ee6493eb44068a7bcd4ad7bbf33f414a8ecdc85df50c324')


def probe_completion():
    fixture = probe_fixture()
    return (f"complete revision=synthetic fixture={fixture['id']} fixture_sha256={fixture['sha256']} samples=360 exit_frame=359 "
            'clock=359 dash_events=1 max_trails=3 max_committed=3 max_captured=3 fresh_export=1 native_probe_checks=1 full_completion=1 '
            'input_source=scripted_guest_controls capture=dash_trails graphics_teardown=1 log_closed=1 status=0\n')


def probe_log(receipt=None):
    fixture = probe_fixture()
    rows = ['Celeste native room DIAGNOSTIC boot revision=synthetic fixed_step=1/60',
            f"guest dash probe fixture={fixture['id']} fixture_sha256={fixture['sha256']} input_source=scripted_guest_controls samples=360 exit_frame=359 physical_controller_verified=false host_input_injected=false capture_policy=dash_trails",
            'assets ready', 'capture policy=dash_trails', 'frame ready']
    if receipt is None:
        receipt = f"frame_saved path=ux0:data/celeste_native_room-synthetic-dash-probe.ppm revision=synthetic frame=60 capture=dash_trails stage=after_draw_glFinish_GL_BACK_RGBA_CPU_before_swap probe_fixture={fixture['id']} probe_fixture_sha256={fixture['sha256']} native_probe_checks=1"
    for frame in range(360):
        trails = sum(frame >= start for start in (43,48,58)) if frame < 100 else 0
        committed = sum(frame >= start for start in (44,49,59)) if frame < 100 else 0
        captured = sum(frame >= start for start in (45,49,59)) if frame < 100 else 0
        fields = dict(fixture=fixture['id'], frame=frame, left=0, right=0, up=int(40 <= frame < 60), down=0,
                      cross=0, triangle=0, start=int(frame==359), square=int(frame==40), l=0, jump=0,
                      jump_pressed=0, jump_released=0, dash=int(frame==40), dash_pressed=int(frame==40),
                      dash_released=int(frame==41), grab=0, reset=0, exit=int(frame==359), x=0,
                      y=-int(40 <= frame < 60), aim_x=0, aim_y=-int(40 <= frame < 60),
                      state=14 if frame < 35 else 2 if 40 <= frame < 58 else 0, dead=0,
                      clock=min(frame+1,359), dash_events=int(frame>=43), trails=trails,
                      committed_trails=committed, captured_trails=captured,
                      fresh_export=int(frame>=60), native_probe_checks=int(frame>=60))
        rows.append('guest_dash_probe '+' '.join(f'{key}={value}' for key,value in fields.items()))
        if frame == 59:
            rows.append(receipt.rstrip('\n'))
    rows += ['clean exit frame=359 dead=0 resets=0 state=0',
             'guest_dash_probe_complete '+probe_completion().split(' ',1)[1].split(' input_source=',1)[0]+' graphics_teardown=1']
    return '\n'.join(rows)+'\n'


class DashProbeGuestTests(unittest.TestCase):
    def test_new_imported_runtime_dependency_is_fingerprinted_in_every_mode(self):
        original = Path.read_bytes
        def changed(path):
            data = original(path)
            return data+b'\n' if path.name=='native_room_dash_runtime.py' else data
        for mode in ({},{'automatic':True},{'dash_probe':True}):
            with self.subTest(mode=mode):
                before = replay.harness_fingerprint(**mode)
                with patch.object(Path,'read_bytes',changed):
                    self.assertNotEqual(before,replay.harness_fingerprint(**mode))

    def verify(self,text=None,receipt=None,fixture=None,frame=None):
        return verify_dash_probe_guest(text if text is not None else probe_log(), 'synthetic', fixture or probe_fixture(),
                                       receipt if receipt is not None else probe_completion(),frame)

    def test_closed_receipt_matches_actual_producer_wire_format(self):
        self.assertEqual(dash_probe_completion_receipt('synthetic',probe_fixture()),probe_completion())

    def test_complete_producer_shaped_contract_is_recomputed(self):
        proof = self.verify()
        self.assertEqual((proof['samples'],proof['exit_frame'],proof['clock']), (360,359,359))
        self.assertEqual(proof['capture_frame'],60)
        self.assertFalse(proof['physical_proof'])

    def test_sample_corruption_fails_parameterized(self):
        text = probe_log()
        lines = text.splitlines(keepends=True)
        sample = next(line for line in lines if line.startswith('guest_dash_probe ') and ' frame=40 ' in line)
        mutations = {'missing':text.replace(sample,''), 'duplicate':text.replace(sample,sample+sample),
                     'reordered':text.replace(' frame=40 ',' frame=41 '), 'truncated':text.rstrip('\n'),
                     'wrong_input':text.replace('frame=40 left=0','frame=40 left=1'),
                     'missing_field':text.replace('frame=40 left=0','frame=40'),
                     'no_initial_respawn':text.replace('state=14','state=0'),
                     'late_boot':text.replace(lines[0],'').replace('clean exit ',lines[0]+'clean exit ',1),
                     'wrong_aim':text.replace('aim_y=-1','aim_y=0'),
                     'wrong_edge':text.replace('dash_pressed=1','dash_pressed=0'),
                     'wrong_clock':text.replace('clock=41 ','clock=42 '),
                     'terminal_update':text.replace('clock=359 dash_events=1 trails=0 committed_trails=0 captured_trails=0 fresh_export=1 native_probe_checks=1\nclean exit',
                                                    'clock=360 dash_events=1 trails=0 committed_trails=0 captured_trails=0 fresh_export=1 native_probe_checks=1\nclean exit'),
                     'no_dash':text.replace('dash_events=1','dash_events=0'),
                     'no_three_trails':text.replace('trails=3','trails=2'),
                     'no_export':text.replace('fresh_export=1','fresh_export=0'),
                     'failed_probe':text.replace('native_probe_checks=1','native_probe_checks=0'),
                     'dead':text.replace('dead=0','dead=1'),
                     'wrong_boot':text.replace('boot revision=synthetic','boot revision=stale'),
                     'wrong_hash':text.replace(probe_fixture()['sha256'],'0'*64),
                     'wrong_fixture':text.replace(probe_fixture()['id'],'first_room_auto_death_v2'),
                     'bad_summary':text.replace('max_captured=3','max_captured=2'),
                     'no_teardown':text.replace('graphics_teardown=1','graphics_teardown=0'),
                     'duplicate_field':text.replace('frame=40 left=0','frame=40 frame=40 left=0'),
                     'early_fresh':text.replace('fresh_export=0','fresh_export=1'),
                     'fatal_state_restore':text+'FATAL: Trail pass failed native GL state restoration\n'}
        for label,mutated in mutations.items():
            with self.subTest(label=label), self.assertRaises(ValueError):
                self.verify(text=mutated)

    def test_closed_completion_corruption_fails_parameterized(self):
        good = probe_completion()
        for receipt in (good.rstrip('\n'),good.replace('log_closed=1','log_closed=0'),
                        good.replace('status=0','status=1'),good.replace('samples=360','samples=359'),
                        good.replace('capture=dash_trails','capture=initial_respawn'),
                        replay.completion_receipt('synthetic',automatic=True)):
            with self.subTest(receipt=receipt), self.assertRaises(ValueError):
                self.verify(receipt=receipt)

    def test_export_identity_is_bound_to_logged_receipt_and_fixture(self):
        fields = dict(token.split('=',1) for token in next(line for line in probe_log().splitlines() if line.startswith('frame_saved ')).split()[1:])
        for key,value in (('probe_fixture_sha256','0'*64),('frame','61'),('capture','spawn')):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.verify(frame={'receipt_fields':fields | {key:value},'frame_state':{'frame':60}})


class DashProbeSourceTests(unittest.TestCase):
    def setUp(self):
        directory = ROOT / '.audit/native-room-vita/dash-source-tests'
        directory.mkdir(parents=True,exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=directory)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        header = self.root / replay.DASH_PROBE_SOURCE
        header.parent.mkdir(parents=True)
        header.write_bytes(b'generated host source identity fixture\n')
        self.fixture = probe_fixture() | {'sha256':hashlib.sha256(header.read_bytes()).hexdigest()}
        self.provenance = dict(guest_dash_probe=self.fixture['id'],guest_dash_probe_fixture=self.fixture,
                               guest_replay=None,guest_automatic=None,render_style='animated_player_partial',
                               player={'death_animation_extension':True},visuals={'spike_textures':['up','left']},decals={'static':22})
        self.vpk = self.root / 'synthetic.vpk'
        self.vpk.write_bytes(b'generated host package bytes')
        source = {'schema':1,'state_sha256':'synthetic-complete-source'}
        self.package = dict(staging=self.provenance,source_before=source,source_after=source,exact_wip=True,
                            vpk_sha256=hashlib.sha256(self.vpk.read_bytes()).hexdigest(),
                            build_binding=dict(source=source,self_matches_rebuilt_chain=True,capture_policy='dash_trails'))

    def verify(self,expected=None,package=None):
        with patch('native_room_replay.subprocess.run',return_value=SimpleNamespace(stdout=json.dumps(package or self.package))) as run, \
             patch('native_room_replay.source_state',return_value=('synthetic',[])):
            selected = replay.verify_dash_probe_source(self.provenance,self.vpk,self.root,self.root/'build/src/vita',self.root/'staging',expected)
        return selected,run.call_args

    def test_actual_native_verifier_receives_explicit_wip_and_source_paths(self):
        selected,call = self.verify(self.root/'expected.json')
        self.assertEqual(selected['fixture'],self.fixture)
        self.assertEqual(call.kwargs['cwd'],self.root)
        self.assertIn(str(self.root/'scripts/verify_native_room_vpk.py'),call.args[0])
        self.assertEqual(call.args[0][-2:],['--expected-source-state',str(self.root/'expected.json')])

    def test_strict_default_rejects_wip_without_opt_in(self):
        with self.assertRaisesRegex(ValueError,'explicit'):
            self.verify()

    def test_clean_default_does_not_forward_wip(self):
        _,call = self.verify(package=self.package | {'exact_wip':False})
        self.assertNotIn('--expected-source-state',call.args[0])

    def test_source_resident_and_capture_mutations_fail_parameterized(self):
        for key in ('source','capture','self','vpk','staging','fixture'):
            package = copy.deepcopy(self.package)
            if key=='source': package['source_after'] = {'changed':True}
            if key=='capture': package['build_binding']['capture_policy'] = 'initial_respawn'
            if key=='self': package['build_binding']['self_matches_rebuilt_chain'] = False
            if key=='vpk': package['vpk_sha256'] = 'stale'
            if key=='staging': package['staging']['guest_dash_probe'] = None
            if key=='fixture': self.provenance['guest_dash_probe_fixture'] = self.fixture | {'sha256':'0'*64}
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.verify(self.root/'expected.json',package)
            self.provenance['guest_dash_probe_fixture'] = self.fixture

    def test_native_verifier_failure_has_no_fallback(self):
        error = subprocess.CalledProcessError(1,['native verifier'],stderr='resident source mismatch')
        with patch('native_room_replay.subprocess.run',side_effect=error) as run, self.assertRaisesRegex(ValueError,'resident source mismatch'):
            replay.verify_dash_probe_source(self.provenance,self.vpk,self.root,self.root/'build',self.root/'staging')
        self.assertEqual(run.call_count,1)


class DashProbeBoundaryTests(unittest.TestCase):
    setUp = dash_feedback.DashProbeFeedbackTests.setUp
    set_pixel = dash_feedback.DashProbeFeedbackTests.set_pixel
    set_raw = dash_feedback.DashProbeFeedbackTests.set_raw
    prepare_probe = dash_feedback.DashProbeFeedbackTests.prepare_probe
    run_scenario = guest_replay.ReplayHostBoundaryTests.run_scenario

    def bundle(self):
        self.prepare_probe()
        self.metadata['frame'] = 60
        self.set_pixel(40,543,[23,35,47])
        receipt = 'frame_saved '+' '.join(f'{key}={value}' for key,value in self.metadata.items())+'\n'
        return dict(ppm=b'P6\n960 544\n255\n'+self.pixels,receipt=receipt,raw=self.raw,log=probe_log(receipt),
                    provenance=dict(render_style='animated_player_partial',visuals=self.visuals,player=self.player,decals=self.decals))

    def test_full_fresh_bundle_passes_existing_guest_only_owned_runtime_path(self):
        feedback,order = self.run_scenario('complete',dash_probe=True,frame_fixture=self.bundle())
        self.assertEqual(order,['installer'])
        self.assertTrue(feedback['stages']['full_completion'])
        self.assertEqual(feedback['guest_dash_probe_observed']['samples'],360)
        self.assertFalse(feedback['frame']['black_letterbox_rows'])
        self.assertFalse(feedback['frame']['dash_probe']['physical_proof'])

    def test_runtime_guards_leave_dash_partial_parameterized(self):
        for mode in ('no_frame','unclosed_frame','skip_existing','bad_receipt','missing_events','guest_failure',
                     'source_drift','source_verify_failure','config_mutation','wrong_mode_completion'):
            with self.subTest(mode=mode):
                feedback,_ = self.run_scenario(mode,dash_probe=True,frame_fixture=self.bundle())
                self.assertFalse(feedback['stages']['full_completion'])

    def test_other_modes_failure_path_cannot_fail_dash(self):
        feedback,_ = self.run_scenario('wrong_mode_failure',dash_probe=True,frame_fixture=self.bundle())
        self.assertTrue(feedback['stages']['full_completion'])

    def test_owned_host_status_is_binding_parameterized(self):
        for mode,status in (('host_failure',133),('host_timeout',None)):
            with self.subTest(mode=mode):
                feedback,_ = self.run_scenario(mode,host_exit_code=status,dash_probe=True,frame_fixture=self.bundle())
                self.assertTrue(feedback['stages']['input'])
                self.assertFalse(feedback['stages']['full_completion'])

    def test_failure_published_during_final_host_wait_rejects_completed_dash_parameterized(self):
        for kind in ('regular','symlink','dangling_symlink','unknown'):
            with self.subTest(kind=kind):
                feedback,order = self.run_scenario('complete',dash_probe=True,frame_fixture=self.bundle(),late_failure_kind=kind)
                self.assertEqual(order,['installer'])
                self.assertEqual([event['host_exit_code'] for event in feedback['host_events'] if 'host_exit_code' in event],[0])
                self.assertFalse(feedback['stages']['full_completion'],json.dumps({key:feedback[key] for key in ('stages','errors','late_failure_event','raised_error')}))
                self.assertIsNotNone(feedback['raised_error'])
                self.assertTrue(any(error['stage']=='guest_failure_after' for error in feedback['errors']))
                self.assertEqual(feedback['late_failure_event']['phase'],'host_wait')

    def test_failure_published_during_owned_cleanup_is_checked_parameterized(self):
        for kind in ('regular','symlink','dangling_symlink'):
            with self.subTest(kind=kind):
                feedback,order = self.run_scenario('host_timeout',host_exit_code=None,cleanup_exit_code=0,dash_probe=True,
                                                   frame_fixture=self.bundle(),late_failure_kind=kind,late_failure_phase='cleanup')
                self.assertEqual(order,['installer','runtime'])
                self.assertEqual(feedback['host_events'][-1]['host_exit_code'],0)
                self.assertFalse(feedback['stages']['full_completion'])
                self.assertTrue(any(error['stage']=='guest_failure_after' for error in feedback['errors']))
                self.assertEqual(feedback['raised_error']['type'],'RuntimeError')
                self.assertEqual(feedback['late_failure_event']['phase'],'cleanup')

    def test_late_failure_rejects_old_scripted_modes_parameterized(self):
        for arguments in ({'automatic':True},{}):
            with self.subTest(arguments=arguments):
                feedback,_ = self.run_scenario('complete',late_failure_kind='regular',**arguments)
                self.assertFalse(feedback['stages']['full_completion'],json.dumps({key:feedback[key] for key in ('stages','errors','late_failure_event','raised_error')}))
                self.assertIsNotNone(feedback['raised_error'])
                self.assertTrue(any(error['stage']=='guest_failure_after' for error in feedback['errors']))

    def test_existing_dash_artifacts_are_rejected_before_install_parameterized(self):
        from smoke_native_room import main
        bundle = self.bundle()
        for name in ('celeste_native_room.log','celeste_native_room.ready',
                     'celeste_native_room-synthetic-dash-probe.ppm','celeste_native_room-synthetic-dash-probe.ppm.txt',
                     'celeste_native_room-synthetic-dash-probe.ppm.trail.rgba',
                     'celeste_native_room-complete-synthetic-dash-probe.txt','celeste_native_room-failure-synthetic-dash-probe.txt'):
            with self.subTest(name=name):
                root = self.root / name
                fs = root / 'state'
                data = fs / 'ux0/data'
                data.mkdir(parents=True)
                stale = data / name
                stale.write_bytes(b'prior evidence retained')
                config = root / 'config.yml'
                config.write_text('synthetic private config\n')
                vpk = root / 'synthetic.vpk'
                provenance = dict(revision='synthetic',tracked_changes=False,guest_replay=None,guest_automatic=None,
                                  guest_dash_probe=probe_fixture()['id'],guest_dash_probe_fixture=probe_fixture(),**bundle['provenance'])
                with zipfile.ZipFile(vpk,'w') as package:
                    package.writestr('assets/native-room/provenance.json',json.dumps(provenance))
                selected = dict(fixture=probe_fixture(),package=dict(vpk_sha256=hashlib.sha256(vpk.read_bytes()).hexdigest(),build_binding={'capture_policy':'dash_trails'}))
                output = ROOT / '.audit/native-room-vita/dash-stale-tests' / self.root.name / name
                args = ['smoke','--guest-dash-probe','--state',str(fs),'--output',str(output),'--vpk',str(vpk),
                        '--source-root',str(root),'--build',str(root/'build'),'--staging',str(root/'staging')]
                with patch('sys.argv',args), \
                     patch('smoke_native_room.verify_dash_probe_source',return_value=selected), \
                     patch('smoke_native_room.launcher_kind',return_value='linuxdeploy'), \
                     patch('smoke_native_room.launch_command',return_value=(['bwrap'],{})), \
                     patch('smoke_native_room.prepare',return_value=(fs,config)), \
                     patch('smoke_native_room.subprocess.Popen',side_effect=AssertionError('No stale state installation')) as spawn, \
                     self.assertRaisesRegex(ValueError,'fresh.*Dash|Dash.*fresh'):
                    main()
                spawn.assert_not_called()
                self.assertEqual(stale.read_bytes(),b'prior evidence retained')

    def test_prior_feedback_cannot_supply_a_dash_frame(self):
        from smoke_native_room import main
        from native_room_feedback import new_feedback
        directory = ROOT / '.audit/native-room-vita/dash-feedback-tests' / self.root.name
        directory.mkdir(parents=True)
        vpk = directory / 'synthetic.vpk'
        provenance = dict(revision='synthetic',tracked_changes=False,guest_replay=None,guest_automatic=None,
                          guest_dash_probe=probe_fixture()['id'],guest_dash_probe_fixture=probe_fixture(),**self.bundle()['provenance'])
        with zipfile.ZipFile(vpk,'w') as package:
            package.writestr('assets/native-room/provenance.json',json.dumps(provenance))
        prior = new_feedback('synthetic',vpk)
        prior['stages']['native_image'] = True
        prior['frame'] = {'prior':True}
        feedback_path = directory / 'prior-feedback.json'
        feedback_path.write_text(json.dumps(prior))
        args = ['smoke','--guest-dash-probe','--state',str(directory/'state'),'--output',str(directory/'output'),
                '--vpk',str(vpk),'--feedback',str(feedback_path),'--source-root',str(self.root),
                '--build',str(self.root/'build'),'--staging',str(self.root/'staging')]
        selected = dict(package=dict(vpk_sha256=hashlib.sha256(vpk.read_bytes()).hexdigest(),build_binding={'capture_policy':'dash_trails'}))
        with patch('sys.argv',args),patch('smoke_native_room.prepare',side_effect=AssertionError('Prior feedback reached state preparation')) as prepare, \
             patch('smoke_native_room.verify_dash_probe_source',return_value=selected), \
             patch('smoke_native_room.launcher_kind',return_value='linuxdeploy'), \
             self.assertRaisesRegex(ValueError,'fresh.*feedback'):
            main()
        prepare.assert_not_called()
        self.assertEqual(json.loads(feedback_path.read_text()),prior)
