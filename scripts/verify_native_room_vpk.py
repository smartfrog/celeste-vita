#!/usr/bin/env python3
"""Inspect our diagnostic VPK against its private staging and build outputs."""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import zipfile
from sfo import parse_sfo
from native_room_revision import REPO_ROOT, source_state
from native_room_replay import verify_replay_intent


def verify(vpk, build, staging):
    manifest = json.loads((staging / "assets/native-room/provenance.json").read_text())
    revision, changes = source_state(REPO_ROOT)
    if changes:
        raise ValueError("Current source/config is not clean: " + "; ".join(changes))
    if manifest["revision"] != revision or manifest["tracked_changes"]:
        raise ValueError("Staging is not from the exact clean delivery revision")
    replay = bool(manifest.get("guest_replay"))
    verify_replay_intent(manifest,replay,REPO_ROOT)
    cache = build.parents[1] / "CMakeCache.txt"
    if replay or cache.is_file():
        expected = "CELESTE_ROOM_GUEST_REPLAY:BOOL="+("ON" if replay else "OFF")
        if expected not in cache.read_text().splitlines():
            raise ValueError("Build and package guest replay intent differ")
    elf = (build / "celeste_native_room").read_bytes()
    if elf[:7] != b"\x7fELF\x01\x01\x01" or struct.unpack_from("<H",elf,18)[0] != 40:
        raise ValueError("Expected ELF32 little-endian ARM executable")
    if replay and manifest["guest_replay"]["sha256"].encode() not in elf:
        raise ValueError("Guest ELF lacks its exact fixture identity pin")
    asset_names = {"global.mask", "hazards.txt"}
    if manifest.get("render_style", "debug") in {"textured_partial", "animated_player_partial"}:
        texture_count = 8 if manifest.get("spike_art") else 6
        asset_names.update({"visuals.txt", *(f"texture{i}.rgba" for i in range(texture_count))})
    if manifest.get("render_style") == "animated_player_partial":
        asset_names.update({"player.txt", *(f"player{i}.rgba" for i in range(manifest["player"]["pages"]))})
    if set(manifest["files"]) != asset_names:
        raise ValueError("Unexpected manifest asset set for render style")
    expected = {"eboot.bin","sce_sys/param.sfo","assets/native-room/provenance.json", *("assets/native-room/"+name for name in asset_names)}
    with zipfile.ZipFile(vpk) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != expected:
            raise ValueError("Unexpected or corrupt VPK entries")
        sfo = parse_sfo(archive.read("sce_sys/param.sfo"))
        if sfo.get("TITLE_ID") != "CELR00001" or sfo.get("TITLE") != "Celeste Native Room Diagnostic" or sfo.get("APP_VER") != "00.01":
            raise ValueError("Unexpected diagnostic SFO identity")
        eboot = archive.read("eboot.bin")
        if eboot[:4] != b"SCE\0" or eboot != (build / "eboot.bin").read_bytes():
            raise ValueError("Packaged SELF differs from this build")
        for name, metadata in manifest["files"].items():
            data = archive.read("assets/native-room/"+name)
            if data != (staging / "assets/native-room" / name).read_bytes() or hashlib.sha256(data).hexdigest() != metadata["sha256"]:
                raise ValueError("Packaged asset hash mismatch")
        if archive.read("assets/native-room/provenance.json") != (staging / "assets/native-room/provenance.json").read_bytes():
            raise ValueError("Packaged provenance mismatch")
        entries = {name: {"bytes":archive.getinfo(name).file_size,"sha256":hashlib.sha256(archive.read(name)).hexdigest()} for name in sorted(expected)}
    return {"revision":revision,"vpk_bytes":vpk.stat().st_size,"vpk_sha256":hashlib.sha256(vpk.read_bytes()).hexdigest(),
            "elf_sha256":hashlib.sha256(elf).hexdigest(),"entries":entries,"sfo":sfo,"staging":manifest}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vpk",type=Path,required=True)
    parser.add_argument("--build",type=Path,required=True)
    parser.add_argument("--staging",type=Path,required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.vpk,args.build,args.staging),indent=2))
