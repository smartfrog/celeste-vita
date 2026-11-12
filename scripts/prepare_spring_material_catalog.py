"""Prepare one private idle Floor Spring frame from pinned cached original inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from native_room_textures import atlas_metadata
from prepare_spike_material_catalog import fnv1a, read_atlas_frame, require
from prepare_strawberry_material_catalog import unique_object

AUDIT = Path('/home/fred/projects/celeste-vita/.audit/native-spring-command-projection-01')
PINS = {
    'spring': '36a931e162387df599b88df84d851541be25001d24a5114084c6d06c461939d7',
    'sprite': '5095f3b86a78844a4076e1744b28e8ee493923baa920bb06b3497d7f253ebfee',
    'graphics': '7aea400b2428df2708b31c844f0dd15b797c419a4a63f945a473127ab3c4c210',
    'mtexture': '45847f23970911b07541e4bc367cbd156f3b4b1846b63b33d3fed9c7b65ebf6b',
    'image': 'aa87a22589821fc3781672126e68f2195fb46348f261013d8a01c070b53821d3',
    'meta': '1f23b1f35544a3751ffec170b0230c7c9513000ab1549f78ebb9cb9f4203c8d9',
    'atlas': 'b75f913d315bd641c35a4990d9041b238c0d9ef3f8b1247ec557de8a9defc1cc',
}


def materials(atlas, metadata, prefix):
    require(isinstance(atlas, dict) and atlas and isinstance(metadata, dict), 'Invalid Spring atlas metadata')
    require(isinstance(prefix, str) and prefix and prefix.endswith('/'), 'Invalid Spring resource prefix')
    keys = [prefix + f'{index:02}' for index in range(6)] + [prefix + 'white']
    require({key for key in atlas if key.startswith(prefix)} == set(keys), 'Missing or unknown Spring family resource')
    frames = []
    for key in keys:
        frame = read_atlas_frame(atlas, key)
        require(key in metadata and tuple(atlas[key]) == metadata[key], 'Spring raw/JSON atlas metadata differs')
        require(frame['sheet'] == 'Gameplay0' and
                0 <= -frame['offset_x'] <= frame['frame_width'] - frame['width'] and
                0 <= -frame['offset_y'] <= frame['frame_height'] - frame['height'], 'Unsupported Spring trim/sheet')
        frames.append(frame)
    idle = frames[0]
    require(all((frame['frame_width'], frame['frame_height']) == (idle['frame_width'], idle['frame_height'])
                for frame in frames), 'Unsupported Spring Sprite maximum logical dimensions')
    return idle


def encode(inputs):
    require(set(inputs) == set(PINS), 'Invalid Spring input names')
    for name, pin in PINS.items():
        require(hashlib.sha256(inputs[name]).hexdigest() == pin, 'Spring input pin changed: ' + name)
    prefixes = re.findall(r'new Sprite\(GFX\.Game, "([^"]+)"\)', inputs['spring'].decode('utf-8'))
    require(len(prefixes) == 1, 'Unsupported Spring constructor resource binding')
    atlas = json.loads(inputs['atlas'], object_pairs_hook=unique_object)
    frame = materials(atlas, atlas_metadata(inputs['meta']), prefixes[0])
    row = [frame[name] for name in ('sheet','x','y','width','height','offset_x','offset_y','frame_width','frame_height','key')]
    return ('\n'.join(['CSPR1', *PINS.values(), 'floor idle 0 0', '1', ' '.join(map(str,row))]) + '\n').encode('ascii')


def prepare(paths, output):
    require(set(paths) == set(PINS), 'Invalid Spring input names')
    require(output.resolve().is_relative_to(AUDIT), 'Spring catalog must remain private')
    require(not output.parent.exists(), 'Spring descriptor directory must be fresh and exclusive')
    inputs = {name: path.read_bytes() for name, path in paths.items()}
    data = encode(inputs)
    receipt = {'schema': 1, 'kind': 'bounded-idle-floor-spring-material', 'frames': 1,
               'inputs': {name: {'path': str(paths[name]), 'bytes': len(value), 'sha256': PINS[name]}
                          for name,value in inputs.items()},
               'output': {'path': str(output), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                          'fnv1a': f'{fnv1a(data):08x}'},
               'scope': 'Idle frame0 delay0, inactive wiggler, Floor only; no Sprites.xml or image generation'}
    output.parent.mkdir(parents=True, exist_ok=False)
    with output.open('xb') as stream:
        stream.write(data)
    with (output.parent / 'receipt.json').open('x') as stream:
        json.dump(receipt, stream, indent=2)
        stream.write('\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in PINS:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare({name:getattr(args,name) for name in PINS},args.output),indent=2))
