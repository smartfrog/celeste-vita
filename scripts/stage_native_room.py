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
from native_room_revision import REPO_ROOT, validate_source_state, staging_binding, verify_file_identities
from native_room_replay import replay_intent
from native_room_automatic import automatic_intent
from native_room_dash_probe import dash_probe_intent, verify_dash_probe_intent


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


def verified_player_files(directory, provenance, read_verified=verified_bytes):
    if not {"pages", "files", "submitted_player_rgba_bytes", "source_oracle", "source_manifest_sha256", "bank_sha256", "layout"} <= provenance.keys():
        raise ValueError("Player payload and original-source bank provenance pins are required")
    pages = provenance["pages"]
    if type(pages) is not int or not 1 <= pages <= 10:
        raise ValueError("Unexpected bounded player asset set")
    payload = {"player.txt", *(f"player{i}.rgba" for i in range(pages))}
    declared = set(provenance["files"])
    evidence = {"bank.json"} if "bank.json" in declared else set()
    if declared != payload | evidence:
        raise ValueError("Unexpected bounded player asset set")
    if {path.name for path in directory.iterdir()} != declared | {"provenance.json"}:
        raise ValueError("Player payload/evidence inventory differs from its complete pins")
    if ("payload_files" in provenance or "evidence_files" in provenance) and (
            set(provenance.get("payload_files", [])) != payload or set(provenance.get("evidence_files", [])) != evidence):
        raise ValueError("Player payload/evidence roles changed")
    if (provenance.get("death_animation_extension") or provenance.get("sweat_animation_extension")) and not evidence:
        raise ValueError("Extended animation source bank evidence pin is required")
    if provenance["submitted_player_rgba_bytes"] != pages * 32768 or 164864 + pages * 32768 > 512 * 1024:
        raise ValueError("Required player closure exceeds upload budget")
    result = {name: read_verified(directory / name, provenance["files"][name], 65536 if name == "player.txt" else 32768)
              for name in sorted(payload)}
    if any(len(result[f"player{i}.rgba"]) != 32768 for i in range(pages)):
        raise ValueError("Player page size must be exactly 128x64 RGBA")
    source = Path(provenance["source_oracle"])
    source_manifest = json.loads(read_verified(source / "source-manifest.json", provenance["source_manifest_sha256"]))
    original_bank = json.loads(read_verified(source / "bank.json", provenance["bank_sha256"]))
    expected_bank = original_bank
    if evidence:
        if provenance.get("death_animation_extension") or provenance.get("sweat_animation_extension"):
            from native_player_assets import extend_death_bank, extend_sweat_bank
            from native_room_textures import atlas_metadata
            from prepare_room_visuals import MEMBERS
            original_source = Path(source_manifest["source_directory"])
            sprites = read_verified(original_source / "Sprites.xml", MEMBERS["Content/Graphics/Sprites.xml"])
            atlas = read_verified(original_source / "Gameplay.meta", MEMBERS["Content/Graphics/Atlases/Gameplay.meta"])
            metadata = atlas_metadata(atlas)
            if provenance.get("death_animation_extension"):
                expected_bank = extend_death_bank(expected_bank, sprites, metadata)
            if provenance.get("sweat_animation_extension"):
                expected_bank = extend_sweat_bank(expected_bank, sprites, metadata)
        bank = json.loads(read_verified(directory / "bank.json", provenance["files"]["bank.json"]))
        if bank != expected_bank:
            raise ValueError("Prepared bank evidence differs from the pinned original-source bank closure")
    from native_player_assets import player_metadata
    checksums = [checksum(result[f"player{i}.rgba"]) for i in range(pages)]
    if result["player.txt"] != player_metadata(expected_bank, provenance["layout"], checksums).encode():
        raise ValueError("Player metadata payload differs from its original-source bank and generated atlas layout")
    return result


def asset_pins_text(manifest):
    files = manifest["files"]
    replay = manifest.get("guest_replay")
    automatic = manifest.get("guest_automatic")
    probe = manifest.get("guest_dash_probe")
    player = manifest.get("player")
    label = manifest.get("binding", {}).get("revision_label", manifest["revision"] + ("-dirty" if manifest["tracked_changes"] else ""))
    return ('#pragma once\n#include <cstdint>\nnamespace celeste::diagnostic {\n'
            + ('#define CELESTE_STAGED_GAMEPLAY_PRODUCTION 1\n' if manifest.get("gameplay_production") else '')
            + f'constexpr bool guest_replay_enabled = {str(bool(replay)).lower()};\n'
            + f'constexpr const char* guest_automatic = {json.dumps(automatic) if automatic else "nullptr"};\n'
            + (f'constexpr const char* guest_automatic_sha256 = "{manifest["guest_automatic_fixture"]["sha256"]}";\n' if automatic else '')
            + (f'constexpr const char* guest_replay_sha256 = "{replay["sha256"]}";\n' if replay else '')
            + ('#define CELESTE_STAGED_DASH_PROBE 1\n'
               f'constexpr const char* guest_dash_probe = "{probe}";\n'
               f'constexpr const char* guest_dash_probe_sha256 = "{manifest["guest_dash_probe_fixture"]["sha256"]}";\n'
               f'constexpr unsigned guest_dash_probe_samples = {manifest["guest_dash_probe_fixture"]["samples"]};\n'
               f'constexpr unsigned guest_dash_probe_exit_frame = {manifest["guest_dash_probe_fixture"]["exit_frame"]};\n' if probe else '')
            + f'constexpr std::uint32_t mask_checksum = {files["global.mask"]["fnv1a32"]}u;\n'
            + f'constexpr std::uint32_t spike_checksum = {files["hazards.txt"]["fnv1a32"]}u;\n'
            + (f'constexpr std::uint32_t visual_checksum = {files["visuals.txt"]["fnv1a32"]}u;\n' if "visuals.txt" in files else '')
            + (f'constexpr std::uint32_t decal_checksum = {files["decals.txt"]["fnv1a32"]}u;\n' if "decals.txt" in files else '')
            + (f'constexpr std::uint32_t player_checksum = {files["player.txt"]["fnv1a32"]}u;\nconstexpr const char* player_bank_sha256 = "{player["bank_sha256"]}";\n' if player else '')
            + f'constexpr const char* revision = "{label}";\n' + '}\n')


def stage(output, mask_dir, hazard_dir, archive_path, visual_dir=None, player_dir=None, decal_dir=None, guest_replay=False,
          expected_source_state=None, guest_automatic=False, guest_dash_probe=False):
    if int(guest_replay) + int(guest_automatic) + int(guest_dash_probe) > 1:
        raise ValueError("Automatic and legacy guest replay modes are exclusive")
    if guest_automatic and player_dir is None:
        raise ValueError("Guest automatic requires animated Player assets")
    if guest_dash_probe and player_dir is None:
        raise ValueError("Dash probe requires animated Player assets")
    before = validate_source_state(expected_source_state, REPO_ROOT)
    inputs = {}

    def watch(path, data):
        inputs[str(path.resolve())] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        return data

    def read_verified(path, digest, limit=4_000_512):
        return watch(path, verified_bytes(path, digest, limit))

    def read_json(path):
        if path.stat().st_size > 16*1024*1024:
            raise ValueError("Prepared provenance exceeds bound: " + str(path))
        return json.loads(watch(path, path.read_bytes()))

    output = output.resolve()
    if not output.is_relative_to(REPO_ROOT / ".audit"):
        raise ValueError("Private diagnostic assets must remain under .audit")
    if output.exists():
        raise ValueError("Staging output must be fresh; existing artifacts are preserved")
    mask_provenance = read_json(mask_dir / "provenance.json")
    hazard_provenance = read_json(hazard_dir / "provenance.json")
    for provenance in (mask_provenance, hazard_provenance):
        if (provenance["input_sha256"], provenance["map_sha256"], provenance["selected_room"]) != (INPUT_SHA, MAP_SHA, "1"):
            raise ValueError("Wrong prepared input provenance")
    mask = read_verified(mask_dir / "global.mask", mask_provenance["files"]["global.mask"])
    hazards_raw = read_verified(hazard_dir / "hazards.json", hazard_provenance["files"]["hazards.json"],8192)
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
    revision, dirty = before["base_head"], bool(before["changes"])
    asset_dir = output / "assets/native-room"
    files = {"global.mask": mask, "hazards.txt": hazard_data}
    visuals = None
    if visual_dir is not None:
        visuals = read_json(visual_dir / "provenance.json")
        if (visuals["input_sha256"], visuals["map_sha256"], visuals["selected_room"]) != (INPUT_SHA, MAP_SHA, "1"):
            raise ValueError("Wrong visual input provenance")
        spike_art = visuals.get("spike_art") is not None or visuals.get("spike_textures") is not None
        expected_files = {"visuals.txt", *(f"texture{i}.rgba" for i in range(8 if spike_art else 6))}
        expected_bytes = 166912 if spike_art else 164864
        if set(visuals["files"]) != expected_files or visuals["submitted_rgba_bytes"] != expected_bytes:
            raise ValueError("Unexpected visual asset set or submitted byte count")
        for name, digest in visuals["files"].items():
            files[name] = read_verified(visual_dir / name,digest,65_536)
        if spike_art:
            oracle = visuals["spike_oracle"]
            read_verified(Path(oracle["path"]) / "result.json",oracle["result_sha256"],16*1024*1024)
            read_verified(Path(oracle["path"]) / "source-manifest.json",oracle["source_manifest_sha256"],16*1024*1024)
            if visuals["additional_spike_rgba_bytes"] != 2048 or len(visuals["spike_textures"]) != 2:
                raise ValueError("Unexpected source spike texture closure")
        else:
            bake = Path(visuals["source_bake"]["path"])
            read_verified(bake / "result.json",visuals["source_bake"]["result_sha256"])
            read_verified(bake / "source-manifest.json",visuals["source_bake"]["source_manifest_sha256"])
    player = None
    if player_dir is not None:
        if visuals is None:
            raise ValueError("Animated player requires unchanged source-baked room visuals")
        player = read_json(player_dir / "provenance.json")
        if (player["input_sha256"], player["map_sha256"], player["mode"], player["bank"], player["hair_count"]) != (INPUT_SHA, MAP_SHA, "Madeline", "player", 4):
            raise ValueError("Wrong bounded player provenance")
        files.update(verified_player_files(player_dir, player, read_verified))
    decals = None
    if decal_dir is not None:
        if visuals is None:
            raise ValueError("Static decals require unchanged source-baked room visuals")
        decals = read_json(decal_dir / "provenance.json")
        classification = decals.get("classification", {})
        if ((decals["input_sha256"], decals["map_sha256"], decals["selected_room"]) != (INPUT_SHA, MAP_SHA, "1") or
                (classification.get("static"), classification.get("bg"), classification.get("fg"),
                 classification.get("banner_omitted"), classification.get("unique_static_textures")) != (22, 20, 2, 7, 15)):
            raise ValueError("Wrong bounded static decal provenance")
        if set(decals["files"]) != {"decals.txt", "decal0.rgba"} or decals["submitted_decal_rgba_bytes"] != 32768 or \
                decals["max_temporary_cpu_upload_bytes"] > 32768:
            raise ValueError("Unexpected bounded static decal asset set/bytes")
        if Path(decals["visuals"]["path"]).resolve() != Path(visual_dir).resolve():
            raise ValueError("Static decals were prepared against different room visuals")
        for name, digest in decals["files"].items():
            files[name] = read_verified(decal_dir / name, digest, 32_768)
        oracle = decals["oracle"]
        read_verified(Path(oracle["path"]) / "result.json", oracle["result_sha256"], 16*1024*1024)
        read_verified(Path(oracle["path"]) / "source-manifest.json", oracle["source_manifest_sha256"], 16*1024*1024)
    manifest = {"revision": revision, "tracked_changes": dirty, "input_sha256": INPUT_SHA,
                "map_sha256": MAP_SHA, "selected_room": "1", "spawn": [19, 144],
                "render_style": "animated_player_partial" if player else "textured_partial" if visuals else "debug",
                "spike_art": bool(visuals and visuals.get("spike_textures") is not None),
                "decal_art": bool(decals is not None), "visuals": visuals, "player": player,
                "decals": decals,
                "mask_provenance_sha256": hashlib.sha256((mask_dir / "provenance.json").read_bytes()).hexdigest(),
                "hazard_provenance_sha256": hashlib.sha256((hazard_dir / "provenance.json").read_bytes()).hexdigest(),
                "files": {name: {"sha256": hashlib.sha256(data).hexdigest(), "fnv1a32": checksum(data), "bytes": len(data)}
                          for name, data in files.items()},
                 "integrity_claim": "SHA256 verified at preparation/staging; executable-pinned FNV-1a runtime corruption check, not authentication"}
    manifest["guest_replay"] = replay_intent() if guest_replay else None
    automatic = automatic_intent() if guest_automatic else None
    manifest["guest_automatic"] = automatic["id"] if automatic else None
    manifest["guest_automatic_fixture"] = automatic
    if guest_dash_probe:
        probe = dash_probe_intent()
        manifest.update(guest_dash_probe=probe["id"], guest_dash_probe_fixture=probe)
    verify_dash_probe_intent(manifest, guest_dash_probe, REPO_ROOT)
    manifest["prepared_inputs"] = inputs
    manifest["binding"] = staging_binding(manifest, before)
    verify_file_identities(inputs)
    validate_source_state(before, REPO_ROOT)
    asset_dir.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (asset_dir / name).write_bytes(data)
    (asset_dir / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "asset_pins.hpp").write_text(asset_pins_text(manifest))
    if player is not None:
        verified_player_files(player_dir, player, read_verified)
    verify_file_identities(inputs)
    validate_source_state(before, REPO_ROOT)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--output", type=Path, default=Path(".audit/native-room-vita/staging"))
    parser.add_argument("--mask-dir", type=Path, default=Path(".audit/native-static-tilemap/prepared"))
    parser.add_argument("--hazard-dir", type=Path, default=Path(".audit/native-room-hazards/prepared"))
    parser.add_argument("--archive", type=Path, default=Path("game/celeste-linux.zip"))
    parser.add_argument("--visual-dir", type=Path, help="Explicit source-closed private textured-room assets; absent keeps debug mode")
    parser.add_argument("--player-dir", type=Path, help="Explicit source-closed animated player and simulated hair; requires visual-dir")
    parser.add_argument("--decal-dir", type=Path, help="Explicit source-closed 22 static decals; requires visual-dir")
    guest = parser.add_mutually_exclusive_group()
    guest.add_argument("--guest-replay", action="store_true", help="Pin the legacy bounded manual diagnostic guest-controls fixture")
    guest.add_argument("--guest-automatic", action="store_true", help="Pin the input-only automatic first-room fixture; requires player-dir")
    guest.add_argument("--guest-dash-probe", action="store_true", help="Pin the separate 360-sample input-only Dash GPU probe; requires player-dir")
    parser.add_argument("--expected-source-state", type=Path, help="Explicit complete expected code-state manifest; absent requires committed-clean source")
    args = parser.parse_args()
    manifest = stage(args.output, args.mask_dir, args.hazard_dir, args.archive, args.visual_dir, args.player_dir,
                      decal_dir=args.decal_dir, guest_replay=args.guest_replay,
                      expected_source_state=json.loads(args.expected_source_state.read_text()) if args.expected_source_state else None,
                      guest_automatic=args.guest_automatic, guest_dash_probe=args.guest_dash_probe)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
