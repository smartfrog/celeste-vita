"""Discover only compiler-requested private type contracts with the pinned ILSpy."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from check_native_oracle import ROOT, oracle_environment
from read_player_room_core_sources import SDK, TOOL, INPUTS
from read_player_presentation_sources import ILSPY_SHA
from prepare_room_visuals import MEMBERS


def missing_types(text):
    names = set()
    for line in text.splitlines():
        if ': error CS0246:' not in line:
            continue
        match = re.search(r"(?:noms|name) '([A-Za-z_][A-Za-z0-9_]*)'", line)
        if match is None:
            raise ValueError('Unrecognized missing declaration diagnostic: ' + line)
        names.add(match[1])
    return sorted(names)


def declaration_candidates(name, catalog):
    if name not in catalog and name.endswith('Attribute'):
        name = name.removesuffix('Attribute')
    candidates = list(dict.fromkeys(catalog.get(name, [])))
    direct = [value for value in candidates if value[1] in ('Celeste.' + name, 'Monocle.' + name)]
    return direct if len(direct) == 1 else candidates


def write_pins(source, destination, expected_sha256=None):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_relative_to(ROOT / '.audit/native-player-death-respawn'):
        raise ValueError('Pin generation requires immutable private discovery and a fresh destination')
    if destination != ROOT / 'tests/native/oracle/death/declaration-pins.json':
        raise ValueError('Unexpected declaration pin destination')
    receipt = json.loads((source / 'provenance.json').read_text())
    if receipt['tool_sha256'] != ILSPY_SHA or receipt['inputs'] != {name: MEMBERS[name] for name in ('Celeste.exe', 'FNA.dll', 'mscorlib.dll')}:
        raise ValueError('Declaration provenance identity changed')
    pins = {}
    if destination.exists():
        if expected_sha256 is None or hashlib.sha256(destination.read_bytes()).hexdigest() != expected_sha256:
            raise ValueError('Existing declaration pin version changed')
        pins = json.loads(destination.read_text())
    for entry in receipt['sources']:
        if hashlib.sha256((source / 'source' / entry['file']).read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('Declaration body identity changed: ' + entry['file'])
        value = {name: entry[name] for name in ('sha256', 'type', 'assembly')}
        if entry['file'] in pins and pins[entry['file']] != value:
            raise ValueError('Declaration source identity disagreement')
        pins[entry['file']] = value
    destination.write_text(json.dumps(pins, indent=2, sort_keys=True) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diagnostics', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reuse', type=Path, action='append', default=[])
    parser.add_argument('--require-type', action='append', default=[])
    parser.add_argument('--resolve-type', action='append', default=[])
    args = parser.parse_args()
    output, diagnostics = args.output.resolve(), args.diagnostics.resolve()
    private = ROOT / '.audit/native-player-death-respawn'
    if output.exists() or not output.is_relative_to(private) or not diagnostics.is_relative_to(private):
        raise ValueError('Declaration discovery must be fresh and private')
    inputs = {}
    for name in ('Celeste.exe', 'FNA.dll', 'mscorlib.dll'):
        inputs[name] = hashlib.sha256((INPUTS / name).read_bytes()).hexdigest()
        if inputs[name] != MEMBERS[name]:
            raise ValueError('Pinned input changed: ' + name)
    if hashlib.sha256(TOOL.read_bytes()).hexdigest() != ILSPY_SHA:
        raise ValueError('Pinned ILSpy changed')
    if any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name) for name in args.require_type):
        raise ValueError('Invalid explicit declaration request')
    names = sorted(set(missing_types(diagnostics.read_text())) | set(args.require_type))
    resolutions = {}
    for value in args.resolve_type:
        short, full = value.split('=', 1)
        if short not in names or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*', full) or short in resolutions:
            raise ValueError('Invalid explicit declaration resolution')
        resolutions[short] = full
    reused = {}
    for previous in args.reuse:
        previous = previous.resolve()
        if not previous.is_relative_to(private):
            raise ValueError('Reused declaration sources must remain private')
        prior = json.loads((previous / 'provenance.json').read_text())
        if prior['inputs'] != inputs or prior['tool_sha256'] != ILSPY_SHA:
            raise ValueError('Reused declaration provenance changed')
        for entry in prior['sources']:
            path = previous / 'source' / entry['file']
            if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
                raise ValueError('Reused declaration source identity changed')
            reused[entry['file']] = (path, entry)
    output.mkdir()
    (output / 'source').mkdir()
    receipt = {'inspection_only': True, 'declaration_only_requests': names, 'sources': [], 'commands': [], 'inputs': inputs,
        'tool_sha256': ILSPY_SHA, 'diagnostics_sha256': hashlib.sha256(diagnostics.read_bytes()).hexdigest(),
        'recipe_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}

    def run(arguments, target):
        command = list(map(str, [SDK, TOOL, '--disable-updatecheck', *arguments]))
        with target.open('xb') as log:
            result = subprocess.run(command, cwd=ROOT, env=oracle_environment(SDK), stdout=log, stderr=subprocess.STDOUT)
        receipt['commands'].append({'command': command, 'exit_code': result.returncode})
        (output / 'provenance.json').write_text(json.dumps(receipt, indent=2) + '\n')
        if result.returncode:
            raise RuntimeError('Pinned declaration discovery failed: ' + str(target))

    catalog = {}
    full_types = set()
    for assembly in ('Celeste.exe', 'FNA.dll'):
        for kind in ('c', 'i', 's', 'd', 'e'):
            target = output / (assembly + '-' + kind + '.txt')
            run(['-l', kind, INPUTS / assembly], target)
            for line in target.read_text().splitlines():
                match = re.fullmatch(r'(?:Class|Interface|Struct|Delegate|Enum) (\S+)', line)
                if match:
                    full = match[1]
                    full_types.add((assembly, full))
                    catalog.setdefault(full.rsplit('.', 1)[-1], []).append((assembly, full))
    for name in names:
        candidates = declaration_candidates(name, catalog)
        if name in resolutions:
            candidates = [value for value in candidates if value[1] == resolutions[name]]
        if len(candidates) != 1:
            raise ValueError('Ambiguous or missing original declaration: ' + name + ': ' + repr(candidates))
        assembly, full = candidates[0]
        while (assembly, full.rsplit('.', 1)[0]) in full_types:
            full = full.rsplit('.', 1)[0]
        filename = full.replace('`', '_') + '.cs'
        if any(entry['file'] == filename for entry in receipt['sources']):
            continue
        target = output / 'source' / filename
        if filename in reused:
            path, entry = reused[filename]
            target.write_bytes(path.read_bytes())
        else:
            run(['-r', INPUTS, '-t', full, INPUTS / assembly], target)
        receipt['sources'].append({'file': filename, 'type': full, 'assembly': assembly,
            'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'usage': 'declaration-contract-only; no gameplay implementation promotion'})
        (output / 'provenance.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
