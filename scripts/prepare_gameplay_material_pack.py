"""Prepare a private 26-crop completion pack; never execute Source or export its atlas.

The caller supplies a SHA-256-pinned private profile: files maps producer roles to
{path, bytes, sha256}; pins contains additional source inputs; archive identifies
the original zip; members pins its required members. Page files remain in place.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct

from game_input import read_members
from native_material_pack import pack_crops, verify_pin, write_new
from native_room_textures import atlas_metadata, extrude, plan_rectangles
from prepare_spike_material_catalog import read_atlas_frame, require
from stage_native_room import checksum

AUDIT = Path('/home/fred/projects/celeste-vita/.audit/native-gameplay-material-pack-01')
CATALOGS = {'decals': ('CDSC2', 27), 'spikes': ('CSPK1', 2),
            'strawberries': ('CSTR1', 8), 'jumpthru': ('CJTC1', 1),
            'spring': ('CSPR1', 1), 'dust': ('CDUS1', 4)}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def crop_bytes(page, page_width, x, y, width, height):
    return b''.join(page[((y + dy) * page_width + x) * 4:
                         ((y + dy) * page_width + x + width) * 4] for dy in range(height))


def encode_table(pages, bindings):
    lines = ['CSMT1', str(len(pages))]
    lines += [f'{i} {page["width"]} {page["height"]}' for i, page in enumerate(pages)]
    lines.append(str(len(bindings)))
    for key, binding in sorted(bindings.items()):
        frame, layout, aliases = binding['frame'], binding['layout'], binding['aliases']
        lines.append(' '.join(map(str, [4096, 4096, *layout, frame['width'], frame['height'], 0, len(aliases)])))
        lines.append(' '.join(map(str, [frame['sheet'], frame['x'], frame['y'], frame['width'], frame['height'],
                                       frame['offset_x'], frame['offset_y'], frame['frame_width'], frame['frame_height'], key])))
        lines.extend(aliases)
    return ('\n'.join(lines) + '\n').encode('ascii')


def reconstruct(files, atlas):
    bindings = {}

    def add(key, alias=None):
        require(key not in bindings, 'Duplicate parent material: ' + key)
        frame = read_atlas_frame(atlas, key)
        require(frame['sheet'] == 'Gameplay0', 'Parent left pinned Gameplay0')
        bindings[key] = {'frame': frame, 'aliases': [alias] if alias and alias != key else []}

    for role, (magic, expected) in CATALOGS.items():
        lines = files[role].decode('ascii').splitlines()
        require(lines[0] == magic, 'Unsupported producer catalog: ' + role)
        rows = []
        for line in lines:
            fields = line.split(' ')
            if 'Gameplay0' in fields and len(fields) in (10, 11):
                start = fields.index('Gameplay0')
                row = fields[start:]
                require(len(row) == 10, 'Malformed producer atlas row: ' + role)
                alias = row[-1]
                key = 'decals/' + alias.replace('\\', '/').removesuffix('.png') if role == 'decals' else alias
                add(key, alias)
                frame = bindings[key]['frame']
                require([row[0], *map(int, row[1:9])] == [frame['sheet'], frame['x'], frame['y'],
                        frame['width'], frame['height'], frame['offset_x'], frame['offset_y'],
                        frame['frame_width'], frame['frame_height']], 'Producer/atlas disagreement: ' + key)
                rows.append(key)
        require(len(rows) == expected, 'Producer parent count changed: ' + role)

    terrain = files['terrain'].decode('ascii').splitlines()
    require(terrain[0] == 'CSTV1' and terrain[6:9] == ['1', 'Gameplay0 4096 4096', '335'],
            'Pinned terrain catalog shape changed')
    families = set()
    for row in terrain[9:344]:
        fields = row.split(' ')
        key = fields[0]
        if key not in families:
            add(key)
            families.add(key)
        frame = bindings[key]['frame']
        x, y, width, height = map(int, fields[2:6])
        require(fields[1] == '0' and width == height == 8 and x >= frame['x'] and y >= frame['y'] and
                x + width <= frame['x'] + frame['width'] and y + height <= frame['y'] + frame['height'],
                'Terrain material outside parent')
    require(len(families) == 5, 'Terrain parent family count changed')

    logical = files['player_original'].decode('ascii').splitlines()
    packed = files['player_packed'].decode('ascii').splitlines()
    require(logical[:2] == ['CPLAYERDRAW1', '226'] and len(logical) == 228 and
            packed[0] == 'CSPP1' and packed[3] == '6' and packed[10] == '226', 'Player catalog shape changed')
    packed_rows = {row.split(' ')[0]: row.split(' ') for row in packed[11:237]}
    require(len(packed_rows) == 226 and packed[237] == '33', 'All Player frames/animations required')
    for line in logical[2:]:
        row = line.split(' ')
        key = row[0]
        add(key)
        frame = bindings[key]['frame']
        require(len(row) == 17 and row[10:13] == ['Gameplay0', '4096', '4096'] and
                list(map(int, row[13:17])) == [frame['x'], frame['y'], frame['width'], frame['height']] and
                list(map(int, row[4:10])) == [frame['width'], frame['height'], -frame['offset_x'],
                    -frame['offset_y'], frame['frame_width'], frame['frame_height']] and
                packed_rows[key][:10] == row[:10], 'Original/packed Player metadata disagreement: ' + key)
        bindings[key]['player_layout'] = list(map(int, row[1:4]))
    require(len(bindings) == 274, 'Expected all 274 parent bindings')
    return bindings


def prepare(profile_path, profile_sha, output, dry_run=False):
    require(output.resolve().parent == AUDIT and not output.exists(), 'Output must be fresh in canonical private namespace')
    profile = json.loads(verify_pin({'path': str(profile_path), 'bytes': profile_path.stat().st_size, 'sha256': profile_sha}))
    require(profile['schema'] == 1, 'Unsupported private profile')
    files = {role: verify_pin(pin) for role, pin in profile['files'].items()}
    for pin in profile['pins']:
        verify_pin(pin)
    verify_pin(profile['archive'])
    members = read_members(profile['archive']['path'], {name: pin['sha256'] for name, pin in profile['members'].items()})
    for name, data in members.items():
        require(len(data) == profile['members'][name]['bytes'], 'Archive member size pin failed: ' + name)
    verified_hashes = {pin['sha256'] for pin in [*profile['files'].values(), *profile['pins'], *profile['members'].values()]}
    for role in CATALOGS:
        for line in files[role].decode('ascii').splitlines():
            if len(line) == 64 and all(char in '0123456789abcdef' for char in line):
                require(line in verified_hashes, 'Catalog input lacks an actual verified pin: ' + role)
    source = members['Content/Graphics/Atlases/Gameplay0.data']
    require(len(source) >= 9 and struct.unpack_from('<iiB', source) == (4096, 4096, 1), 'Original sheet header changed')
    atlas = json.loads(files['atlas'])
    meta = members['Content/Graphics/Atlases/Gameplay.meta']
    require(atlas_metadata(meta) == {key: tuple(value) for key, value in atlas.items()}, 'Original meta/atlas JSON disagreement')
    bindings = reconstruct(files, atlas)
    base, visuals, decals, player = [json.loads(files[role]) for role in ('base_provenance', 'visual_provenance',
                                                                         'decal_provenance', 'player_provenance')]
    require(digest(files['player_bank']) == player['files']['bank.json'], 'Player bank pin disagreement')
    pages, page_data = [], []

    def page(role, width, height, expected):
        data = files[role]
        require(len(data) == width * height * 4 and digest(data) == expected, 'Old page pin/dimensions failed: ' + role)
        pages.append({'path': profile['files'][role]['path'], 'width': width, 'height': height,
                      'bytes': len(data), 'sha256': digest(data), 'reused': True})
        page_data.append(data)
        return len(pages) - 1

    old = {}
    for i in range(8):
        width, height = (64, 128) if i < 5 else (16, 16)
        index = page(f'visual_page_{i}', width, height, visuals['files'][f'texture{i}.rgba'])
        if i < 5:
            spec = base['textures'][i]
            old[spec['source']] = (index, 1, 1, spec['crop_sha256'])
        elif i > 5:
            spec = visuals['spike_textures'][i - 6]
            old[spec['source']] = (index, 1, 1, spec['crop_sha256'])
    index = page('decal_page', 64, 128, decals['files']['decal0.rgba'])
    for key, spec in decals['textures'].items():
        old[key] = index, spec['u'], spec['v'], spec['crop_sha256']
    player_pages = [page(f'player_page_{i}', 128, 64, player['files'][f'player{i}.rgba']) for i in range(6)]
    for key, binding in bindings.items():
        if 'player_layout' in binding:
            index, x, y = binding['player_layout']
            require(player['layout'][key] == [index, x, y], 'Player provenance layout disagreement')
            old[key] = player_pages[index], x, y, player['crop_sha256'][key]
    require(len(old) == 248 and set(old) <= set(bindings), 'All 248 reusable bindings required')
    for key, (index, x, y, expected) in old.items():
        b = bindings[key]
        f = b['frame']
        require(1 <= x <= pages[index]['width'] - f['width'] - 1 and
                1 <= y <= pages[index]['height'] - f['height'] - 1, 'Old crop bounds disagreement')
        require(digest(crop_bytes(page_data[index], pages[index]['width'], x, y, f['width'], f['height'])) == expected,
                'Old packed crop pixel hash failed: ' + key)
        b['layout'] = index, x, y
    missing = {key: b for key, b in bindings.items() if key not in old}
    require(len(missing) == 26, 'Completion pack must contain exactly 26 missing parents')
    shapes = {key: (b['frame']['width'], b['frame']['height']) for key, b in missing.items()}
    count, layout = plan_rectangles(shapes, 128, 128, 2)
    summary = {'bindings': len(bindings), 'reused': len(old), 'new': len(missing),
               'new_pages': count, 'new_rgba_bytes': count * 128 * 128 * 4, 'layout': layout}
    if dry_run:
        return summary
    from native_room_textures import decode_crops
    crops = decode_crops(source, {key: tuple(b['frame'][field] for field in ('x', 'y', 'width', 'height'))
                                 for key, b in missing.items()})
    new_pages, actual_layout = pack_crops({key: (*shapes[key], pixels) for key, pixels in crops.items()})
    require(actual_layout == layout and len(new_pages) == count, 'Dry-run/actual packing disagreement')
    for i, data in enumerate(new_pages):
        pages.append({'path': f'material{i}.rgba', 'width': 128, 'height': 128, 'bytes': len(data),
                      'sha256': digest(data), 'reused': False})
    for key, binding in missing.items():
        i, x, y = layout[key]
        width, height = shapes[key]
        require(crop_bytes(new_pages[i], 128, x, y, width, height) == crops[key], 'New crop pixel mismatch')
        require(crop_bytes(new_pages[i], 128, x - 1, y - 1, width + 2, height + 2) ==
                extrude(crops[key], width, height, width + 2, height + 2), 'New border pixel mismatch')
        binding['layout'] = len(page_data) + i, x, y
    table = encode_table(pages, bindings)
    manifest = {'schema': 1, 'profile_sha256': profile_sha, **summary, 'pages': pages,
                'table': {'bytes': len(table), 'sha256': digest(table), 'fnv1a': f'{checksum(table):08x}'},
                'crop_sha256': {key: digest(data) for key, data in sorted(crops.items())},
                'scope': 'Metadata and unchanged RGBA only; no GPU capacity, raster, or route readiness claim'}
    output.mkdir(parents=True, exist_ok=False)
    for i, data in enumerate(new_pages):
        write_new(output / f'material{i}.rgba', data)
    write_new(output / 'materials.txt', table)
    write_new(output / 'manifest.json', (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode())
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--profile-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare(args.profile, args.profile_sha256, args.output, args.dry_run), sort_keys=True, indent=2))
