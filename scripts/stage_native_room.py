#!/usr/bin/env python3
"""Verify private prepared assets and stage the bounded native diagnostic package."""

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from binary_map import Reader
from prepare_static_tilemap import INPUT_SHA, MAP_SHA, MEMBER, read_mask, build_mask, map_driver
from prepare_room_hazards import room_hazards
from native_room_revision import REPO_ROOT, source_state
from native_room_replay import replay_intent


def checksum(data):
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value


def hazard_text(hazards):
    rows = []
    for hazard in hazards:
        direction = hazard["direction"]
        values = [hazard[key] for key in ("x", "y", "size")]
        if direction not in {"up", "left"} or any(type(value) is not int for value in values):
            raise ValueError("Unsupported spike data")
        x, y, size = values
        if not (-1_000_000 <= x <= 1_000_000 and -1_000_000 <= y <= 1_000_000 and 0 < size <= 1_000_000):
            raise ValueError("Spike exceeds diagnostic bounds")
        rows.append(f"{direction} {x} {y} {size}\n")
    if len(rows) > 64:
        raise ValueError("Too many spikes")
    return f"CSH1\n{INPUT_SHA}\n{MAP_SHA}\n{len(rows)}\n" + "".join(rows)


def verified_bytes(path, expected, limit=4_000_512):
    if path.stat().st_size > limit:
        raise ValueError(f"Prepared asset exceeds bound: {path}")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"Prepared provenance mismatch: {path}")
    return data


def stage(output, mask_dir, hazard_dir, archive_path, visual_dir=None, player_dir=None, guest_replay=False):
    output = output.resolve()
    if not output.is_relative_to(REPO_ROOT / ".audit"):
        raise ValueError("Private diagnostic assets must remain under .audit")
    mask_provenance = json.loads((mask_dir / "provenance.json").read_text())
    hazard_provenance = json.loads((hazard_dir / "provenance.json").read_text())
    for provenance in (mask_provenance, hazard_provenance):
        if (provenance["input_sha256"], provenance["map_sha256"], provenance["selected_room"]) != (INPUT_SHA, MAP_SHA, "1"):
            raise ValueError("Wrong prepared input provenance")
    mask = verified_bytes(mask_dir / "global.mask", mask_provenance["files"]["global.mask"])
    hazards_raw = verified_bytes(hazard_dir / "hazards.json", hazard_provenance["files"]["hazards.json"],8192)
    if hashlib.sha256(mask).hexdigest() != hazard_provenance["global_mask_sha256"]:
        raise ValueError("Hazard provenance uses a different global mask")
    with zipfile.ZipFile(archive_path) as archive:
        if archive.getinfo(MEMBER).file_size > 16*1024*1024 or archive.getinfo("Celeste.exe").file_size > 32*1024*1024:
            raise ValueError("Private archive input exceeds preparation bounds")
        map_bytes, exe = archive.read(MEMBER), archive.read("Celeste.exe")
    if hashlib.sha256(map_bytes).hexdigest() != MAP_SHA or hashlib.sha256(exe).hexdigest() != INPUT_SHA:
        raise ValueError("Private archive input hashes changed")
    package, root = Reader(map_bytes).map()
    facts, hazards = room_hazards(root)
    if package != "1-ForsakenCity" or read_mask(mask.decode("ascii")) != build_mask(map_driver(root)):
        raise ValueError("Prepared mask differs from accepted full merged construction")
    if json.loads(hazards_raw) != hazards or facts["spawns"][0] != [19, 144]:
        raise ValueError("Prepared hazards or selected spawn changed")
    hazard_data = hazard_text(hazards).encode("ascii")
    revision, changes = source_state(REPO_ROOT)
    dirty = bool(changes)
    asset_dir = output / "assets/native-room"
    asset_dir.mkdir(parents=True, exist_ok=True)
    files = {"global.mask": mask, "hazards.txt": hazard_data}
    visuals = None
    if visual_dir is not None:
        visuals = json.loads((visual_dir / "provenance.json").read_text())
        if (visuals["input_sha256"], visuals["map_sha256"], visuals["selected_room"]) != (INPUT_SHA, MAP_SHA, "1"):
            raise ValueError("Wrong visual input provenance")
        spike_art = visuals.get("spike_art") is not None or visuals.get("spike_textures") is not None
        expected_files = {"visuals.txt", *(f"texture{i}.rgba" for i in range(8 if spike_art else 6))}
        expected_bytes = 166912 if spike_art else 164864
        if set(visuals["files"]) != expected_files or visuals["submitted_rgba_bytes"] != expected_bytes:
            raise ValueError("Unexpected visual asset set or submitted byte count")
        for name, digest in visuals["files"].items():
            files[name] = verified_bytes(visual_dir / name,digest,65_536)
        if spike_art:
            oracle = visuals["spike_oracle"]
            verified_bytes(Path(oracle["path"]) / "result.json",oracle["result_sha256"],16*1024*1024)
            verified_bytes(Path(oracle["path"]) / "source-manifest.json",oracle["source_manifest_sha256"],16*1024*1024)
            if visuals["additional_spike_rgba_bytes"] != 2048 or len(visuals["spike_textures"]) != 2:
                raise ValueError("Unexpected source spike texture closure")
        else:
            bake = Path(visuals["source_bake"]["path"])
            verified_bytes(bake / "result.json",visuals["source_bake"]["result_sha256"])
            verified_bytes(bake / "source-manifest.json",visuals["source_bake"]["source_manifest_sha256"])
    player = None
    if player_dir is not None:
        if visuals is None:
            raise ValueError("Animated player requires unchanged source-baked room visuals")
        player = json.loads((player_dir / "provenance.json").read_text())
        if (player["input_sha256"], player["map_sha256"], player["mode"], player["bank"], player["hair_count"]) != (INPUT_SHA, MAP_SHA, "Madeline", "player", 4):
            raise ValueError("Wrong bounded player provenance")
        pages = player["pages"]
        if not 1 <= pages <= 10 or set(player["files"]) != {"player.txt", *(f"player{i}.rgba" for i in range(pages))}:
            raise ValueError("Unexpected bounded player asset set")
        if player["submitted_player_rgba_bytes"] != pages * 128 * 64 * 4 or 164864 + player["submitted_player_rgba_bytes"] > 512 * 1024:
            raise ValueError("Required player closure exceeds upload budget")
        for name, digest in player["files"].items():
            files[name] = verified_bytes(player_dir / name, digest, 65_536 if name == "player.txt" else 32_768)
        source = Path(player["source_oracle"])
        verified_bytes(source / "source-manifest.json", player["source_manifest_sha256"])
        verified_bytes(source / "bank.json", player["bank_sha256"])
    manifest = {"revision": revision, "tracked_changes": dirty, "input_sha256": INPUT_SHA,
                "map_sha256": MAP_SHA, "selected_room": "1", "spawn": [19, 144],
                "render_style": "animated_player_partial" if player else "textured_partial" if visuals else "debug",
                "spike_art": bool(visuals and visuals.get("spike_textures") is not None), "visuals": visuals, "player": player,
                "mask_provenance_sha256": hashlib.sha256((mask_dir / "provenance.json").read_bytes()).hexdigest(),
                "hazard_provenance_sha256": hashlib.sha256((hazard_dir / "provenance.json").read_bytes()).hexdigest(),
                "files": {name: {"sha256": hashlib.sha256(data).hexdigest(), "fnv1a32": checksum(data), "bytes": len(data)}
                          for name, data in files.items()},
                 "integrity_claim": "SHA256 verified at preparation/staging; executable-pinned FNV-1a runtime corruption check, not authentication"}
    manifest["guest_replay"] = replay_intent() if guest_replay else None
    for name, data in files.items():
        (asset_dir / name).write_bytes(data)
    (asset_dir / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "asset_pins.hpp").write_text(
        '#pragma once\n#include <cstdint>\nnamespace celeste::diagnostic {\n'
        f'constexpr bool guest_replay_enabled = {str(guest_replay).lower()};\n'
        + (f'constexpr const char* guest_replay_sha256 = "{manifest["guest_replay"]["sha256"]}";\n' if guest_replay else '') +
        f'constexpr std::uint32_t mask_checksum = {checksum(mask)}u;\n'
        f'constexpr std::uint32_t spike_checksum = {checksum(hazard_data)}u;\n'
        + (f'constexpr std::uint32_t visual_checksum = {checksum(files["visuals.txt"])}u;\n' if visuals else '') +
        (f'constexpr std::uint32_t player_checksum = {checksum(files["player.txt"])}u;\nconstexpr const char* player_bank_sha256 = "{player["bank_sha256"]}";\n' if player else '') +
        f'constexpr const char* revision = "{revision}{"-dirty" if dirty else ""}";\n' + '}\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".audit/native-room-vita/staging"))
    parser.add_argument("--mask-dir", type=Path, default=Path(".audit/native-static-tilemap/prepared"))
    parser.add_argument("--hazard-dir", type=Path, default=Path(".audit/native-room-hazards/prepared"))
    parser.add_argument("--archive", type=Path, default=Path("game/celeste-linux.zip"))
    parser.add_argument("--visual-dir", type=Path, help="Explicit source-closed private textured-room assets; absent keeps debug mode")
    parser.add_argument("--player-dir", type=Path, help="Explicit source-closed animated player and simulated hair; requires visual-dir")
    parser.add_argument("--guest-replay", action="store_true", help="Pin the bounded diagnostic guest-controls fixture; manual remains default")
    args = parser.parse_args()
    manifest = stage(args.output, args.mask_dir, args.hazard_dir, args.archive, args.visual_dir, args.player_dir, args.guest_replay)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
