"""Prepare the bounded default Dust material from pinned cached Source, in place."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from prepare_spike_material_catalog import ATLAS_SHA, file_identity, fnv1a, read_atlas_frame, require
from prepare_strawberry_material_catalog import unique_object

AUDIT = Path('/home/fred/projects/celeste-vita/.audit/native-particle-command-projection-01')
SOURCE_SHA = 'b1b3485177af52ce8e5a9b10dca4eb10cb9d37180e9fdeff76e043e67708b64e'


def materials(atlas, source):
    match = re.search(r'Chooser<MTexture> sourceChooser = new Chooser<MTexture>\(([^;]+)\);', source)
    require(match is not None, 'Missing Dust texture chooser')
    keys = re.findall(r'GFX.Game\["([^"\n]+)"\]', match[1])
    require(len(keys) == 4 and len(set(keys)) == 4, 'Unsupported Dust texture chooser')
    frames = [read_atlas_frame(atlas, key) for key in keys]
    require(all(frame['frame_width'] == 8 and frame['frame_height'] == 8 for frame in frames),
            'Unsupported Dust original center')
    return frames


def encode(frames):
    lines = ['CDUS1', SOURCE_SHA, ATLAS_SHA, 'Dust 4']
    for index, frame in enumerate(frames):
        lines.append(' '.join(map(str, [index, frame['sheet'], frame['x'], frame['y'],
                                       frame['width'], frame['height'], frame['offset_x'], frame['offset_y'],
                                       frame['frame_width'], frame['frame_height'], frame['key']])))
    return ('\n'.join(lines) + '\n').encode('ascii')


def prepare(atlas_path, source_path, output):
    require(output.resolve().is_relative_to(AUDIT), 'Dust catalog must remain private')
    require(not output.parent.exists(), 'Dust descriptor directory must be fresh and exclusive')
    inputs = {}
    for name, path, pin in [('atlas', atlas_path, ATLAS_SHA), ('source', source_path, SOURCE_SHA)]:
        identity = file_identity(path)
        require(identity['sha256'] == pin, 'Pinned Dust ' + name + ' changed')
        inputs[name] = {'path': str(path), **identity}
    atlas = json.loads(atlas_path.read_text(), object_pairs_hook=unique_object)
    require(isinstance(atlas, dict) and atlas, 'Invalid atlas payload')
    frames = materials(atlas, source_path.read_text())
    data = encode(frames)
    output.parent.mkdir(parents=True, exist_ok=False)
    with output.open('xb') as stream:
        stream.write(data)
    receipt = {'schema': 1, 'kind': 'native-dust-material-catalog-01', 'inputs': inputs,
               'frames': frames, 'output': {'path': str(output), 'bytes': len(data),
                                           'sha256': hashlib.sha256(data).hexdigest(), 'fnv1a': f'{fnv1a(data):08x}'}}
    with (output.parent / 'receipt.json').open('x') as stream:
        json.dump(receipt, stream, indent=2)
        stream.write('\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--atlas', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.atlas, args.source, args.output), indent=2))
