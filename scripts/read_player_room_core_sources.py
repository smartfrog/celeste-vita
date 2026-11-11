#!/usr/bin/env python3
"""Read the pinned private room profile and additional room-core dependency bodies."""

import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from binary_map import Reader
from prepare_static_tilemap import MEMBER, MAP_SHA
from check_native_oracle import oracle_environment
from native_oracle_sdk import sdk_path
from read_player_presentation_sources import ILSPY_SHA, source_type
from prepare_room_visuals import MEMBERS
from extract_native_oracle import SOURCE_HASHES
from prepare_room_visual_oracle import VISUAL_SOURCES

SDK = sdk_path(ROOT)
TOOL = ROOT / '.audit/ilspy/tools/ilspycmd-9.1.0.7988/tools/net8.0/any/ilspycmd.dll'
INPUTS = ROOT / '.audit/ilspy/inputs'
SOURCE_PINS = {
    'Celeste.ClutterBlockGenerator.cs': '05b4f9d4cee0b04f083ec5631072d698f038b8aea5794152fd124a2074c8b374',
    'Celeste.SaveData.cs': '4d5effbda2d6dc7b142eee6b84c019f9335cb0212e0fcf282045a205a1739472',
    'Celeste.AreaStats.cs': '390aee93b1ac152bb220d2257aeba608fc4e4ae0ea5fa83ef72a8324c4792f7c',
    'Celeste.AreaModeStats.cs': 'ec466ddc07c3899930410cfa1305e22418f75ec47d68c36ca01182fcd7f10658',
    'Celeste.AreaKey.cs': '274aabdf01ed68bd565281d26e86fcea0c50dc25dbd4f99bced7efac2848c172',
    'Celeste.AreaMode.cs': 'bde9477f2a79f4e7d35e8c9eb13a1d6ea66eb0acabde2ee2f291dd60842cc1f5',
    'Celeste.Session.cs': 'd1dd0f1a06c1dcb80524ee6c6e03f64465ecd9f291085cc1777522e0efb2f659',
    'Celeste.EntityData.cs': '7e722e9d9fa35c3d5c026264d35f694f450f93300a4cb3967750dbc944d1043d',
    'Celeste.StaticMover.cs': '930ffdf630cf1d6a17c60b8bdbd3bcffce50e503074421e7eac15647ea6d818e',
    'Celeste.Leader.cs': '03355e1c14110fa117838c36cca48fb218047247b9d5f0b3d3cab2e9819402b8',
    'Celeste.WaterInteraction.cs': '0aca5fb523667bf7b97593035e0d73f67442db5b4c502a3ed8db47cb6eefb782',
    'Celeste.WindMover.cs': '4572c72e8a8fafe034cbc50e6c22e9731025157d744c88deb8f0a64031196db3',
    'Celeste.VertexLight.cs': 'd7ca4643a8dc4395cb40001fad51cec0bb4d39a5066a5b90cfb16a74f9d07b06',
    'Celeste.MirrorReflection.cs': '0e30eebd881c24da49fcc72260e03dc0e9a70f8cb9d57c9fdaaca9ad9367bebb',
    'Celeste.PostUpdateHook.cs': '5f4fb4e3cd2e03bbd46556bf5c177d66bfc600d55cc8f078623768802eb9ec64',
    'Celeste.SpawnFacingTrigger.cs': '9bb4a9cd7825e1d0abdbf08b164bb6f4cc30f1111bdaf04fa386d8df0d3ce4be',
    'Celeste.AudioState.cs': 'f8079d26785611236bd3f80a35c221a77bc2fff247fe7ed86723b63ed1a12238',
    'Celeste.ScreenshakeAmount.cs': 'bbc86f9ddea91a1e717f753e293a8501ec680b12a89f8614547df5b64ea05281',
    'Celeste.Assists.cs': '2999d0795daab094322d30a94a1c43ebb9ec2a0e35cc23f4e19d07cf8c8b700d',
    'Celeste.EntityID.cs': 'e659924c3a211258000ff71b9a6987300657cd9243f9a313f8ebe436a926060f',
    'Celeste.SoundSource.cs': '598252562951366ad472ffac0c582084de35f4d5aef0178926325df80ca21d70',
    'Celeste.Follower.cs': '7ebb630acfc34e6eeae80b04d5c09d6054f4b7b20a6c86d6c917043fde883023',
    'Celeste.AudioTrackState.cs': '3a76ce1d4ea7598012b9a49a2f3dcc468f6867800ed2680c839ea65a826f12d7',
    'Celeste.ModeProperties.cs': '8b35daf83c95c1d6a4c85a6a94dc125f5415d88757bc4ec59d156742ddcd934b',
    'Celeste.BadelineOldsite.cs': '43be3d7a744e6a6fc650285412cee3bc0432355cdd522c4f580550735b9a299b',
    'Monocle.Camera.cs': '87ea8ab095fa766e4f816e1b6fccc1e349f4f9bc55eb8f51cf1f75ed5097f91a',
    'Monocle.BitTag.cs': 'a114b8ff5168ce22e56db5b482a2e96da51990d14d9d91d37da2469228336583',
    'Celeste.Settings.cs': 'fbddd928b8f9b62fbfde274952bc7937785ca8e4cd5d3b7c34430a1d5bb00dbd',
    'Celeste.DecalData.cs': '6a69a49aceb482dfc4d301ad94737b9ac0bfe236466bf1229046ed077ddc3ba0',
    'Celeste.BinaryPacker.cs': '254de801184f066b4f08498d58645f0ece0506a39d9d2b56020edd46e58b3206',
    'Celeste.Collision.cs': 'd5fa4ab05a086dd1eced3178256aca3dbad89c290bc9e9912346281e23716e60',
    'Celeste.BackdropRenderer.cs': 'f6c356622ecfadcb4863934698c40cc53211c3df9f0338820fcba2c2ea5d12b4',
    'Celeste.FormationBackdrop.cs': '5c34442da781befab6d69c2881962b9ffa55a42e6f171f3447d7923203a26dc2',
    'Celeste.TotalStrawberriesDisplay.cs': '2308f2d39e6480daf7509e6872f34b519459b8261ae17d4823ae6ba0beaf4a9f',
    'Celeste.HudRenderer.cs': '785e84c8f984b57347aa6800a4e0923c5f07f552fdff34ec3192f5a80c23b07b',
    'Celeste.LightingRenderer.cs': '01bb8ef633506f709da14649b2aae54268cf73bca08bfd3260d71ce72de07eb2',
    'Celeste.BloomRenderer.cs': '7c4fb4767a27f5caed9f343808ba87e86e954869c3cc6efe70bf6b8795a8cf45',
    'Monocle.ParticleSystem.cs': '0bbf59ecb44aa0950bf816b6aed7b640f227e3934547708fc63fd6356d9edd83',
    'Monocle.ParticleType.cs': '08e0e07ef340cce2b54d9ebb4bf34a2c465b6db8707d6d9a9c7e7ba594b5eae5',
    'Celeste.TrailManager.cs': '6f67fb23652acf515ee32e5cfdca418555903b6466b7c5aa0dc3b5d5bc9933cc',
    'Microsoft.Xna.Framework.Point.cs': '06f238d1d1e768de51bf13ca58079eef2437b1796c453ae314061f6b9c375bd3',
    'Celeste.MEP.cs': 'cece15c70865b4b588a21ee52e91514d756e9d181bd0c20e507aa52f658a5480',
    'Celeste.CheckpointData.cs': '0d58e043833a4fe4c1f6a2a7ee47a149cb1eb4adfd4e3911cd84b2a209df2772',
    'Celeste.Tags.cs': 'e7537e9ad7d5c436ce271cc3ea10fc65aab35853a5dfc133ad854876abaf038d',
    'Monocle.Particle.cs': '80edfd403d007a7c074be00efe7947081d6d242c93a0aa2462def8aa939a4252',
    'Monocle.SimpleCurve.cs': 'f32d08d5bd705a826c5f4c0e10b2ce7d1a465f5d288140a2c29204a948a01400',
    'Celeste.Trigger.cs': '1daf32b2c7418553b4e3897b16eeab0a985f2ac22a25edda03c7d502fb364949',
    'Celeste.BloomPoint.cs': '01f75388f064d4e465fb62422799ea55ec7edabaca46495cea5bcda688383d9c',
    'Celeste.GameplayRenderer.cs': '294faa1e6e9b7bb5b83429b5da32d19b7ced485bf5354cf4a51b6c97c5aa4931',
    'Celeste.BackgroundTiles.cs': 'fcdc0bc52a9653af51c27e556cd880a66384295ec4c306d4de6a96fd756d9b50',
    'Monocle.TileGrid.cs': 'f78e0e6b2a7dded3a5bced650ac817ab0106fbfe396406b7bc09e780a42b4fbc',
    'Celeste.Pathfinder.cs': 'dcbf096025164b132dbeec1bcc074af4530ffca03bc9747d1e31b66457982f05',
    'Celeste.MapData.cs': 'e820408a848bfee05aba0d98cf698cf5061438ac3cf1f6640f44cf7db1d8a898',
    'Microsoft.Xna.Framework.Matrix.cs': '6252a377415f09ce2ea364debcd1cf2318fc1748091c62a007f7540958de6c07',
    'Microsoft.Xna.Framework.Vector3.cs': '902f9b70d7ca65e6771e2d7d28d7bbba28731fb5d598040533567376f73468a5',
    'Microsoft.Xna.Framework.Graphics.Viewport.cs': '8d1fcd6234cfaab75a2c2e864a8d155e498483c0cf0ea29e6824476bbba8ed05',
    'Celeste.Overlay.cs': '90ddbbfa9068a2e87a53079e1eabd82ce1f75b51fec754d9b0a431651a69cb50',
    'Celeste.HiresSnow.cs': 'fb451689f753e55c4b61f13a7451add48517ca99c2f974ad06d28b17156a5d10',
    'Celeste.Backdrop.cs': 'e529cd695be8b24e499b28c71b85a6eb92ba62cf807e24544d8d25bc39604681',
    'Celeste.WallBooster.cs': '51944c249f54ee42e55f15807245c8e989defe4c6ad71867e0a2eb4bd917aeb2',
    'Celeste.DreamBlock.cs': 'ae60e156acd67faaf2f373f44b134778b34dbb1570e25e5df7f751cb342dfd18',
    'Celeste.FlingBird.cs': 'a9f728ad2495068e25f1e588f7f905db40ef0949042df79cd0c5ae7fe6aaeb48',
    'Celeste.Snow.cs': '8cf74a3525b8fa2685a63026f9065c061b6d4e488d8635374efa96348bf28ed8',
    'Celeste.WindSnowFG.cs': '084f8010be716063d7fb298857a9a1782656f53fd7dcc8b939f208f057fbf85f',
    'Celeste.StrawberriesCounter.cs': '8a2c4fac6c7d490017842c671906830aa3c2bf6043076cb6732f56c02552ba29',
    'Celeste.HiresRenderer.cs': 'b63b43412ddf2aac74340d20d05d7db93e9bb738165b6ab038ab5ccce3d7850f',
    'Celeste.MountainCamera.cs': '3863bd2a22f1ee1ff3a62f0b3066c56b9084a231537b6df31b3477f024acc972',
    'Microsoft.Xna.Framework.Graphics.VertexDeclaration.cs': 'b3fe410d9d5676cd64ac129845b55707dd411193b8b331ae46a3e1469dd7d2b0',
    'Microsoft.Xna.Framework.Graphics.IVertexType.cs': '0120ab262bc990884b69fb7dbab67a57cde90c369e8b21068de39b25782a9382',
    'Monocle.Wiggler.cs': 'e414e804e5b2bc5250af6c6500861835a58584b4187f8ddcc68be7f7a93be849',
    'Celeste.Platform.cs': '14326fc90f5f74926a1f289895690ea60163eef3629b3837d2cd34a939a94f03',
    'Celeste.Solid.cs': 'd69ce2a1f4fa172d3d1024e3a1996479a55f93d828569084900fbc30b4a2fe61',
    'Celeste.JumpThru.cs': '5ca7240b8aed9b25cd439849da870b9e2acad807e6add3669ae16c137693a67e',
    'Celeste.SurfaceIndex.cs': 'fa0519e4762e7d8d0f33180bbb10e43636bb95e2347646f3f255d6079c868d2c',
    'Celeste.DashCollision.cs': '5f7ba95b06cd119501fabeb8871bdb1f626fa7d93f15d4bf10e6808d408f6ca1',
    'Celeste.ClimbBlocker.cs': '3ae0a2bdf6508e519acd551533f9e50d75666dbc3371e88b669e5e87cc4db74a',
    'Celeste.ClutterBlock.cs': 'd1b314d4d58cebfc0338671e7455bbdfed25f3a692487f0dacfcdb006af9c1ee',
    'Monocle.Pooled.cs': '3b8cef2b272cdea323cbd37d1983389075dfab65589f844ff5ea9001696dbc9e',
    'Celeste.BeforeRenderHook.cs': '110416743422627bd0b90af96558e16af8decea8a7cb26a46ae66a72821e23d7',
    'Monocle.Pooler.cs': '9fbe4572c329bc084c5a9c5b839e6642c34b434ba97e9fce534a9a0cefb9f34a',
    'Microsoft.Xna.Framework.Graphics.VertexElement.cs': 'c3d51f541a8d55c9412aff6c768f3acb0c289f53cd5765c09e181675d6dd5c5c',
    'Microsoft.Xna.Framework.Graphics.VertexElementFormat.cs': '22789f596ec7a6dd26d14e59305b438b8cfbfe8dd88043dc3a0e998f7a719b17',
    'Microsoft.Xna.Framework.Graphics.VertexElementUsage.cs': '2b2bf5f425722d1fba693ae91511136a7c4b8948e0bb4d3816f6820eeba500eb',
    'Microsoft.Xna.Framework.Graphics.Blend.cs': '7f2adafbf081cbc8235e694fce150630ae215e8ab76d354fc792ee49781e394d',
    'Microsoft.Xna.Framework.Graphics.BlendFunction.cs': 'e39496ab68a0fd1458c5fe8d0b8829d4ef28504178b355db622c237c9ce136c7',
    'Microsoft.Xna.Framework.Graphics.GraphicsResource.cs': '2b9988b27aa4cd88ef3cbff32c6d3dc368683b55f797cb7c0e8655b519e7c85a',
    'Microsoft.Xna.Framework.Graphics.BlendState.cs': 'c26c316cfb0ecfa301d84f14576172356436670a2b2fcb45b7ba1e692274f735',
    'Microsoft.Xna.Framework.Graphics.ColorWriteChannels.cs': 'de4899357a9293ac910e1d27e6f78206aa0bfc88ca7247ade0d0005f5cc98665',
    'Monocle.VirtualAsset.cs': '5b5f0a19e30f0ebf446de3f1b142d8afa592dc6ba7268a25467a32d82abc5ab1',
    'Monocle.VirtualRenderTarget.cs': 'c07a60d04e613876f2f3cdbe897f98522c9d0697d4138ec3327c4f0837d79404',
    'Celeste.DashCollisionResults.cs': 'ae057a337c8a6232128b68e8f288104947ceeaf8e04bb186bbbe095738262124',
    'Celeste.IOverlayHandler.cs': '3e2645e444b698860b9b5b3c91e77b1660127a01323915f2822d1643436248c5',
    'Celeste.ClutterAbsorbEffect.cs': '81d1063118f2ae1a077f220842b97da41a86c711686907a785d38dae7cca4249',
    'Celeste.LightOcclude.cs': '431d19e345f5b142351bc7141bc190ba9d4bb17ea3c427286902a71d25531bc8',
    'Monocle.Shaker.cs': 'd4e6bc9e54dda39c56cccf80b76eb848bd9cdc9aeadd928f012f60da14f33056',
    'Celeste.ClutterCabinet.cs': 'f37e08c57fdf7d9c0a8bfc216077028ede4b17ef7c1a40ff061f2a697221dfeb',
} | {name: SOURCE_HASHES[name] for name in ('Celeste.Actor.cs', 'Celeste.CollisionData.cs', 'Celeste.LevelData.cs',
    'Monocle.Collider.cs', 'Monocle.Hitbox.cs', 'Monocle.Grid.cs', 'Monocle.Collide.cs', 'Celeste.SolidTiles.cs')}
SOURCE_PINS |= {name: digest for name, digest in VISUAL_SOURCES.items() if name != 'System.Random.cs'}
TYPES = tuple(name.removesuffix('.cs') for name in SOURCE_PINS)
RAW_ROOM_SHA = '3eefb6d3fae3cc0977583d8f53075da3db98da01795c0ce56f5b799e8bc65eb3'


def presentation_profile(room):
    attributes = room['attributes']
    if attributes.get('windPattern') != 'None' or attributes.get('underwater') is not False or attributes.get('space') is not False:
        raise ValueError('Unsupported mechanical environment')
    layers = {layer['name']: layer for layer in room['children']}
    if len(layers) != len(room['children']):
        raise ValueError('Duplicate room layer')
    entities = layers['entities']['children']
    if Counter(entity['name'] for entity in entities) != {'player': 1, 'spikesUp': 4, 'spikesLeft': 1, 'goldenBerry': 1}:
        raise ValueError('Unsupported mechanical entity inventory')
    if layers.get('triggers', {}).get('children', []):
        raise ValueError('Unsupported nonempty trigger inventory')
    stripped = copy.deepcopy(room)
    changes = []
    for layer in stripped['children']:
        if layer['name'] in ('fgdecals', 'bgdecals', 'objtiles'):
            old = copy.deepcopy(layer)
            layer['children'] = []
            if 'innerText' in layer['attributes']:
                layer['attributes']['innerText'] = ''
            changes.append({'layer': layer['name'], 'original': old, 'stripped': copy.deepcopy(layer)})
    return stripped, changes


def main():
    parser = argparse.ArgumentParser(description='Private room-core dependency discovery; not lifecycle acceptance')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reuse', type=Path, action='append', default=[], help='Pinned prior directory or source file; may repeat, never overwrites it')
    parser.add_argument('--inspect-type', action='append', help='Explicit narrow discovery only; unknown hashes never satisfy the room-core inventory')
    args = parser.parse_args()
    OUTPUT = args.output.resolve()
    SOURCE = OUTPUT / 'source'
    if not OUTPUT.is_relative_to(ROOT / '.audit/native-player-death-respawn') or OUTPUT.exists():
        raise ValueError('Private source output must be fresh')
    selected_types = tuple(args.inspect_type) if args.inspect_type else TYPES
    if any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*', name) for name in selected_types) or len(set(selected_types)) != len(selected_types):
        raise ValueError('Invalid or duplicate discovery type')
    for name in ('Celeste.exe', 'FNA.dll', 'mscorlib.dll'):
        if hashlib.sha256((INPUTS / name).read_bytes()).hexdigest() != MEMBERS[name]:
            raise ValueError('Pinned input changed: ' + name)
    if hashlib.sha256(TOOL.read_bytes()).hexdigest() != ILSPY_SHA:
        raise ValueError('Pinned ILSpy changed')
    OUTPUT.mkdir(parents=True)
    receipt = {'recipe_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'sources': [], 'commands': [],
        'inputs': {name: MEMBERS[name] for name in ('Celeste.exe', 'FNA.dll', 'mscorlib.dll')}, 'tool_sha256': ILSPY_SHA,
        'inspection_only': bool(args.inspect_type)}
    for arguments, name in ((['--version'], 'sdk.log'), (['--list-runtimes'], 'runtime.log')):
        command = list(map(str, [SDK, *arguments]))
        with (OUTPUT / name).open('x') as log:
            result = subprocess.run(command, cwd=ROOT, env=oracle_environment(SDK), stdout=log, stderr=subprocess.STDOUT)
        receipt['commands'].append({'command': command, 'exit_code': result.returncode})
        (OUTPUT / 'provenance.json').write_text(json.dumps(receipt, indent=2) + '\n')
        if result.returncode:
            raise RuntimeError('Pinned offline runtime check failed: ' + name)
    if (OUTPUT / 'sdk.log').read_text().strip() != '8.0.425' or 'Microsoft.NETCore.App 8.0.31 [' not in (OUTPUT / 'runtime.log').read_text():
        raise ValueError('Pinned SDK/runtime changed')
    with zipfile.ZipFile(ROOT / 'game/celeste-linux.zip') as archive:
        data = archive.read(MEMBER)
    if hashlib.sha256(data).hexdigest() != MAP_SHA:
        raise ValueError('Pinned map changed')
    _, root = Reader(data).map()
    levels = next(node['children'] for node in root['children'] if node['name'] == 'levels')
    room = next(node for node in levels if node['attributes']['name'] == 'lvl_1')
    (OUTPUT / 'raw-room.json').write_text(json.dumps(room, indent=2) + '\n')
    if hashlib.sha256((OUTPUT / 'raw-room.json').read_bytes()).hexdigest() != RAW_ROOM_SHA:
        raise ValueError('Pinned raw room metadata changed')
    stripped, changes = presentation_profile(room)
    (OUTPUT / 'presentation-stripped-room.json').write_text(json.dumps(stripped, indent=2) + '\n')
    (OUTPUT / 'profile-delta.json').write_text(json.dumps({'map_sha256': MAP_SHA, 'changes': changes,
        'raw_room_sha256': hashlib.sha256((OUTPUT / 'raw-room.json').read_bytes()).hexdigest(),
        'stripped_room_sha256': hashlib.sha256((OUTPUT / 'presentation-stripped-room.json').read_bytes()).hexdigest(),
        'claim': 'Private phase0 caller-profile inspection only; no whole-level fidelity'}, indent=2) + '\n')
    SOURCE.mkdir()
    reused = {}
    for previous in args.reuse:
        prior = previous.resolve()
        if not prior.is_relative_to(ROOT / '.audit/native-player-death-respawn'):
            if not prior.is_file() or not any(prior.is_relative_to(directory) for directory in
                    (ROOT / '.audit/ilspy/cs', ROOT / '.audit/native-room-visuals/source-closure-01')):
                raise ValueError('Reused sources must remain private pinned bodies')
        if prior.is_file():
            if prior.name not in SOURCE_PINS:
                raise ValueError('Unrecognized source reuse file')
            reused[prior.name] = prior
        else:
            for entry in json.loads((prior / 'provenance.json').read_text())['sources']:
                if entry['file'] in SOURCE_PINS and entry['sha256'] == SOURCE_PINS[entry['file']]:
                    reused[entry['file']] = prior / 'source' / entry['file']
    for name in selected_types:
        if name + '.cs' in reused:
            prior = reused[name + '.cs']
            data = prior.read_bytes()
            if hashlib.sha256(data).hexdigest() != SOURCE_PINS[name + '.cs']:
                raise ValueError('Prior source identity changed: ' + name)
            (SOURCE / (name + '.cs')).write_bytes(data)
            receipt['sources'].append({'file': name + '.cs', 'sha256': SOURCE_PINS[name + '.cs'], 'reused_from': str(prior)})
            continue
        assembly, type_name = source_type(name + '.cs')
        if name == 'Monocle.VirtualMap':
            type_name += '`1'
        command = list(map(str, [SDK, TOOL, '--disable-updatecheck', '-r', INPUTS, '-t', type_name, INPUTS / assembly]))
        path = SOURCE / (name + '.cs')
        with path.open('xb') as output, (SOURCE / (name + '.stderr')).open('xb') as error:
            result = subprocess.run(command, cwd=ROOT, env=oracle_environment(SDK), stdout=output, stderr=error)
        receipt['commands'].append({'command': command, 'exit_code': result.returncode})
        (OUTPUT / 'provenance.json').write_text(json.dumps(receipt, indent=2) + '\n')
        if result.returncode:
            raise RuntimeError('Narrow extraction failed: ' + name)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if path.name in SOURCE_PINS and digest != SOURCE_PINS[path.name]:
            raise ValueError('Pinned decompiled source changed: ' + name)
        if not args.inspect_type and path.name not in SOURCE_PINS:
            raise ValueError('Unpinned source cannot satisfy the room-core inventory')
        receipt['sources'].append({'file': path.name, 'sha256': digest})
    (OUTPUT / 'provenance.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
