#!/usr/bin/env python3
"""Resolve the pinned private .NET SDK for the supported Linux host architectures."""

import platform
from pathlib import Path


VERSION = "8.0.425"
TOOLS = ".audit/native-oracle/tools"
SDK_DIRECTORIES = {
    "linux-x64": f"dotnet-{VERSION}-linux-x64",
    "linux-arm64": f"dotnet-{VERSION}",
}
MACHINE_RIDS = {
    "x86_64": "linux-x64",
    "aarch64": "linux-arm64",
}


def host_rid(system=None, machine=None):
    system = platform.system() if system is None else system
    machine = platform.machine() if machine is None else machine
    if system != "Linux":
        raise RuntimeError(f"Unsupported host OS for the private .NET SDK: {system!r}; supported: Linux")
    if machine not in MACHINE_RIDS:
        raise RuntimeError(
            f"Unsupported host architecture for the private .NET SDK: {machine!r}; supported: x86_64, aarch64")
    return MACHINE_RIDS[machine]


def sdk_path(root, system=None, machine=None):
    return Path(root) / TOOLS / SDK_DIRECTORIES[host_rid(system, machine)] / "dotnet"
