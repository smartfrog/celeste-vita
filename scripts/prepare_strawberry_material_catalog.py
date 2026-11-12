"""Prepare eight private Strawberry atlas frames and the source idle sequence."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from prepare_spike_material_catalog import ATLAS_SHA, file_identity, fnv1a, read_atlas_frame, require

AUDIT = Path('/home/fred/projects/celeste-vita/.audit/native-strawberry-command-projection-01')
SOURCE_SHA = '8fa498d3ff01ed6dbdb779a2caced5a263a1f86dd52f234a6a9ec8f2e6bda6a8'
SPRITES_SHA = 'baec20ec28911be5ef8acc6b181c6818095aa867c692c14d57d26e42c00fc04a'


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate atlas key: ' + key)
        result[key] = value
    return result


def materials(atlas, sprites):
    berries = sprites.findall('strawberry')
    require(len(berries) == 1, 'Missing or duplicate Strawberry sprite')
    berry = berries[0]
    require(berry.get('start') == 'idle' and len(berry.findall('Center')) == 1,
            'Unsupported Strawberry initial animation/origin')
    idle = [child for child in berry if child.get('id') == 'idle']
    require(len(idle) == 1 and idle[0].tag == 'Loop' and idle[0].get('delay') == '.1',
            'Missing, duplicate or unsupported Strawberry idle animation')
    sequence = []
    for group in idle[0].get('frames', '').split(','):
        require(re.fullmatch(r'[0-7]-[0-7]', group) is not None, 'Invalid Strawberry idle frame range')
        start, end = map(int, group.split('-'))
        require(start <= end, 'Reversed Strawberry idle frame range')
        sequence.extend(range(start, end + 1))
    require(sequence == list(range(7)) * 4 + list(range(8)), 'Unsupported Strawberry idle sequence')
    prefix = berry.get('path', '') + idle[0].get('path', '')
    require(prefix and '..' not in prefix and not prefix.startswith('/'), 'Invalid Strawberry frame prefix')
    frames = [read_atlas_frame(atlas, prefix + f'{index:02}') for index in range(8)]
    return frames, sequence


def encode(frames, sequence):
    lines = ['CSTR1', SOURCE_SHA, ATLAS_SHA, SPRITES_SHA, 'idle 36',
             ' '.join(map(str, sequence)), '8']
    for index, frame in enumerate(frames):
        lines.append(' '.join(map(str, [index, frame['sheet'], frame['x'], frame['y'],
                                       frame['width'], frame['height'], frame['offset_x'],
                                       frame['offset_y'], frame['frame_width'], frame['frame_height'], frame['key']])))
    return ('\n'.join(lines) + '\n').encode('ascii')


def prepare(atlas_path, sprites_path, source_path, output):
    require(output.resolve().is_relative_to(AUDIT), 'Strawberry catalog must remain private')
    require(not output.parent.exists(), 'Strawberry descriptor directory must be fresh and exclusive')
    inputs = {}
    for name, path, pin in [('atlas', atlas_path, ATLAS_SHA), ('sprites', sprites_path, SPRITES_SHA),
                             ('source', source_path, SOURCE_SHA)]:
        identity = file_identity(path)
        require(identity['sha256'] == pin, 'Pinned Strawberry ' + name + ' changed')
        inputs[name] = {'path': str(path), **identity}
    atlas = json.loads(atlas_path.read_text(), object_pairs_hook=unique_object)
    require(isinstance(atlas, dict) and atlas, 'Invalid atlas payload')
    frames, sequence = materials(atlas, ET.parse(sprites_path).getroot())
    data = encode(frames, sequence)
    output.parent.mkdir(parents=True, exist_ok=False)
    with output.open('xb') as stream:
        stream.write(data)
    receipt = {'schema': 1, 'kind': 'native-strawberry-material-catalog-01', 'inputs': inputs,
               'frames': frames, 'idle': sequence,
               'output': {'path': str(output), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                          'fnv1a': f'{fnv1a(data):08x}'}}
    with (output.parent / 'receipt.json').open('x') as stream:
        json.dump(receipt, stream, indent=2)
        stream.write('\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--atlas', type=Path, required=True)
    parser.add_argument('--sprites', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.atlas, args.sprites, args.source, args.output), indent=2))
