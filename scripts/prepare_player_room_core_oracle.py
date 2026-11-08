#!/usr/bin/env python3
"""Compile the canonical room-core method/initializer cut without claiming closure."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

from check_native_oracle import ROOT, PRIVATE, oracle_environment, verify_extraction
from native_room_revision import source_state
from native_room_textures import atlas_metadata
from prepare_player_death_oracle import prepare
from prepare_player_presentation_oracle import source_block
from read_player_death_sources import SOURCE_PINS
from read_player_room_core_sources import SOURCE_PINS as ROOM_PINS, RAW_ROOM_SHA, presentation_profile
from room_core_frontier import build_tool, emit as emit_frontier

GUI_META = "Content/Graphics/Atlases/Gui.meta"
GUI_META_SHA = "884ea39e604e34e3a45b005d164a5249de9a985e58fde7ef730193c47363525b"


def project_text(files=('Extracted.cs', 'Shared.cs', 'Geometry.cs', 'Services.cs', 'RoomCoreProbe.cs', 'RoomCoreGpu.cs', 'NativeImportGuard.cs', 'NativeImportGuardProbe.cs', 'RoomCoreExecution.cs', 'NativeAbiMetadataAudit.cs', 'PlatformIdentityFixture.cs', 'PlatformIdentityFixtureProbe.cs', 'RoomCoreRoomInput.cs', 'RoomCoreCaller.cs'), reference=None):
    referenced = '' if reference is None else f'<Reference Include="PrivateCheckpoint"><HintPath>{reference}</HintPath></Reference>'
    assembly = '' if reference is None else '<AssemblyName>RoomCoreHelpers</AssemblyName>'
    return ('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework>'
        '<UseAppHost>false</UseAppHost><AllowUnsafeBlocks>true</AllowUnsafeBlocks><EnableDefaultCompileItems>false</EnableDefaultCompileItems>'
        + ('<StartupObject>RoomCoreProbe</StartupObject>' if reference is None else '') +
        '<DefineConstants>DEATH_SOURCE_GATE;GRID_ORACLE</DefineConstants><NuGetAudit>false</NuGetAudit>' + assembly + '</PropertyGroup><ItemGroup>'
        + ''.join(f'<Compile Include="{name}"/>' for name in files) + referenced + '</ItemGroup></Project>')


def compile_project(output, identity, before, execution=None):
    sdk = PRIVATE / 'tools/dotnet-8.0.425/dotnet'
    commands = []
    actions = [(['restore', output / 'Oracle.csproj', '--configfile', output / 'NuGet.Config'], 'restore.log'),
        (['build', output / 'Oracle.csproj', '--no-restore', '-c', 'Release', '-p:UseSharedCompilation=false', '--disable-build-servers'], 'build.log')]
    if execution:
        actions.append((execution, 'execution.log'))
    for args, log in actions:
        command = list(map(str, [sdk, *args]))
        with (output / log).open('x') as stream:
            result = subprocess.run(command, cwd=ROOT, env=oracle_environment(sdk), stdout=stream, stderr=subprocess.STDOUT)
        commands.append({'command': command, 'exit_code': result.returncode, 'log': log})
        (output / 'commands-run.json').write_text(json.dumps(commands, indent=2) + '\n')
        if source_state() != before:
            raise RuntimeError('Source changed during the room-core probe')
        if result.returncode:
            errors = {line for line in (output / log).read_text().splitlines() if ': error CS' in line}
            (output / 'probe-result.json').write_text(json.dumps({'status': 'blocked-not-room-core-closed', 'unique_compile_errors': len(errors),
                'source_identity': identity, 'source_revision': before[0], 'source_changes': before[1], 'log': log,
                'claim': 'No room-core lifecycle execution; six baseline diagnostics are not room-core coverage'}, indent=2) + '\n')
            raise RuntimeError(f'Room-core dependency probe failed with {len(errors)} unique errors: {output / log}')


def native_abi_audit(output):
    sdk = PRIVATE / 'tools/dotnet-8.0.425/dotnet'
    generated = output / 'bin/Release/net8.0/Oracle.dll'
    report = output / 'native-abi-identity.json'
    command = [str(sdk), str(generated), 'native-abi-metadata-audit', str(generated), str(report),
        str(ROOT / '.audit/ilspy/inputs/Celeste.exe'), str(ROOT / '.audit/ilspy/inputs/FNA.dll'), '1094']
    with (output / 'native-abi-audit.log').open('x') as log:
        result = subprocess.run(command, cwd=ROOT, env=oracle_environment(sdk), stdout=log, stderr=subprocess.STDOUT)
    if not report.is_file():
        raise RuntimeError(f'Native ABI metadata audit produced no report: {output / "native-abi-audit.log"}')
    data = json.loads(report.read_text())
    if result.returncode or data['failures'] or not all(contract['ok'] for contract in data['rootContracts']):
        raise RuntimeError(f'Native ABI metadata identity failed: {len(data["failures"])} signature mismatches, '
            f'{sum(not contract["ok"] for contract in data["rootContracts"])} root contract mismatches: {report}')
    return data


def helper_probe(extract, manifest, baseline, room_source, output, before):
    manifest['extractions'] = []
    manifest['claim'] = 'Isolated mandatory helper execution only; NOT LoadLevel, Level ticks or lifecycle closure'
    content = 'using System; using System.Collections.Generic; using System.Globalization; using System.Xml.Serialization; using Monocle; using Microsoft.Xna.Framework;\n'
    content += 'namespace Monocle { using Random = PresentationOracle.TracedRandom; public static class Calc {\n'
    content += extract('Monocle.Calc.cs', [(19, 21), (323, 344), (376, 379), (480, 495)]) + '\n} }\n'
    content += 'namespace Celeste { public static class Celeste {\n' + extract('Celeste.Celeste.cs', [(14, 30)]) + '\n}\n'
    content += 'public class WindController {\n' + extract('Celeste.WindController.cs', [(10, 27)]) + '\n}\n'
    for name, ranges, declaration in (
        ('SaveData', [(10, 136)], 'public class SaveData'), ('AreaStats', [(10, 16), (96, 129)], 'public class AreaStats'),
        ('AreaModeStats', [(10, 65)], 'public class AreaModeStats'), ('AreaKey', [(9, 85)], 'public struct AreaKey'),
        ('Assists', [(9, 45)], 'public struct Assists'), ('EntityID', [(9, 46)], 'public struct EntityID'),
        ('EntityData', [(11, 27), (63, 70)], 'public class EntityData'),
        ('LevelData', [(10, 397)], 'public class LevelData'), ('DecalData', [(7, 11)], 'public class DecalData'),
        ('BinaryPacker', [(11, 64)], 'public static class BinaryPacker'),
        ('ClutterBlockGenerator', [(10, 54), (156, 276)], 'public static class ClutterBlockGenerator')):
        content += declaration + ' {\n' + extract('Celeste.' + name + '.cs', ranges) + '\n}\n'
    content += extract('Celeste.AreaMode.cs', [(3, 8)])
    content += '\npublic partial class GoldenBranch { public void Run(EntityData entity3, Vector2 vector, EntityID entityID) {\n'
    content += extract('Celeste.Level.cs', [(506, 513)]) + '\n} } }\n'
    (output / 'Extracted.cs').write_text(content)
    manifest['extracted_sha256'] = hashlib.sha256(content.encode()).hexdigest()
    manifest['baseline_reference_sha256'] = hashlib.sha256((baseline / 'bin/Release/net8.0/Oracle.dll').read_bytes()).hexdigest()
    support = ROOT / 'tests/native/oracle/death/RoomCoreHelpers.cs'
    (output / 'RoomCoreHelpers.cs').write_bytes(support.read_bytes())
    room_input = ROOT / 'tests/native/oracle/death/RoomCoreRoomInput.cs'
    (output / room_input.name).write_bytes(room_input.read_bytes())
    manifest['room_core_support_sha256'] = {str(support.relative_to(ROOT)): hashlib.sha256(support.read_bytes()).hexdigest()}
    manifest['room_core_support_sha256'][str(room_input.relative_to(ROOT))] = hashlib.sha256(room_input.read_bytes()).hexdigest()
    (output / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    identity = verify_extraction(output)
    (output / 'source-identity.json').write_text(json.dumps(identity, indent=2) + '\n')
    (output / 'Oracle.csproj').write_text(project_text(('Extracted.cs', 'RoomCoreHelpers.cs', 'RoomCoreRoomInput.cs'), baseline / 'bin/Release/net8.0/Oracle.dll'))
    (output / 'NuGet.Config').write_bytes((baseline / 'NuGet.Config').read_bytes())
    compile_project(output, identity, before, [output / 'bin/Release/net8.0/RoomCoreHelpers.dll', room_source / 'raw-room.json', output / 'helper-result.json', room_source / 'presentation-stripped-room.json'])
    return identity


def remove_fixture_class(text, name):
    match = re.search(r'[ \t]*\bpublic (?:(?:static|sealed|abstract|partial) )*(?:class|struct) ' + re.escape(name) + r'(?:\s*:[^\n{]+)?\s*\{', text)
    if match is None:
        raise ValueError('Missing declared fixture class: ' + name)
    depth = 1
    end = match.end()
    while end < len(text) and depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    if depth:
        raise ValueError('Malformed fixture class: ' + name)
    start = match.start()
    attributes = re.search(r'(?:^[ \t]*\[[^\n]+\][ \t]*\n)+[ \t]*\Z', text[:start], re.M)
    if attributes:
        start = attributes.start()
    return text[:start] + text[end:]


def callback_guards(original, selected):
    callbacks = set()
    for line in original.splitlines():
        if 'StateMachine.SetCallbacks(' in line:
            arguments = line.split('(', 1)[1].split(')', 1)[0].split(',')
            callbacks.update(argument.strip() for argument in arguments[1:] if argument.strip() != 'null')
    guards = []
    for name in sorted(callbacks):
        if re.search(r'^\s*(?:private|public|protected) [^\n=;{}]+\b' + re.escape(name) + r'\(', selected, re.M):
            continue
        match = re.search(r'^\t((?:private|public|protected) [^\n=;]+\b' + re.escape(name) + r'\([^\n]*\))\s*$', original, re.M)
        if match is None:
            raise ValueError('Missing excluded callback signature: ' + name)
        guards.append(match.group(1) + ' { throw new DeathOracle.UnsupportedClosure("Excluded state callback: ' + name + '"); }')
    return guards


def room_shared_support(text):
    for name in ('Platform', 'Solid', 'JumpThru', 'SurfaceIndex', 'ClimbBlocker'):
        text = remove_fixture_class(text, name)
    boundaries = (
        ('public static void BurstFG(Vector2 position, float angle, int count, float range)', ' { Calls++; }'),
        ('public static void Burst(Vector2 position, float angle)', ' { Calls++; }'))
    for declaration, body in boundaries:
        original = declaration + body
        if text.count(original) != 1:
            raise ValueError('Missing legacy presentation boundary: ' + declaration)
        name = declaration.split('(', 1)[0].rsplit(' ', 1)[1]
        text = text.replace(original, declaration + ' => throw new DeathOracle.UnsupportedClosure("Room-core source not linked: ' + name + '");')
    original_xml = '        public static XmlDocument LoadContentXML(string path) { var xml = new XmlDocument(); xml.Load(path); return xml; }\n'
    if text.count(original_xml) != 1:
        raise ValueError('Missing old XML loading boundary')
    text = text.replace(original_xml, '')
    if text.count('public sealed class Texture2D') != 1:
        raise ValueError('Missing original metadata texture boundary')
    text = text.replace('public sealed class Texture2D', 'public class Texture2D : GraphicsResource', 1)
    text, count = re.subn(r'    \[AttributeUsage\(AttributeTargets.Class\)\]\n#if DEATH_SOURCE_GATE\n.*?\n#endif\n', '', text, flags=re.S)
    if count != 1:
        raise ValueError('Missing presentation tracking attribute aliases')
    return text


def build(source, room_source, output, helpers_only=False, declarations_source=None):
    source, room_source, output = source.resolve(), room_source.resolve(), output.resolve()
    if not output.is_relative_to(ROOT / '.audit/native-player-death-respawn') or output.exists():
        raise ValueError('Room-core probe output must be fresh and private')
    if not room_source.is_relative_to(ROOT / '.audit/native-player-death-respawn'):
        raise ValueError('Room-core discovery must remain private')
    receipt = json.loads((room_source / 'provenance.json').read_text())
    discovered = {entry['file']: entry['sha256'] for entry in receipt['sources']}
    if len(receipt['sources']) != len(ROOM_PINS) or discovered != ROOM_PINS:
        raise ValueError('Room-core discovery inventory is incomplete')
    for name, expected in ROOM_PINS.items():
        source_block((room_source / 'source' / name).read_bytes(), [], expected)
    if hashlib.sha256((room_source / 'raw-room.json').read_bytes()).hexdigest() != RAW_ROOM_SHA:
        raise ValueError('Pinned raw room metadata changed')
    raw = json.loads((room_source / 'raw-room.json').read_text())
    stripped, changes = presentation_profile(raw)
    if stripped != json.loads((room_source / 'presentation-stripped-room.json').read_text()):
        raise ValueError('Declared room profile changed')
    output.mkdir(parents=True)
    before = source_state()
    baseline = output / 'baseline'
    prepare(source, baseline)
    manifest = json.loads((baseline / 'source-manifest.json').read_text())
    manifest.update(claim='Canonical room-core compile cut; separate fresh processes execute the bounded Respawn14->Normal0 live tick and one caller-stimulated Die/wipe/Reload round trip, zero of eight families closed',
                    room_core_recipe_sha256={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in (Path(__file__), ROOT / 'scripts/read_player_room_core_sources.py')},
                    room_core_provenance_sha256=hashlib.sha256((room_source / 'provenance.json').read_bytes()).hexdigest(),
                    room_profile_changes=changes)
    pins = SOURCE_PINS | discovered
    locations = (source, source / 'presentation', room_source / 'source')
    declarations = {}
    if declarations_source is not None:
        declaration_directories = tuple(path.resolve() for path in declarations_source)
        if any(not path.is_relative_to(ROOT / '.audit/native-player-death-respawn') for path in declaration_directories):
            raise ValueError('Declaration contracts must remain private')
        pin_path = ROOT / 'tests/native/oracle/death/declaration-pins.json'
        declarations = json.loads(pin_path.read_text())
        actual = {}
        for directory in declaration_directories:
            declaration_receipt = json.loads((directory / 'provenance.json').read_text())
            for entry in declaration_receipt['sources']:
                value = {key: entry[key] for key in ('sha256', 'type', 'assembly')}
                if entry['file'] in actual and actual[entry['file']] != value:
                    raise ValueError('Declaration receipt disagreement')
                actual[entry['file']] = value
        if actual != declarations:
            raise ValueError('Declaration source inventory differs from tracked pins')
        for name, entry in declarations.items():
            path = next(directory / 'source' / name for directory in declaration_directories if (directory / 'source' / name).is_file())
            source_block(path.read_bytes(), [], entry['sha256'])
            if name in pins and pins[name] != entry['sha256']:
                raise ValueError('Executable/declaration source disagreement: ' + name)
            pins[name] = entry['sha256']
        locations += tuple(directory / 'source' for directory in declaration_directories)
        manifest['declaration_pin_manifest_sha256'] = hashlib.sha256(pin_path.read_bytes()).hexdigest()

    def extract(name, ranges):
        path = next((directory / name for directory in locations if (directory / name).is_file()), None)
        if path is None:
            raise ValueError('Missing original source: ' + name)
        blocks = source_block(path.read_bytes(), ranges, pins[name])
        manifest['extractions'].append({'file': name, 'source_path': str(path.relative_to(ROOT)),
            'source_sha256': pins[name], 'lines_inclusive': ranges,
            'blocks_sha256': [hashlib.sha256(block).hexdigest() for block in blocks]})
        return '\n'.join(block.decode() for block in blocks)

    def whole(name, namespace):
        path = next(directory / name for directory in locations if (directory / name).is_file())
        lines = path.read_text().splitlines()
        start = next(index + 2 for index, line in enumerate(lines) if line == 'namespace ' + namespace + ';')
        return 'namespace ' + namespace + ' {\n' + extract(name, [(start, len(lines))]) + '\n}\n'

    if helpers_only:
        return helper_probe(extract, manifest, baseline, room_source, output, before)

    with zipfile.ZipFile(ROOT / 'game/celeste-linux.zip') as archive:
        gui_meta = archive.read(GUI_META)
    if hashlib.sha256(gui_meta).hexdigest() != GUI_META_SHA:
        raise ValueError('Pinned GUI atlas metadata changed')
    gui_atlas = atlas_metadata(gui_meta)
    (output / 'gui-atlas.json').write_text(json.dumps(gui_atlas, sort_keys=True) + '\n')
    manifest['gui_atlas_sha256'] = hashlib.sha256((output / 'gui-atlas.json').read_bytes()).hexdigest()
    manifest['gui_meta_sha256'] = GUI_META_SHA

    content = (baseline / 'Extracted.cs').read_text()
    for name in ('Entity', 'Scene', 'Tracker', 'MTexture', 'Calc'):
        content = remove_fixture_class(content, name)
    start = content.index('namespace Celeste { public static class Celeste {\n')
    end = content.index('namespace PresentationOracle { public unsafe partial class OriginalSpriteBatch', start)
    player_ranges = [(14, 1114), (1116, 1253), (1255, 1329), (1341, 1414), (1425, 2250),
        (2310, 2362), (2436, 2546), (2548, 2675), (2677, 2832), (2855, 2908), (2910, 2929),
        (2941, 3005), (3083, 3473), (3475, 3555), (3557, 3843), (4569, 4576), (4593, 4600), (6121, 6154), (6280, 6334)]
    frontier_ranges = {
        'Celeste.Player.cs': player_ranges,
        'Celeste.Celeste.cs': [(152, 162)],
        'Celeste.Settings.cs': [(131, 142)],
        'Celeste.SFX.cs': [(1590, 1595)],
        'Celeste.Audio.cs': [(66, 66), (68, 68), (132, 161), (265, 274), (291, 308), (389, 395), (397, 404), (406, 420), (422, 441), (579, 585), (596, 617), (619, 638), (640, 647), (648, 662)],
        'FMOD.Studio.HandleBase.cs': [(49, 65)],
        'Celeste.Spikes.cs': [(39, 73), (75, 78), (91, 138), (251, 260)],
        'Celeste.PlayerCollider.cs': [(16, 22), (24, 50)],
        'Celeste.Input.cs': [(79, 94), (96, 135), (137, 187), (189, 271), (292, 303), (326, 329), (331, 373)],
        'Celeste.SaveData.cs': [(10, 136), (362, 369), (414, 418)],
        'Celeste.UserIO.cs': [(36, 40), (40, 69)],
        'Monocle.VirtualInput.cs': [(19, 27)],
        'Monocle.VirtualButton.cs': [(29, 65), (79, 105)],
        'Monocle.VirtualIntegerAxis.cs': [(40, 49), (100, 103)],
        'Monocle.VirtualJoystick.cs': [(41, 41), (45, 69), (235, 238)],
        'Monocle.Binding.cs': [(30, 76), (224, 260)],
        'Celeste.LedgeBlocker.cs': [(14, 18)],
        'SDL2.SDL.cs': [],
        'Monocle.Engine.cs': [(52, 52), (58, 58), (81, 85), (89, 99)],
        'Monocle.MInput.cs': [(16, 18), (38, 62), (303, 307), (476, 479), (1353, 1369)],
        'Microsoft.Xna.Framework.Input.KeyboardState.cs': [(76, 79), (130, 145)],
        'Monocle.Tracker.cs': [(10, 143), (162, 165), (185, 193), (212, 215), (235, 285)],
        'Monocle.Tracked.cs': [(9, 12)],
        'Monocle.Calc.cs': [(19, 23), (263, 272), (323, 349), (371, 394), (405, 445), (480, 495), (542, 572),
            (641, 644), (712, 720), (731, 744), (776, 804), (821, 832), (849, 852), (854, 867), (874, 893),
            (988, 996), (1017, 1020), (1027, 1030), (1042, 1055), (1185, 1205), (1222, 1260), (1446, 1452),
            (1472, 1517), (1552, 1555), (1607, 1610), (1696, 1699), (1802, 1805), (2092, 2113)],
        'Monocle.MTexture.cs': [(9, 98), (106, 125), (140, 154), (166, 199), (231, 234)],
        'Microsoft.Xna.Framework.Graphics.SpriteBatch.cs': [],
        'Celeste.MountainCamera.cs': [],
        'Celeste.Level.cs': [(15, 325), (357, 1435), (1642, 1673), (1726, 2008), (2616, 2623), (2704, 2713), (2724, 2817)],
        'Celeste.MapData.cs': [(47, 77), (87, 100), (289, 316)],
        'Monocle.Pooler.cs': [(9, 53)],
        'Monocle.Entity.cs': [(10, 482), (493, 540), (551, 581), (627, 634), (648, 658), (682, 690), (728, 738), (762, 776), (893, 896), (923, 946), (995, 998)],
        'Monocle.Scene.cs': [(10, 28), (32, 43), (63, 91), (126, 129), (141, 145), (356, 367), (810, 830), (839, 847), (892, 913)],
        'Monocle.Collider.cs': [[1, 10000]],
        'Monocle.Hitbox.cs': [[1, 112], [119, 10000]],
        'Monocle.Grid.cs': [[1, 375], [409, 10000]],
        'Celeste.BadelineOldsite.cs': [],
        'Celeste.WallBooster.cs': [],
        'Celeste.DreamBlock.cs': [],
        'Celeste.FlingBird.cs': [],
        'Celeste.Backdrop.cs': [(99, 155)],
        'Celeste.BackdropRenderer.cs': [(28, 76)],
        'Celeste.FormationBackdrop.cs': [(16, 48)],
        'Celeste.Overlay.cs': [],
        'Celeste.Pathfinder.cs': [(60, 65)],
        'Celeste.HiresSnow.cs': [],
        'Celeste.GameplayRenderer.cs': [(12, 16)],
        'Celeste.HudRenderer.cs': [],
        'Celeste.HiresRenderer.cs': [],
        'Celeste.TotalStrawberriesDisplay.cs': [(30, 92)],
        'Celeste.LightingRenderer.cs': [(88, 113)],
        'Celeste.BloomRenderer.cs': [(46, 49)],
        'Celeste.DisplacementRenderer.cs': [(43, 54), (126, 169)],
        'Celeste.TrailManager.cs': [(251, 265)],
        'Celeste.ClutterBlockGenerator.cs': [(156, 276)],
        'Celeste.ClutterBlock.cs': [],
        'Celeste.IOverlayHandler.cs': [],
        'Celeste.ClutterAbsorbEffect.cs': [],
        'Celeste.LightOcclude.cs': [],
        'Monocle.Shaker.cs': [],
        'Celeste.ClutterCabinet.cs': [],
    }
    replacement = ''
    actor = (room_source / 'source/Celeste.Actor.cs').read_text().splitlines()
    replacement += 'namespace Celeste {\n' + extract('Celeste.Actor.cs', [(7, len(actor))]) + '\n'
    replacement += extract('Celeste.Collision.cs', [(3, 3)]) + '\n' + extract('Celeste.CollisionData.cs', [(5, 18)]) + '\n}\n'
    content = content[:start] + replacement + content[end:]
    for name in ('VertexLight', 'MirrorReflection', 'SoundSource', 'Leader', 'Follower', 'StaticMover', 'WaterInteraction', 'WindMover', 'WindController', 'PostUpdateHook', 'EntityID', 'Assists', 'AreaKey', 'AreaMode', 'AreaModeStats', 'AreaStats', 'ModeProperties', 'AudioState', 'AudioTrackState', 'EntityData', 'LevelData', 'DecalData', 'MEP', 'CheckpointData', 'Tags', 'Trigger', 'SpawnFacingTrigger', 'BloomPoint'):
        content += whole('Celeste.' + name + '.cs', 'Celeste')
    content += whole('Celeste.PlayerInventory.cs', 'Celeste')
    for name in ('BackgroundTiles',):
        content += whole('Celeste.' + name + '.cs', 'Celeste')
    for name in ('Autotiler', 'AnimatedTiles', 'AnimatedTilesBank', 'SolidTiles', 'Platform', 'Solid', 'JumpThru', 'SurfaceIndex', 'DashCollision', 'DashCollisionResults', 'ClimbBlocker', 'StrawberriesCounter', 'BeforeRenderHook'):
        content += whole('Celeste.' + name + '.cs', 'Celeste')
    for name in ('Camera', 'BitTag', 'ParticleType', 'ParticleSystem', 'Particle', 'Wiggler', 'Pooled', 'VirtualAsset', 'VirtualRenderTarget'):
        content += whole('Monocle.' + name + '.cs', 'Monocle')
    for name in ('BlendState', 'Blend', 'BlendFunction', 'ColorWriteChannels', 'GraphicsResource', 'IVertexType', 'VertexElement', 'VertexElementFormat', 'VertexElementUsage', 'VertexDeclaration'):
        content += whole('Microsoft.Xna.Framework.Graphics.' + name + '.cs', 'Microsoft.Xna.Framework.Graphics')
    content += whole('Monocle.VirtualMap.cs', 'Monocle')
    content += whole('Monocle.Tileset.cs', 'Monocle')
    content += whole('Monocle.TileGrid.cs', 'Monocle')
    content += 'namespace Monocle { public struct SimpleCurve {\n' + extract('Monocle.SimpleCurve.cs', [(7, 45)]) + '\n}\n}\n'
    content += 'namespace Microsoft.Xna.Framework { public struct Point : IEquatable<Point> {\n' + extract('Microsoft.Xna.Framework.Point.cs', [(13, 85)]) + '\n}\n}\n'
    content = content.replace('public struct Vector2 : IEquatable<Vector2>', 'public partial struct Vector2 : IEquatable<Vector2>', 1)
    content += 'namespace Microsoft.Xna.Framework { public partial struct Vector2 {\n' + extract('Microsoft.Xna.Framework.Vector2.cs', [(92, 216), (222, 355), (404, 432)]) + '\n}\n'
    content += 'public struct Vector3 : IEquatable<Vector3> {\n' + extract('Microsoft.Xna.Framework.Vector3.cs', [(14, 108)]) + '\n}\n'
    content += 'public struct Matrix : IEquatable<Matrix> {\n' + extract('Microsoft.Xna.Framework.Matrix.cs', [(13, 45), (89, 89), (149, 167), (201, 223), (676, 754), (787, 837), (977, 1040), (1083, 1154), (1334, 1347)]) + '\n}\n}\n'
    content = content.replace('public struct Rectangle {', 'public partial struct Rectangle : IEquatable<Rectangle> {', 1)
    content += 'namespace Microsoft.Xna.Framework { public partial struct Rectangle {\n' + extract('Microsoft.Xna.Framework.Rectangle.cs', [(31, 60), (70, 214)]) + '\n}\n}\n'
    content += 'namespace Microsoft.Xna.Framework.Graphics { public struct Viewport {\n' + extract('Microsoft.Xna.Framework.Graphics.Viewport.cs', [(8, 129)]) + '\n}\n}\n'
    if 'Celeste.SaveData.cs' not in declarations:
        content += 'namespace Celeste { public partial class SaveData {\n' + extract('Celeste.SaveData.cs', [(10, 136)]) + '\n}\n}\n'
    content += 'namespace Celeste { public partial class Session {\n' + extract('Celeste.Session.cs', [(12, 125), (170, 232), (251, 276)]) + '\n}\n'
    content += 'public static class BinaryPacker {\n' + extract('Celeste.BinaryPacker.cs', [(11, 64)]) + '\n}\n}\n'
    content += 'namespace Celeste { public class AreaData {\n' + extract('Celeste.AreaData.cs', [(12, 80), (84, 92), (820, 851), (867, 900), (907, 954)]) + '\n}\n}\n'
    content += 'namespace DeathOracle { using global::Celeste; using static global::Celeste.AreaData; static class RoomCoreAreaInput { public static void Configure() {\n'
    content += extract('Celeste.AreaData.cs', [(96, 191)]) + '\nAreas[1].ID = 1;\nAreas[1].Spike = "default";\n} } }\n'
    manifest['caller_area_input'] = 'First two original area object initializers plus declared Spike atlas id only; original AreaData.Load/global map loading is not executed or claimed'
    manifest['caller_runtime_profile'] = 'Declared 1920x1080 camera viewport, empty audio events with inert SFX cache, source Lighting/Bloom/Hud renderers, field-only room header, declared LevelLoader field subset for Particles/StrawberriesDisplay, pinned GUI atlas metadata, no-device rumble profile, and an Engine.Scene/Pooler driver fixture; no original startup, save-audio, full LevelLoader, or input-device parity'
    content += whole('Monocle.Collide.cs', 'Monocle')
    selected_files = {entry['file'] for entry in manifest['extractions']}
    for name in declarations:
        if name not in selected_files:
            frontier_ranges.setdefault(name, [(10, 136)] if name == 'Celeste.SaveData.cs' else [])
    selections = []
    for name, ranges in frontier_ranges.items():
        path = next(directory / name for directory in locations if (directory / name).is_file())
        selection = {'Source': str(path), 'Sha256': pins[name], 'ExecutableRanges': ranges,
            'Aliases': ['Random = PresentationOracle.TracedRandom'], 'AllowNativeAbiDeclarations': True, 'ExecutableImplicitTypes': {
                'Celeste.Level.cs': ['Level'], 'Celeste.BackdropRenderer.cs': ['BackdropRenderer'],
                'Celeste.DisplacementRenderer.cs': ['DisplacementRenderer'], 'Celeste.HudRenderer.cs': ['HudRenderer'],
                'Celeste.HiresRenderer.cs': ['HiresRenderer'], 'Celeste.SaveData.cs': ['SaveData'],
                'Monocle.Binding.cs': ['Binding']}.get(name, [])}
        if name == 'SDL2.SDL.cs':
            selection['ManagedPlatformFixture'] = {
                'OriginalMethodSha256': '2d269f2c750dd882d9b233e66422d06b38ab9b3d11ed77aed537bfbfd78fcafe',
                'OriginalBodySha256': '87ceb960ed5b2f65cbbbd38d1ce60396c2845de54ea639fd97276d651830ecfa',
                'ReplacementBodySha256': '36d3155ba05e7066484857c0c559dbdf5aae08c2ea1ea94d61d84c03e47b1a53',
                'Profile': 'pc-linux', 'Reason': 'Parent-approved managed reference-platform identity input Linux; not original SDL wrapper/native execution or physical Vita identity'}
        selections.append(selection)
    tool = build_tool(output / 'frontier-tool')
    frontier, inventory = emit_frontier(tool, selections, output)
    frontier = remove_fixture_class(frontier, 'Distort')
    inventory['Declarations'] = [entry for entry in inventory['Declarations'] if not entry['File'].endswith('/Celeste.Distort.cs')]
    inventory['OutputSha256'] = hashlib.sha256(frontier.encode()).hexdigest()
    (output / 'Frontier.cs').write_text(frontier)
    (output / 'frontier-inventory.json').write_text(json.dumps({key: inventory[key] for key in
        ('Executable', 'Declarations', 'ManagedPlatformFixtures', 'OutputSha256')}, indent=2) + '\n')
    manifest['executable_members'] = inventory['Executable']
    manifest['declaration_contracts'] = inventory['Declarations']
    manifest['native_abi_declarations'] = [entry for entry in inventory['Declarations'] if entry['Kind'] == 'native-abi']
    root_contract_files = ('FMOD.ADVANCEDSETTINGS.cs', 'FMOD.SYSTEM_CALLBACK.cs', 'FMOD.SYSTEM_CALLBACK_TYPE.cs', 'FMOD.DSP_RESAMPLER.cs')
    manifest['native_abi_root_contracts'] = [{'file': name, **declarations[name]} for name in root_contract_files if name in declarations]
    manifest['native_abi_root_contract_policy'] = 'Original root FMOD types are pinned declaration contracts beside FMOD.System so unqualified parameter types bind to FMOD, not FMOD.Studio. No native bodies or Studio/root normalization.'
    manifest['managed_platform_fixtures'] = inventory['ManagedPlatformFixtures']
    manifest['frontier_output_sha256'] = inventory['OutputSha256']
    manifest['recording_gpu_boundary'] = {
        'type': 'Celeste.Distort', 'source_file': 'tests/native/oracle/death/RoomCoreGpu.cs',
        'source_sha256': hashlib.sha256((ROOT / 'tests/native/oracle/death/RoomCoreGpu.cs').read_bytes()).hexdigest(),
        'reason': 'Source Reload writes Distort presentation floats; original GPU effect parameter writes are replaced by a typed recording boundary. State fields are preserved; lifecycle, RNG, clocks and ownership remain source.'}
    lifecycle_files = {'Celeste.PlayerDeadBody.cs', 'Celeste.DeathEffect.cs', 'Celeste.ScreenWipe.cs', 'Celeste.AngledWipe.cs'}
    manifest['death_lifecycle_sources'] = [entry for entry in manifest['extractions'] if entry['file'] in lifecycle_files]
    manifest['death_lifecycle_claim'] = 'Whole unchanged death presentation/coroutine bodies from the accepted baseline extraction, compiled beside the room-core cut; caller invokes Player.Die as probe stimulus only.'
    manifest['stats_boundary'] = 'Original SaveData.AddDeath executes its session/AreaModeStats/TotalDeaths writes; platform telemetry leaves Stats/StatsForStadia use recording no-op fixtures. No telemetry or persistence parity is claimed.'
    manifest['driver_scene_boundary'] = 'Engine.Scene is initialized once to the same Level instance before execution as a declared driver environment. The caller never swaps Scene, Player, position, or state to claim reload; the reload is observed only from the source-created second Player, LoadLevel wipe-in, and wipe OnComplete=Level.Reload. Original Engine.Update is not executed.'
    manifest['frontier_recipe_sha256'] = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (ROOT / 'scripts/room_core_frontier.py', ROOT / 'tests/native/oracle/death/DeclarationFrontier.cs')}
    content += 'namespace Celeste.Editor {}\nnamespace Celeste.Pico8 {}\nnamespace SDL2 {}\nnamespace Microsoft.Xna.Framework.Audio {}\nnamespace Microsoft.Xna.Framework.Media {}\nnamespace Microsoft.Xna.Framework.Input.Touch {}\nnamespace MonoGame.Utilities {}\n' + frontier
    content = content.replace('using System; ', 'using FMOD.Studio; using System.Xml.Serialization; using System.IO; using System.Runtime.InteropServices; using System; ', 1)
    (output / 'Extracted.cs').write_text(content)
    manifest['extracted_sha256'] = hashlib.sha256(content.encode()).hexdigest()
    (output / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    identity = verify_extraction(output)
    (output / 'source-identity.json').write_text(json.dumps(identity, indent=2) + '\n')
    (output / 'Geometry.cs').write_bytes((baseline / 'Geometry.cs').read_bytes())
    shared = room_shared_support((baseline / 'Shared.cs').read_text())
    shared = remove_fixture_class(shared, 'Calc')
    if 'Celeste.Dust.cs' in declarations:
        shared = remove_fixture_class(shared, 'Dust')
    if 'Monocle.Draw.cs' in declarations:
        shared = remove_fixture_class(shared, 'Draw')
    if 'Celeste.GFX.cs' in declarations:
        shared = remove_fixture_class(shared, 'GFX')
    (output / 'Shared.cs').write_text(shared)
    manifest['pending_mechanical_support'] = {
        'claim': 'Legacy presentation-only approximations now throw on invocation; these are NOT implemented room-core services',
        'methods': ['Dust.BurstFG', 'Dust.Burst'],
        'generated_shared_sha256': hashlib.sha256(shared.encode()).hexdigest()}
    services = (baseline / 'Services.cs').read_text()
    for name in ('Player', 'Level', 'Entity', 'Collider', 'VertexLight', 'Leader', 'Follower', 'WindController', 'SaveData', 'Session', 'Camera', 'BitTag', 'Tags', 'Matrix', 'Vector3', 'TrailManager', 'PoolBoundary', 'Engine', 'GFX', 'Calc', 'VertexPositionColor', 'Glitch', 'Distort', 'SampledButton', 'AssistProfile', 'ClearBoundary', 'CounterDisplay', 'DisplacementBoundary', 'GraphicsBoundary', 'DeviceBoundary', 'ViewportBoundary'):
        services = remove_fixture_class(services, name)
    for name in ('Strawberry', 'LevelExit', 'Lookout', 'Textbox', 'Booster', 'CassetteBlockManager', 'Holdable', 'Input', 'Audio'):
        if 'Celeste.' + name + '.cs' in declarations:
            services = remove_fixture_class(services, name)
    for name in ('RumbleStrength', 'RumbleLength'):
        if 'Celeste.' + name + '.cs' in declarations:
            services, count = re.subn(r'    public enum ' + name + r' \{[^\n]+\}\n', '', services)
            if count != 1:
                raise ValueError('Missing original enum replacement: ' + name)
    (output / 'Services.cs').write_text(services)
    (output / 'RoomCoreProbe.cs').write_bytes((ROOT / 'tests/native/oracle/death/RoomCoreProbe.cs').read_bytes())
    (output / 'RoomCoreGpu.cs').write_bytes((ROOT / 'tests/native/oracle/death/RoomCoreGpu.cs').read_bytes())
    for name in ('NativeImportGuard.cs', 'NativeImportGuardProbe.cs', 'RoomCoreExecution.cs', 'NativeAbiMetadataAudit.cs', 'PlatformIdentityFixture.cs', 'PlatformIdentityFixtureProbe.cs', 'RoomCoreRoomInput.cs', 'RoomCoreCaller.cs'):
        (output / name).write_bytes((ROOT / 'tests/native/oracle/death' / name).read_bytes())
    manifest['room_core_support_sha256'] = {'tests/native/oracle/death/RoomCoreProbe.cs': hashlib.sha256((output / 'RoomCoreProbe.cs').read_bytes()).hexdigest(),
        'Services.cs_after_fixture_removal': hashlib.sha256(services.encode()).hexdigest(),
        'scripts/read_player_room_core_sources.py': hashlib.sha256((ROOT / 'scripts/read_player_room_core_sources.py').read_bytes()).hexdigest()}
    manifest['room_core_support_sha256']['tests/native/oracle/death/RoomCoreGpu.cs'] = hashlib.sha256((output / 'RoomCoreGpu.cs').read_bytes()).hexdigest()
    for name in ('NativeImportGuard.cs', 'NativeImportGuardProbe.cs', 'RoomCoreExecution.cs', 'NativeAbiMetadataAudit.cs', 'PlatformIdentityFixture.cs', 'PlatformIdentityFixtureProbe.cs', 'RoomCoreRoomInput.cs', 'RoomCoreCaller.cs'):
        manifest['room_core_support_sha256']['tests/native/oracle/death/' + name] = hashlib.sha256((output / name).read_bytes()).hexdigest()
    for fixture in manifest['managed_platform_fixtures']:
        fixture['ReferencePlatform'] = 'Linux'
        fixture['Provider'] = 'tests/native/oracle/death/PlatformIdentityFixture.cs'
        fixture['ProviderSha256'] = manifest['room_core_support_sha256'][fixture['Provider']]
    manifest['native_abi_exclusion'] = 'Unchanged extern/DllImport contracts, not managed implementations. Generated assembly module initializer installs its sole throwing native resolver before source initialization. No native loading or default fallthrough. Resolver follows native loading caches: interception is proven only for the pinned import in fresh diagnostic processes without prior native bindings or FMOD mappings, not as a universal block. Isolated negative tests are not real RoomCore coverage.'
    manifest['gpu_exclusion'] = 'Typed recording-only device/resources; original GraphicsResource ownership callbacks, VertexDeclaration metadata/stride, geometry/math, RNG, clocks and gameplay callbacks remain source bodies. No GPU pixels or full FNA backend fidelity.'
    manifest['audio_boundary'] = 'Declared inert event-description cache entries map the pinned SFX path constants to null before source execution. Original Audio/Player/SoundSource bodies execute and receive no event instances. No FMOD system, native audio, sound, music, or startup-audio parity is claimed.'
    manifest['immutable_map_input'] = 'Field-only preloaded single-room input storage. MapData constructor/Load/Reload remain guarded; no original map constructor or its field-initializer execution is claimed for this supplied input object. Original Get/TileBounds execute. Remaining world/caller construction is incomplete; no whole-map/LevelLoader fidelity.'
    (output / 'presentation-stripped-room.json').write_bytes((room_source / 'presentation-stripped-room.json').read_bytes())
    for name in ('atlas.json', 'Sprites.xml'):
        data = (baseline / name).read_bytes() if name == 'atlas.json' else (source / 'presentation' / name).read_bytes()
        (output / name).write_bytes(data)
        manifest['room_core_support_sha256'][str(name)] = hashlib.sha256(data).hexdigest()
    (output / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (output / 'Oracle.csproj').write_text(project_text())
    (output / 'NuGet.Config').write_bytes((baseline / 'NuGet.Config').read_bytes())
    compile_project(output, identity, before)
    audit = native_abi_audit(output)
    manifest['native_abi_identity'] = {
        'generatedNativeImports': audit['generatedNativeImports'],
        'originalNativeImports': audit['originalNativeImports'],
        'allGeneratedNativeBodiesNull': audit['allGeneratedNativeBodiesNull'],
        'failures': len(audit['failures']),
        'rootContracts': [{'name': contract['name'], 'ok': contract['ok']} for contract in audit['rootContracts']],
        'expectedRootTypes': audit['expectedRootTypes'],
        'wrongStudioTypes': audit['wrongStudioTypes'],
        'nativeCalls': audit['nativeCalls'],
        'normalization': audit['normalization']}
    manifest['native_abi_identity_report_sha256'] = hashlib.sha256((output / 'native-abi-identity.json').read_bytes()).hexdigest()
    (output / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    result = {'status': 'compiled-bounded-respawn-and-death-roundtrip-not-family-closure', 'source_identity': identity,
        'source_revision': before[0], 'source_changes': before[1], 'native_abi_declarations': len(manifest['native_abi_declarations']),
        'native_abi_identity_failures': len(audit['failures']), 'native_abi_root_contract_failures': sum(not contract['ok'] for contract in audit['rootContracts']),
        'claim': 'Compilation only in this recipe; separate fresh-process executions establish one bounded Respawn14->Normal0 live tick and one caller-stimulated Die/corpse/wipe/Reload/second-Respawn round trip; zero of eight families closed'}
    (output / 'probe-result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--room-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--helpers-only', action='store_true', help='Execute isolated save/golden/RNG/clutter helpers, never lifecycle acceptance')
    parser.add_argument('--declarations-source', type=Path, action='append')
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.room_source, args.output, args.helpers_only, args.declarations_source), indent=2))
