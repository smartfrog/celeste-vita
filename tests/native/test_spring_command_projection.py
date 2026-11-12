"""Read-only 514-frame Spring command oracle, bounded to the observed zero-reload route."""
import copy
import json
import os
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from prepare_spring_material_catalog import AUDIT,PINS
from prepare_native_transition_fixture import room_records
from test_spike_command_projection import ROOMS,ROOMS_IDENTITY,float32,require
from test_native_gameplay_draw_projection import SOURCE_TRACE,SOURCE_IDENTITY,file_identity,sample_source,source_keys,native_keys

NATIVE=Path(os.environ.get('CELESTE_SPRING_NATIVE_TRACE',AUDIT/'command-implementation-01/combined-release-01.stdout'))
CATALOG=Path(os.environ.get('CELESTE_SPRING_CATALOG',AUDIT/'command-implementation-01/descriptor-01/catalog.txt'))
OFFSETS=[(x,y) for x in range(-1,2) for y in range(-1,2) if x or y]+[(0,0)]
FRAMES=514
SEMANTIC=('2',12)


def read_catalog(path):
    lines=path.read_text().splitlines()
    require(len(lines)==11 and lines[:10]==['CSPR1',*PINS.values(),'floor idle 0 0','1'],'Spring catalog provenance/schema changed')
    fields=lines[10].split()
    require(len(fields)==10,'Invalid Spring frame shape')
    x,y,w,h,ox,oy,fw,fh=map(int,fields[1:9])
    require(0<=x<=4096-w and 0<=y<=4096-h and w>0 and h>0 and
            0<=-ox<=fw-w and 0<=-oy<=fh-h,'Invalid Spring crop/trim')
    return {'texture':fields[9],'sheet':fields[0],'sourceRectangle':[x,y,w,h],'origin':[fw/2+ox,fh+oy]}


def read_source(path):
    require(file_identity(path)==SOURCE_IDENTITY,'Frozen SOURCE trace changed')
    require(file_identity(ROOMS)==ROOMS_IDENTITY,'Pinned authored rooms changed')
    authored=[(room['name'],obj) for room in room_records(json.loads(ROOMS.read_text()))
              for obj in room['objects'] if obj[0]=='spring']
    require(len(authored)==1 and (authored[0][0],authored[0][1][1])==SEMANTIC and authored[0][1][2:4]==[360,-40],
            'Independent authored Floor Spring binding changed')
    frames={};current=None
    with path.open() as stream:
        for line in stream:
            if not line.startswith('{"event":"draw-'):continue
            row=json.loads(line);tick=row['tick'];event=row['event']
            if event=='draw-state' and row['phase']=='before-draw':
                require(current is None and tick==len(frames),'SOURCE frame chronology changed')
                owners=[owner for owner in row['state']['entities'] if owner['type']=='Spring']
                current={'commands':[],'owners':owners,'spans':[]}
            elif event=='draw-command' and row['owner']['type']=='Spring':
                require(current is not None and tick==len(frames),'Unbound SOURCE Spring command')
                current['commands'].append(dict(row,room=SEMANTIC[0],authoredId=SEMANTIC[1]))
            elif event=='draw-dispatch':
                require(current is not None and tick==len(frames),'Unbound SOURCE Spring dispatch')
                current['spans']=[span for span in row['entities'] if span['type']=='Spring']
            elif event=='draw-state' and row['phase']=='after-draw':
                require(current is not None and tick==len(frames),'Unfinished SOURCE Spring frame')
                frames[tick]=current;current=None
    require(current is None and list(frames)==list(range(FRAMES)),'Incomplete SOURCE route')
    stable=None
    for tick,frame in frames.items():
        reached=tick>=374
        require(len(frame['commands'])==9*reached and len(frame['owners'])==len(frame['spans'])==int(reached),'SOURCE Spring lifetime/count changed')
        if not reached:continue
        owner=frame['owners'][0];span=frame['spans'][0];components=owner['components']
        require(owner['position']==authored[0][1][2:4] and owner['Visible'] and owner['Collidable'] and owner['springWiggler']==0,
                'SOURCE Spring does not bind pinned idle authored owner')
        require([component['type'] for component in components]==['PlayerCollider','HoldableCollider','PufferCollider','Sprite','StaticMover','Wiggler']
                and not components[5]['Active'],'SOURCE Spring component order/wiggler changed')
        binding=(owner['id'],components[3]['id'])
        require(stable is None or stable==binding,'SOURCE Spring zero-reload lifetime changed');stable=binding
        require(span['entity']==owner['id'] and [command['index'] for command in frame['commands']]==list(range(span['drawStart'],span['drawEnd'])),
                'SOURCE Spring dispatch span changed')
        for piece,command in enumerate(frame['commands']):
            attribution=command['owner']
            require(attribution['entity']==owner['id'] and attribution['component']==(components[3]['id'] if piece==8 else None)
                    and attribution['componentType']==('Sprite' if piece==8 else None),'SOURCE outline/main component binding changed')
            require(command['position']==[owner['position'][i]+OFFSETS[piece][i] for i in range(2)] and
                    command['color']==([255,255,255,255] if piece==8 else [0,0,0,255]),'SOURCE outline order/color changed')
    return frames


def read_native(path):
    native={'rosters':{},'dispatches':{},'commands':{tick:[] for tick in range(FRAMES)},'states':{}}
    names={'draw-owner-roster':'rosters','draw-owner-dispatch':'dispatches'};ended=False
    with path.open() as stream:
        for line in stream:
            if not line.startswith(('{"event":"draw-owner-','{"event":"spring-command"','{"event":"phase"','{"event":"native-ended"')):continue
            row=json.loads(line);event=row['event']
            require(not ended,'Native rows after route end')
            if event=='native-ended':
                require(row['frames']==FRAMES and row['loads']==2 and row['reloads']==0,'Native zero-reload route incomplete');ended=True;continue
            tick=row['tick'];require(0<=tick<FRAMES,'Native Spring tick out of range')
            if event in names:
                destination=native[names[event]];require(tick not in destination,'Duplicate native roster/dispatch tick');destination[tick]=row
            elif event=='spring-command':native['commands'][tick].append(row)
            elif row['phase']=='after-frame':
                require(tick not in native['states'],'Duplicate native after-frame state');native['states'][tick]=row['state']
    require(ended and all(sorted(native[key])==list(range(FRAMES)) for key in native),'Incomplete native route')
    return native


def validate_bindings(native):
    identities={};semantic_ids={}
    for tick in range(FRAMES):
        live=native['rosters'][tick]['live'];by_id={owner['identity']:owner for owner in live}
        require(len(by_id)==len(live),'Aliased native roster identity')
        dispatch=native['dispatches'][tick]['order']
        require(dispatch==[owner['identity'] for owner in live if owner['visible'] and not owner['hudExcluded']],
                'Native dispatch differs from whole roster')
        owners=[by_id[identity] for identity in dispatch if by_id[identity]['kind']=='Spring']
        require(len(owners)==int(tick>=374),'Native Spring owner lifetime changed')
        commands=native['commands'][tick]
        require([command['ownerIdentity'] for command in commands]==[owner['identity'] for owner in owners for _ in range(9)],
                'Spring command owner/dispatch/count mismatch')
        for index,command in enumerate(commands):
            owner=by_id[command['ownerIdentity']];identity=owner['identity'];key=(owner['room'],owner['authoredId']);piece=index%9
            require(key==SEMANTIC and command['index']==index and command['piece']==piece and
                    (command['room'],command['authoredId'])==key and command['dispatchIndex']==dispatch.index(identity),
                    'Spring command semantic binding/piece mismatch')
            require(identities.setdefault(identity,key)==key and semantic_ids.setdefault(key,identity)==identity,
                    'Spring identity changed during zero-reload lifetime')
            require(command['orientation']=='floor' and command['animation']=='idle' and command['animationFrame']==0,'Unsupported Spring idle state')
            states=[entity for entity in native['states'][tick]['entities'] if entity['id']==identity]
            require(len(states)==1 and (states[0]['kind'],states[0]['room'],states[0]['authoredId'])==('spring',*SEMANTIC),
                    'Spring command has no actual native entity state')
            state=states[0]
            require(state['wiggler']==0 and state['collidable'] and state['box']==[16,6,-8,-6], 'Unsupported actual native Spring body/wiggler')
            require(command['position']==[state['position'][i]+OFFSETS[piece][i] for i in range(2)],'Spring command does not use actual native body/outline offset')


def compare_tick(tick,source,actual,frame):
    expected=source['commands'];require(len(actual)==len(expected),f'tick {tick}: Spring command count')
    for piece,(wanted,command) in enumerate(zip(expected,actual)):
        for field in ('room','authoredId','sheet','sourceRectangle','color','effects','dimensions','finiteGeometry','verticesFloat32Bits'):
            require(command[field]==wanted[field],f'tick {tick} piece {piece}: Spring {field}')
        for field in ('position','origin','scale'):
            require(list(map(float32,command[field]))==list(map(float32,wanted[field])),f'tick {tick} piece {piece}: Spring {field}')
        require(float32(command['rotation'])==float32(wanted['rotation']),f'tick {tick}: Spring rotation')
        require(all(command[field]==frame[field] for field in frame),'Spring material mapping changed')


class SpringCommandProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not NATIVE.exists() and 'CELESTE_SPRING_NATIVE_TRACE' not in os.environ:
            raise unittest.SkipTest('Requires private Spring native projection evidence')
        cls.frame=read_catalog(CATALOG);cls.source=read_source(SOURCE_TRACE);cls.native=read_native(NATIVE)

    def test_all_514_frames_1260_commands_and_25200_geometry_components(self):
        for tick in range(FRAMES):compare_tick(tick,self.source[tick],self.native['commands'][tick],self.frame)
        self.assertEqual(sum(map(len,self.native['commands'].values())),1260)

    def test_whole_owner_order_and_actual_native_binding(self):
        validate_bindings(self.native);source=sample_source(SOURCE_TRACE)
        for tick in range(FRAMES):self.assertEqual(native_keys(self.native['rosters'][tick]),source_keys(tick,source[tick]))

    def test_source_logical_bottom_center_is_not_center_of_clipped_crop(self):
        self.assertEqual(self.frame['origin'],[6,3])
        self.assertEqual(self.frame['sourceRectangle'],[68,0,12,3])
        for tick in range(374,FRAMES):self.assertEqual(self.native['commands'][tick][-1]['origin'],[6,3])

    def test_known_spring_and_strawberry_identity_swap_rejects(self):
        changed=copy.deepcopy(self.native);live=changed['rosters'][414]['live']
        spring=next(owner for owner in live if owner['kind']=='Spring');berry=next(owner for owner in live if owner['kind']=='Strawberry')
        spring_id,berry_id=spring['identity'],berry['identity'];self.assertNotEqual(spring_id,berry_id)
        spring['identity'],berry['identity']=berry_id,spring_id
        exchange=lambda identity:berry_id if identity==spring_id else spring_id if identity==berry_id else identity
        changed['dispatches'][414]['order']=[exchange(identity) for identity in changed['dispatches'][414]['order']]
        for row in changed['commands'][414]:row['ownerIdentity']=berry_id
        for entity in changed['states'][414]['entities']:entity['id']=exchange(entity['id'])
        self.assertEqual((spring['identity'],berry['identity']),(berry_id,spring_id))
        with self.assertRaisesRegex(ValueError,'lifetime'):validate_bindings(changed)

    def test_unknown_identity_rejects(self):
        changed=copy.deepcopy(self.native);changed['commands'][414][0]['ownerIdentity']=999999999
        with self.assertRaisesRegex(ValueError,'owner/dispatch'):validate_bindings(changed)

    def test_aliased_roster_identity_rejects(self):
        changed=copy.deepcopy(self.native);live=changed['rosters'][414]['live'];live[-1]['identity']=live[0]['identity']
        with self.assertRaisesRegex(ValueError,'Aliased'):validate_bindings(changed)

    def test_missing_owner_rejects(self):
        changed=copy.deepcopy(self.native);owner=next(owner for owner in changed['rosters'][414]['live'] if owner['kind']=='Spring')
        changed['rosters'][414]['live'].remove(owner);changed['dispatches'][414]['order'].remove(owner['identity'])
        with self.assertRaisesRegex(ValueError,'lifetime'):validate_bindings(changed)

    def test_dispatch_reordering_rejects(self):
        changed=copy.deepcopy(self.native);order=changed['dispatches'][414]['order'];order[0],order[1]=order[1],order[0]
        with self.assertRaisesRegex(ValueError,'dispatch differs'):validate_bindings(changed)

    def test_lifetime_identity_tamper_rejects(self):
        changed=copy.deepcopy(self.native);owner=next(owner for owner in changed['rosters'][414]['live'] if owner['kind']=='Spring')
        old=owner['identity'];owner['identity']=999999999
        changed['dispatches'][414]['order']=[owner['identity'] if identity==old else identity for identity in changed['dispatches'][414]['order']]
        for row in changed['commands'][414]:row['ownerIdentity']=owner['identity']
        with self.assertRaisesRegex(ValueError,'lifetime'):validate_bindings(changed)

    def test_piece_body_and_unsupported_idle_state_reject_parameterized(self):
        for field,value in [('piece',7),('dispatchIndex',0),('orientation','wallLeft'),('animation','bounce'),('animationFrame',1),('position',[0,0])]:
            with self.subTest(field=field):
                changed=copy.deepcopy(self.native);changed['commands'][414][0][field]=value
                with self.assertRaises(ValueError):validate_bindings(changed)

    def test_logical_fields_colors_order_and_geometry_reject_parameterized(self):
        for field,value in [('color',[255,255,255,255]),('origin',[8,8]),('sourceRectangle',[0,0,12,3]),
                            ('verticesFloat32Bits',[]),('scale',[1,1.1]),('rotation',1),('effects','FlipHorizontally')]:
            with self.subTest(field=field):
                changed=copy.deepcopy(self.native['commands'][414]);changed[0][field]=value
                with self.assertRaises(ValueError):compare_tick(414,self.source[414],changed,self.frame)
        changed=copy.deepcopy(self.native['commands'][414]);changed[0],changed[1]=changed[1],changed[0]
        with self.assertRaises(ValueError):compare_tick(414,self.source[414],changed,self.frame)

    def test_catalog_material_tamper_rejects(self):
        frame=dict(self.frame,texture='owned/not-idle')
        with self.assertRaisesRegex(ValueError,'material'):compare_tick(414,self.source[414],self.native['commands'][414],frame)


if __name__=='__main__':unittest.main()
