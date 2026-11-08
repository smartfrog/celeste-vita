"""Emit source-pinned declaration contracts beside unchanged executable members."""

import hashlib
import json
from pathlib import Path
import subprocess

from check_native_oracle import ROOT, PRIVATE, oracle_environment

SDK = PRIVATE / 'tools/dotnet-8.0.425/dotnet'
TOOL_SOURCE = ROOT / 'tests/native/oracle/death/DeclarationFrontier.cs'


def project(source, roslyn=False):
    references = ''.join('<Reference Include="' + name + '"><HintPath>$(MSBuildSDKsPath)/../Roslyn/bincore/' + name
        + '.dll</HintPath></Reference>' for name in ('Microsoft.CodeAnalysis', 'Microsoft.CodeAnalysis.CSharp')) if roslyn else ''
    return ('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework>'
        '<UseAppHost>false</UseAppHost><EnableDefaultCompileItems>false</EnableDefaultCompileItems><NuGetAudit>false</NuGetAudit>'
        '</PropertyGroup><ItemGroup><Compile Include="' + str(source) + '"/>' + references + '</ItemGroup></Project>')


def run(command, output, log):
    with (output / log).open('x') as stream:
        result = subprocess.run(list(map(str, command)), cwd=ROOT, env=oracle_environment(SDK), stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError('Pinned frontier command failed: ' + str(output / log))


def build_tool(output):
    output.mkdir()
    (output / 'Frontier.csproj').write_text(project(TOOL_SOURCE, True))
    (output / 'NuGet.Config').write_text('<configuration><packageSources><clear/></packageSources></configuration>')
    run([SDK, 'restore', output / 'Frontier.csproj', '--configfile', output / 'NuGet.Config'], output, 'restore.log')
    run([SDK, 'build', output / 'Frontier.csproj', '--no-restore', '-c', 'Release', '-p:UseSharedCompilation=false', '--disable-build-servers'], output, 'build.log')
    return output / 'bin/Release/net8.0/Frontier.dll'


def emit(tool, selections, output):
    request = {'Selections': selections, 'Output': str(output / 'Frontier.cs'), 'Inventory': str(output / 'frontier-inventory.json')}
    (output / 'frontier-request.json').write_text(json.dumps(request, indent=2) + '\n')
    run([SDK, tool, output / 'frontier-request.json'], output, 'frontier.log')
    inventory = json.loads((output / 'frontier-inventory.json').read_text())
    generated = (output / 'Frontier.cs').read_text()
    if hashlib.sha256(generated.encode()).hexdigest() != inventory['OutputSha256']:
        raise ValueError('Declaration frontier output identity changed')
    for category in ('Executable', 'Declarations'):
        for entry in inventory[category]:
            source = Path(entry['File']).read_bytes()
            if hashlib.sha256(source).hexdigest() != entry['SourceSha256']:
                raise ValueError('Declaration frontier source identity changed')
            text = source.decode().encode('utf-16-le')
            span = text[entry['Start'] * 2:entry['End'] * 2].decode('utf-16-le')
            if hashlib.sha256(span.encode()).hexdigest() != entry['Sha256']:
                raise ValueError('Declaration frontier span identity changed')
            if (category == 'Executable' or entry['Kind'] == 'native-abi') and span not in generated:
                raise ValueError('Unchanged member identity failed in declaration frontier: ' + entry['Name'])
    for fixture in inventory['ManagedPlatformFixtures']:
        body = fixture['ReplacementBody']
        if hashlib.sha256(body.encode()).hexdigest() != fixture['ReplacementBodySha256'] or body not in generated:
            raise ValueError('Managed platform fixture replacement identity changed')
        if any(entry == fixture['Original'] for entry in inventory['Executable']):
            raise ValueError('Managed platform fixture must not claim unchanged executable identity')
    return generated, inventory
