"""Validate the frozen Dash producer's input observations and closed completion."""

import re
from native_room_replay import DASH_PROBE_ID, DASH_PROBE_SOURCE, dash_probe_intent, dash_probe_inputs

SAMPLE_KEYS = frozenset(('fixture frame left right up down cross triangle start square l jump jump_pressed '
                         'jump_released dash dash_pressed dash_released grab reset exit x y aim_x aim_y state dead '
                         'clock dash_events trails committed_trails captured_trails fresh_export native_probe_checks').split())
SUMMARY_KEYS = frozenset(('revision fixture fixture_sha256 samples exit_frame clock dash_events max_trails '
                          'max_committed max_captured fresh_export native_probe_checks full_completion graphics_teardown').split())


def verify_fixture(fixture):
    if not isinstance(fixture,dict) or not isinstance(fixture.get('sha256'),str):
        raise ValueError('Dash fixture requires a header identity object')
    expected = dict(id=DASH_PROBE_ID, samples=360, exit_frame=359, source=DASH_PROBE_SOURCE)
    if (set(fixture) != set(expected) | {'sha256'} or any(fixture.get(k) != v for k,v in expected.items()) or
            not re.fullmatch(r'[0-9a-f]{64}',fixture.get('sha256',''))):
        raise ValueError('Dash fixture lacks the exact input-header identity')


def verify_dash_probe_intent(provenance, enabled, root=None):
    intent = provenance.get('guest_dash_probe')
    fixture = provenance.get('guest_dash_probe_fixture')
    if not enabled:
        if intent is not None or fixture is not None:
            raise ValueError('Disabled Dash mode cannot carry Dash intent or fixture pins')
        return
    if intent != DASH_PROBE_ID or provenance.get('guest_replay') or provenance.get('guest_automatic'):
        raise ValueError('Dash probe intent differs from requested exclusive guest mode')
    if not isinstance(fixture,dict):
        raise ValueError('Missing staged Dash fixture')
    verify_fixture(fixture)
    if root is not None and fixture != dash_probe_intent(root):
        raise ValueError('Staged Dash fixture hash differs from authoritative source')
    if provenance.get('render_style') != 'animated_player_partial' or not provenance.get('player'):
        raise ValueError('Dash probe requires the production animated Player profile')


def completion_fields(revision, fixture):
    verify_fixture(fixture)
    if not re.fullmatch(r'[A-Za-z0-9._-]{1,192}',revision):
        raise ValueError('Invalid bounded Dash revision')
    return (f"revision={revision} fixture={DASH_PROBE_ID} fixture_sha256={fixture['sha256']} samples=360 exit_frame=359 "
            'clock=359 dash_events=1 max_trails=3 max_committed=3 max_captured=3 fresh_export=1 native_probe_checks=1 full_completion=1')


def dash_probe_completion_receipt(revision, fixture):
    return ('complete '+completion_fields(revision,fixture)+
            ' input_source=scripted_guest_controls capture=dash_trails graphics_teardown=1 log_closed=1 status=0\n')


def record_fields(line, prefix, keys=None, strings=()):
    if not line.startswith(prefix):
        raise ValueError('Wrong Dash record prefix')
    fields = {}
    for token in line[len(prefix):].split():
        key,separator,value = token.partition('=')
        if not separator or not value or key in fields:
            raise ValueError('Malformed or duplicate Dash record field')
        fields[key] = value
    if keys is not None and set(fields) != keys:
        raise ValueError('Dash record keys differ from the frozen producer contract')
    if keys is not None:
        for key in fields.keys() - set(strings):
            if not re.fullmatch(r'0|-?[1-9][0-9]{0,19}',fields[key]):
                raise ValueError('Invalid canonical Dash integer: '+key)
            fields[key] = int(fields[key])
    return fields


def verify_dash_probe_guest(text, revision, fixture, closed_receipt, frame=None):
    verify_fixture(fixture)
    if closed_receipt != dash_probe_completion_receipt(revision,fixture):
        raise ValueError('Dash closed completion differs from its exact source/teardown/log contract')
    if len(text.encode()) > 1_000_000 or not text.endswith('\n') or '\0' in text or 'FATAL' in text:
        raise ValueError('Truncated, oversized or failed Dash guest log')
    if any(marker in text for marker in ('guest automatic ', 'guest_automatic', 'guest replay ', 'manual reset ', 'capture_skipped_existing ')):
        raise ValueError('Dash log contains a wrong-mode/manual/stale-export record')
    lines = text.splitlines()
    boot = [line for line in lines if 'DIAGNOSTIC boot revision=' in line]
    expected_boot = f'Celeste native room DIAGNOSTIC boot revision={revision} fixed_step=1/60'
    if len(boot) != 1 or not (boot[0] == expected_boot or boot[0].startswith(expected_boot+' ')):
        raise ValueError('Dash boot revision differs from the bound package')
    marker = (f"guest dash probe fixture={DASH_PROBE_ID} fixture_sha256={fixture['sha256']} input_source=scripted_guest_controls "
              'samples=360 exit_frame=359 physical_controller_verified=false host_input_injected=false capture_policy=dash_trails')
    if [line for line in lines if line.startswith('guest dash probe')] != [marker]:
        raise ValueError('Dash boot fixture/hash/input-source receipt differs')
    if [line for line in lines if line.startswith('capture policy=')] != ['capture policy=dash_trails']:
        raise ValueError('Dash guest lacks its resident capture policy receipt')
    for startup in ('assets ready','frame ready'):
        if sum(line.startswith(startup) for line in lines) != 1:
            raise ValueError('Dash guest lacks unique startup marker: '+startup)
    samples,offsets,exports,summaries = [],[],[],[]
    for offset,line in enumerate(lines):
        if line.startswith('guest_dash_probe '):
            if len(line.encode()) > 767 or summaries:
                raise ValueError('Oversized Dash sample or sample after completion')
            samples.append(record_fields(line,'guest_dash_probe ',SAMPLE_KEYS,{'fixture'}))
            offsets.append(offset)
        elif line.startswith('guest_dash_probe_complete '):
            if len(line.encode()) > 767:
                raise ValueError('Oversized Dash summary')
            summaries.append((offset,record_fields(line,'guest_dash_probe_complete ',SUMMARY_KEYS,{'revision','fixture','fixture_sha256'})))
        elif line.startswith('guest_dash_probe'):
            raise ValueError('Malformed Dash observation prefix')
        elif line.startswith('frame_saved '):
            exports.append((offset,record_fields(line,'frame_saved ')))
    if len(samples) != 360 or len(summaries) != 1 or len(exports) != 1:
        raise ValueError('Dash requires exactly 360 observations, one export and one summary')
    startup_offsets = [lines.index(boot[0]),lines.index(marker),
                       next(i for i,line in enumerate(lines) if line.startswith('assets ready')),
                       lines.index('capture policy=dash_trails'),
                       next(i for i,line in enumerate(lines) if line.startswith('frame ready')),offsets[0]]
    if startup_offsets != sorted(startup_offsets) or samples[0]['state']!=14:
        raise ValueError('Dash startup must precede its observed fresh Respawn14 session')
    previous = None
    phases = [14]
    max_counts = dict(trails=0,committed_trails=0,captured_trails=0)
    fresh_frames = []
    inputs = dash_probe_inputs()
    for index,(sample,controls) in enumerate(zip(samples,inputs,strict=True)):
        expected = dict(fixture=DASH_PROBE_ID,frame=index,left=0,right=0,up=int(controls['y']==-1),down=0,cross=0,triangle=0,
                        start=controls['exit'],square=controls['dash'],l=0,jump_pressed=0,jump_released=0,
                        dash_pressed=controls['dash'],dash_released=int(index>0 and inputs[index-1]['dash'] and not controls['dash']),
                        grab=0,aim_x=controls['x'],aim_y=controls['y'],
                        clock=min(index+1,359),dead=0)
        expected.update(controls)
        if any(sample[key] != value for key,value in expected.items()):
            raise ValueError('Dash input/buttons/edges/aim/order/clock differ from the pinned fixture')
        state = sample['state']
        if state != phases[-1]:
            phases.append(state)
        if phases not in ([14],[14,0],[14,0,2],[14,0,2,0]) or (state==2 and index<40):
            raise ValueError('Dash observations lack ordered Respawn14/Normal/Dash/Normal phases')
        if index==40 and state!=2:
            raise ValueError('Dash input did not enter the live Dash state')
        events = sample['dash_events']
        if events not in (0,1) or (index<40 and events) or (previous and events<previous['dash_events']):
            raise ValueError('Dash observations lack one monotonic input-driven launch')
        if events and (previous is None or not previous['dash_events']) and state != 2:
            raise ValueError('Dash launch event occurred outside Dash')
        for key in max_counts:
            value = sample[key]
            if not 0<=value<=3 or value>sample['trails'] or (value and not events):
                raise ValueError('Invalid occupied/committed/captured Dash trail counts')
            if previous and previous['fresh_export'] and value>previous[key]:
                raise ValueError('Dash trail count increased after its single captured burst')
            max_counts[key] = max(max_counts[key],value)
        fresh = sample['fresh_export']
        if fresh not in (0,1) or sample['native_probe_checks']!=fresh or (previous and fresh<previous['fresh_export']):
            raise ValueError('Dash fresh-export/native-probe checks are invalid or not monotonic')
        if fresh:
            fresh_frames.append(index)
        if index==359 and any(sample[key]!=previous[key] for key in ('state','dead','clock','dash_events',*max_counts,'fresh_export','native_probe_checks')):
            raise ValueError('Dash terminal observation updated the session')
        previous = sample
    if phases != [14,0,2,0] or previous['dash_events']!=1 or set(max_counts.values())!={3} or not fresh_frames:
        raise ValueError('Dash did not observe one complete live Dash and three committed/captured trails')
    capture_frame = fresh_frames[0]
    if not 40<capture_frame<359 or any(samples[capture_frame-1][key]!=3 for key in max_counts):
        raise ValueError('Fresh Dash export lacks three preceding occupied/committed/captured trails')
    export_offset,export = exports[0]
    expected_export = dict(path=f'ux0:data/celeste_native_room-{revision}-dash-probe.ppm',revision=revision,frame=str(capture_frame),
                           capture='dash_trails',stage='after_draw_glFinish_GL_BACK_RGBA_CPU_before_swap',
                           probe_fixture=DASH_PROBE_ID,probe_fixture_sha256=fixture['sha256'],native_probe_checks='1')
    if any(export.get(key)!=value for key,value in expected_export.items()) or not offsets[capture_frame-1]<export_offset<offsets[capture_frame]:
        raise ValueError('Dash export identity/timing differs from source and observed fresh capture')
    if frame is not None and (frame.get('receipt_fields')!=export or frame.get('frame_state',{}).get('frame')!=capture_frame):
        raise ValueError('Dash actual closed export differs from the guest log/fixture')
    summary_offset,summary = summaries[0]
    expected_summary = record_fields('guest_dash_probe_complete '+completion_fields(revision,fixture)+' graphics_teardown=1',
                                     'guest_dash_probe_complete ',SUMMARY_KEYS,{'revision','fixture','fixture_sha256'})
    if summary!=expected_summary or summary_offset<=offsets[-1] or any(line for line in lines[summary_offset+1:]):
        raise ValueError('Dash summary differs from recomputed observations or is not terminal')
    clean = [(i,line) for i,line in enumerate(lines) if line.startswith('clean exit ')]
    if len(clean)!=1 or not offsets[-1]<clean[0][0]<summary_offset or any(re.findall(r'\b'+key+r'=(\d+)\b',clean[0][1])!=[str(value)] for key,value in dict(frame=359,dead=0,resets=0,state=0).items()):
        raise ValueError('Dash lacks its unique observed final live clean exit')
    return dict(markers=['guest_dash_probe_complete','clean exit'],samples=360,exit_frame=359,clock=359,
                capture_frame=capture_frame,max_trails=3,max_committed=3,max_captured=3,physical_proof=False,
                scope='source_bound_runtime_contract_not_compositing_acceptance')
