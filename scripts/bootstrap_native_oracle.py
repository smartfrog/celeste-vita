#!/usr/bin/env python3
"""Install the pinned, hash-verified private reference SDK without a global install."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import urllib.request

from native_oracle_sdk import SDK_DIRECTORIES, VERSION, host_rid


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / ".audit/native-oracle/tools"
METADATA = "https://builds.dotnet.microsoft.com/dotnet/release-metadata/8.0/releases.json"
METADATA_BYTES = 2 * 1024 * 1024
PINS = {
    "linux-arm64": {
        "bytes": 212188361,
        "sha512": "84a4d017d74d7aa842e981679d1b044e6be1f35b9b2b214021e30bc40871d016d29611cca373d8502ad5c890e3ad360ee698f9cf2d7a4d5a9fba102d88ba310f",
    },
    "linux-x64": {
        "bytes": 216833108,
        "sha512": "934b8060a7190e5909ad1fd0785db542f487b3bbf6cdd14826b02095fdd0d0394298b1634085eff302928fccc33f7c1a7253e9b87df555fc36fce819bcd2e798",
    },
}
CHUNK_BYTES = 1024 * 1024
LEGACY_RID = "linux-arm64"


def state_directory(rid):
    return TOOLS if rid == LEGACY_RID else TOOLS / f"bootstrap-{rid}"


def read_metadata(response):
    metadata = bytearray()
    while chunk := response.read(min(CHUNK_BYTES, METADATA_BYTES - len(metadata) + 1)):
        if len(chunk) > METADATA_BYTES - len(metadata):
            raise RuntimeError(f"SDK metadata exceeds byte limit {METADATA_BYTES}")
        metadata.extend(chunk)
    return bytes(metadata)


def select_artifact(metadata, rid, pin):
    try:
        sdk = next(sdk for release in json.loads(metadata)["releases"] for sdk in release["sdks"]
                   if sdk["version"] == VERSION)
        artifact = next(file for file in sdk["files"] if file["rid"] == rid)
    except (KeyError, TypeError, StopIteration, json.JSONDecodeError) as error:
        raise RuntimeError(f"Invalid release metadata or pinned SDK artifact missing for {rid}") from error
    if sdk.get("runtime-version") != "8.0.31":
        raise RuntimeError("Unexpected SDK/runtime pairing")
    if artifact.get("hash") != pin["sha512"]:
        raise RuntimeError("Published metadata SDK SHA512 differs from the pinned artifact")
    return sdk, artifact


def verify_archive(archive, pin):
    size = archive.stat().st_size
    if size != pin["bytes"]:
        raise RuntimeError(f"SDK archive size mismatch: expected {pin['bytes']}, got {size}: {archive}")
    with archive.open("rb") as package:
        digest = hashlib.file_digest(package, "sha512").hexdigest()
    if digest != pin["sha512"]:
        raise RuntimeError(f"SDK SHA512 mismatch: {archive}")
    return digest


def download_archive(artifact, archive, pin):
    expected_bytes = pin["bytes"]
    download = None
    try:
        with tempfile.NamedTemporaryFile(dir=TOOLS, prefix=archive.name + ".", suffix=".part", delete=False) as output:
            download = Path(output.name)
            received = 0
            with urllib.request.urlopen(artifact["url"], timeout=120) as response:
                while chunk := response.read(min(CHUNK_BYTES, expected_bytes - received + 1)):
                    if len(chunk) > expected_bytes - received:
                        raise RuntimeError(f"SDK archive size exceeds pinned {expected_bytes} bytes")
                    output.write(chunk)
                    received += len(chunk)
            if received != expected_bytes:
                raise RuntimeError(f"SDK archive size mismatch: expected {expected_bytes}, got {received} (premature EOF)")
        digest = verify_archive(download, pin)
        download.replace(archive)
        return digest
    finally:
        if download is not None:
            download.unlink(missing_ok=True)


def main():
    rid = host_rid()
    pin = PINS.get(rid)
    if pin is None:
        raise RuntimeError(f"No pinned .NET SDK artifact for host RID {rid}")
    state = state_directory(rid)
    TOOLS.mkdir(parents=True, exist_ok=True)
    state.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(METADATA, timeout=120) as response:
        metadata = read_metadata(response)
    sdk, artifact = select_artifact(metadata, rid, pin)
    (state / "releases.json").write_bytes(metadata)
    archive = TOOLS / f"dotnet-sdk-{VERSION}-{rid}.tar.gz"
    digest = verify_archive(archive, pin) if archive.exists() else download_archive(artifact, archive, pin)
    directory = TOOLS / SDK_DIRECTORIES[rid]
    directory.mkdir(exist_ok=True)
    with tarfile.open(archive) as package:
        package.extractall(directory, filter="data")
    environment = os.environ | {
        "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
        "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
        "DOTNET_CLI_HOME": str(state / "cli"),
        "NUGET_PACKAGES": str(state / "packages"),
    }
    version = subprocess.check_output([directory / "dotnet", "--version"], env=environment, text=True).strip()
    if version != VERSION:
        raise RuntimeError(f"Unexpected installed SDK: {version}")
    receipt = {"metadata": METADATA, "version": version, "runtime": sdk["runtime-version"], "rid": rid,
               "path": str(directory / "dotnet"), "artifact": artifact,
               "bytes": archive.stat().st_size, "sha512": digest}
    (state / "sdk-verification.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
