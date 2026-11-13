#!/usr/bin/env python3
"""Inspect our diagnostic VPK against its private staging and build outputs."""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import zipfile
from sfo import parse_sfo
from native_room_revision import REPO_ROOT, source_state, validate_source_state, source_binding, file_identity, verify_file_identities
from native_room_replay import verify_replay_intent
from native_room_build import verify_build, cache_values
from native_room_automatic import verify_automatic_intent
from native_room_dash_probe import verify_dash_probe_intent
from stage_native_gameplay import METADATA


def verify(vpk, build, staging, expected_source_state=None):
    manifest = json.loads((staging / "assets/native-room/provenance.json").read_text())
    if expected_source_state is None:
        revision, changes = source_state(REPO_ROOT)
        if changes:
            raise ValueError("Current source/config is not clean: " + "; ".join(changes))
        if manifest["revision"] != revision or manifest["tracked_changes"]:
            raise ValueError("Staging is not from the exact clean delivery revision")
    before = validate_source_state(expected_source_state, REPO_ROOT)
    revision = before["base_head"]
    if manifest["revision"] != revision or manifest["tracked_changes"] != bool(before["changes"]):
        raise ValueError("Staging differs from the exact expected source state")
    if expected_source_state is not None and not manifest.get("binding"):
        raise ValueError("Expected-source-state verification requires an exact build binding, not a HEAD-dirty label")
    binding = verify_build(build.parents[1], staging, expected_source_state) if manifest.get("binding") else None
    replay = bool(manifest.get("guest_replay"))
    verify_replay_intent(manifest,replay,REPO_ROOT)
    automatic = bool(manifest.get("guest_automatic"))
    verify_automatic_intent(manifest,automatic,REPO_ROOT)
    probe = bool(manifest.get("guest_dash_probe"))
    verify_dash_probe_intent(manifest,probe,REPO_ROOT)
    if probe and (not binding or binding["capture_policy"] != "dash_trails"):
        raise ValueError("Dash probe verification requires its resident dash_trails build binding")
    if automatic and not binding:
        raise ValueError("Guest automatic verification requires its resident build binding")
    cache = build.parents[1] / "CMakeCache.txt"
    if automatic or cache.is_file():
        if (cache_values(cache).get("CELESTE_ROOM_GUEST_AUTOMATIC", "OFF") == "ON") != automatic:
            raise ValueError("Build and package guest automatic intent differ")
    if probe or cache.is_file():
        if (cache_values(cache).get("CELESTE_ROOM_DASH_PROBE", "OFF") == "ON") != probe:
            raise ValueError("Build and package Dash probe intent differ")
    gameplay = manifest.get("gameplay_production")
    if gameplay or cache.is_file():
        if (cache_values(cache).get("CELESTE_ROOM_GAMEPLAY_PRODUCTION", "OFF") == "ON") != bool(gameplay):
            raise ValueError("Build and package gameplay production intent differ")
    if gameplay and (gameplay != "automatic-transition" or not binding or binding["capture_policy"] != "bounded_gameplay_production"):
        raise ValueError("Gameplay package requires exact bounded production build binding")
    if replay or cache.is_file():
        expected = "CELESTE_ROOM_GUEST_REPLAY:BOOL="+("ON" if replay else "OFF")
        if expected not in cache.read_text().splitlines():
            raise ValueError("Build and package guest replay intent differ")
    elf = (build / "celeste_native_room").read_bytes()
    if elf[:7] != b"\x7fELF\x01\x01\x01" or struct.unpack_from("<H",elf,18)[0] != 40:
        raise ValueError("Expected ELF32 little-endian ARM executable")
    if replay and manifest["guest_replay"]["sha256"].encode() not in elf:
        raise ValueError("Guest ELF lacks its exact fixture identity pin")
    if automatic and manifest["guest_automatic_fixture"]["sha256"].encode() not in elf:
        raise ValueError("Guest automatic ELF lacks its exact fixture identity pin")
    if probe and manifest["guest_dash_probe_fixture"]["sha256"].encode() not in elf:
        raise ValueError("Dash probe ELF lacks its exact fixture identity pin")
    asset_names = {"global.mask", "hazards.txt"}
    if gameplay:
        asset_names = set(METADATA)
        pages = set(manifest["files"]) - asset_names
        if not pages or len(pages) > 64 or any(not name.startswith("page") or not name.endswith(".rgba") or
                not name[4:-5].isdigit() for name in pages):
            raise ValueError("Unexpected gameplay page inventory")
        asset_names.update(pages)
    if manifest.get("render_style", "debug") in {"textured_partial", "animated_player_partial"}:
        texture_count = 8 if manifest.get("spike_art") else 6
        asset_names.update({"visuals.txt", *(f"texture{i}.rgba" for i in range(texture_count))})
    if manifest.get("render_style") == "animated_player_partial":
        asset_names.update({"player.txt", *(f"player{i}.rgba" for i in range(manifest["player"]["pages"]))})
    if manifest.get("decal_art"):
        asset_names.update({"decals.txt", "decal0.rgba"})
    if set(manifest["files"]) != asset_names:
        raise ValueError("Unexpected manifest asset set for render style")
    expected = {"eboot.bin","sce_sys/param.sfo","assets/native-room/provenance.json", *("assets/native-room/"+name for name in asset_names)}
    watched = {str(path.resolve()): file_identity(path) for path in
               [vpk, build / "celeste_native_room", build / "eboot.bin", staging / "assets/native-room/provenance.json",
                *(staging / "assets/native-room" / name for name in asset_names), *([cache] if cache.is_file() else [])]}
    with zipfile.ZipFile(vpk) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != expected or len(archive.namelist()) != len(expected):
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
    verify_file_identities(watched)
    if binding:
        verify_file_identities(binding["inputs"])
        verify_file_identities(binding["artifacts"])
    after = validate_source_state(before, REPO_ROOT)
    return {"revision":revision,"vpk_bytes":vpk.stat().st_size,"vpk_sha256":hashlib.sha256(vpk.read_bytes()).hexdigest(),
            "elf_sha256":hashlib.sha256(elf).hexdigest(),"entries":entries,"sfo":sfo,"staging":manifest,
            "source_before":source_binding(before),"source_after":source_binding(after),"build_binding":binding,
            "exact_wip":expected_source_state is not None and bool(before["changes"])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vpk",type=Path,required=True)
    parser.add_argument("--build",type=Path,required=True)
    parser.add_argument("--staging",type=Path,required=True)
    parser.add_argument("--expected-source-state",type=Path,help="Explicit complete source-state manifest; default remains committed-clean only")
    args = parser.parse_args()
    print(json.dumps(verify(args.vpk,args.build,args.staging,
                            json.loads(args.expected_source_state.read_text()) if args.expected_source_state else None),indent=2))
