#!/usr/bin/env python3
"""Stage the complete source-exported bounded player/hair closure privately."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from check_native_oracle import ROOT, verify_extraction
from native_player_assets import pack_player_crops, extend_death_bank, player_metadata
from native_room_textures import atlas_metadata, decode_crops
from prepare_room_visuals import MEMBERS
from prepare_static_tilemap import INPUT_SHA, MAP_SHA
from stage_native_room import checksum
from game_input import archive_identity, read_members


def prepare(oracle, archive_path, output, death=False, source_root=None):
    if not output.resolve().is_relative_to(ROOT / ".audit") or output.exists():
        raise ValueError("Player presentation output must be fresh and private")
    identity = verify_extraction(oracle) if source_root is None else verify_extraction(oracle, source_root)
    if json.loads((oracle / "gate-result.json").read_text())["status"] != "unchanged-body-and-hair-source-executed":
        raise ValueError("Player source executable gate is missing")
    bank = json.loads((oracle / "bank.json").read_text())
    if (bank["mode"], bank["bank"], bank["hairCount"], bank["origin"]) != ("Madeline", "player", 4, [16, 32]):
        raise ValueError("Source default-profile identity changed")
    if len(bank["animations"]) != 24 or len(bank["bangs"]) != 3:
        raise ValueError("Unexpected bounded source closure")
    names = ("Celeste.exe", "FNA.dll", "mscorlib.dll", "Content/Graphics/Sprites.xml",
             "Content/Graphics/Atlases/Gameplay.meta", "Content/Graphics/Atlases/Gameplay0.data")
    members = read_members(archive_path, {name: MEMBERS[name] for name in names})
    metadata = atlas_metadata(members["Content/Graphics/Atlases/Gameplay.meta"])
    if death:
        bank = extend_death_bank(bank, members["Content/Graphics/Sprites.xml"], metadata)
    crops = {}
    for frame in bank["frames"]:
        name = frame["name"]
        sheet, x, y, w, h, tx, ty, fw, fh = metadata[name]
        if sheet != "Gameplay0" or frame["rectangle"] != [x, y, w, h] or frame["trim"] != [-tx, -ty] or frame["size"] != [fw, fh]:
            raise ValueError("Source-exported texture metadata differs from independent atlas input")
        crops[name] = x, y, w, h
    decoded = decode_crops(members["Content/Graphics/Atlases/Gameplay0.data"], crops)
    pages, layout = pack_player_crops({name: (crops[name][2], crops[name][3], rgba) for name, rgba in decoded.items()})
    names = sorted(crops)
    text = player_metadata(bank, layout, [checksum(page) for page in pages])
    output.mkdir(parents=True)
    for i, page in enumerate(pages):
        (output / f"player{i}.rgba").write_bytes(page)
    (output / "player.txt").write_text(text)
    (output / "bank.json").write_text(json.dumps(bank, indent=2) + "\n")
    inputs = {name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in members.items()}
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir()}
    result = {"input_sha256": INPUT_SHA, "map_sha256": MAP_SHA, "mode": "Madeline", "bank": "player", "hair_count": 4,
              "source_oracle": str(oracle), "source_identity": identity, "bank_sha256": hashlib.sha256((oracle / "bank.json").read_bytes()).hexdigest(),
               "source_manifest_sha256": hashlib.sha256((oracle / "source-manifest.json").read_bytes()).hexdigest(),
              "death_animation_extension": death, "animations": len(bank["animations"]),
              "source_root": str(source_root or ROOT),
               "inputs": inputs, "frames": len(names), "pages": len(pages), "files": files,
               "payload_files": sorted({"player.txt", *(f"player{i}.rgba" for i in range(len(pages)))}),
               "evidence_files": ["bank.json"],
              "page_checksums": [checksum(page) for page in pages], "metadata_checksum": checksum(text.encode()),
              "submitted_player_rgba_bytes": sum(map(len, pages)), "temporary_upload_bytes": 128 * 64 * 4,
              "alpha_counts": dict(Counter(alpha for rgba in decoded.values() for alpha in rgba[3::4])),
              "crop_sha256": {name: hashlib.sha256(rgba).hexdigest() for name, rgba in decoded.items()},
              "layout": layout,
               "archive": archive_identity(archive_path)}
    (output / "provenance.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--archive", type=Path, default=ROOT / "game/celeste-linux.zip")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--death", action="store_true", help="Extend only the original three PlayerDeadBody animations")
    parser.add_argument("--source-root", type=Path, help="Explicit immutable oracle source root when different from this native worktree")
    args = parser.parse_args()
    result = prepare(args.oracle, args.archive, args.output, args.death, args.source_root)
    print(json.dumps({key: result[key] for key in ("frames", "pages", "submitted_player_rgba_bytes", "alpha_counts")}, indent=2))
