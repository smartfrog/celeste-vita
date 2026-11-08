#!/usr/bin/env python3
"""Stage the complete source-exported bounded player/hair closure privately."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import zipfile

from check_native_oracle import ROOT, verify_extraction
from native_player_assets import pack_player_crops
from native_room_textures import atlas_metadata, decode_crops
from prepare_room_visuals import MEMBERS
from prepare_static_tilemap import INPUT_SHA, MAP_SHA
from stage_native_room import checksum


def prepare(oracle, archive_path, output):
    if not output.resolve().is_relative_to(ROOT / ".audit") or output.exists():
        raise ValueError("Player presentation output must be fresh and private")
    identity = verify_extraction(oracle)
    if json.loads((oracle / "gate-result.json").read_text())["status"] != "unchanged-body-and-hair-source-executed":
        raise ValueError("Player source executable gate is missing")
    bank = json.loads((oracle / "bank.json").read_text())
    if (bank["mode"], bank["bank"], bank["hairCount"], bank["origin"]) != ("Madeline", "player", 4, [16, 32]):
        raise ValueError("Source default-profile identity changed")
    if len(bank["animations"]) != 24 or len(bank["bangs"]) != 3:
        raise ValueError("Unexpected bounded source closure")
    members = {}
    with zipfile.ZipFile(archive_path) as archive:
        if archive_path.stat().st_size != 883881658:
            raise ValueError("Private Linux archive length changed")
        for name in ("Celeste.exe", "FNA.dll", "mscorlib.dll", "Content/Graphics/Sprites.xml",
                     "Content/Graphics/Atlases/Gameplay.meta", "Content/Graphics/Atlases/Gameplay0.data"):
            data = archive.read(name)
            if hashlib.sha256(data).hexdigest() != MEMBERS[name]:
                raise ValueError("Pinned private member changed: " + name)
            members[name] = data
    metadata = atlas_metadata(members["Content/Graphics/Atlases/Gameplay.meta"])
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
    indices = {name: i for i, name in enumerate(names)}
    frames = {frame["name"]: frame for frame in bank["frames"]}
    text = f"CSPP1\n{INPUT_SHA}\n{MAP_SHA}\n{len(pages)}\n"
    text += "".join(f"{checksum(page):08x}\n" for page in pages)
    text += f"{len(names)}\n"
    for name in names:
        frame = frames[name]
        fields = [name, *layout[name], *frame["rectangle"][2:], *map(int, frame["trim"]), *frame["size"],
                  *map(int, frame["hairOffset"]), frame["hairFrame"], int(frame["hasHair"])]
        text += " ".join(map(str, fields)) + "\n"
    text += f"{len(bank['animations'])}\n"
    for a in bank["animations"]:
        delay = struct.unpack("<I", struct.pack("<f", a["delay"]))[0]
        text += f"{a['id']} {delay:08x} {a['next'] or '-'} {len(a['frames'])} "
        text += " ".join(str(indices[name]) for name in a["frames"]) + "\n"
    text += " ".join(str(indices[name]) for name in [*bank["bangs"], bank["hair"]]) + "\n"
    output.mkdir(parents=True)
    for i, page in enumerate(pages):
        (output / f"player{i}.rgba").write_bytes(page)
    (output / "player.txt").write_text(text)
    inputs = {name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in members.items()}
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir()}
    result = {"input_sha256": INPUT_SHA, "map_sha256": MAP_SHA, "mode": "Madeline", "bank": "player", "hair_count": 4,
              "source_oracle": str(oracle), "source_identity": identity, "bank_sha256": hashlib.sha256((oracle / "bank.json").read_bytes()).hexdigest(),
              "source_manifest_sha256": hashlib.sha256((oracle / "source-manifest.json").read_bytes()).hexdigest(),
              "inputs": inputs, "frames": len(names), "pages": len(pages), "files": files,
              "page_checksums": [checksum(page) for page in pages], "metadata_checksum": checksum(text.encode()),
              "submitted_player_rgba_bytes": sum(map(len, pages)), "temporary_upload_bytes": 128 * 64 * 4,
              "alpha_counts": dict(Counter(alpha for rgba in decoded.values() for alpha in rgba[3::4])),
              "crop_sha256": {name: hashlib.sha256(rgba).hexdigest() for name, rgba in decoded.items()},
              "layout": layout,
              "archive": {"path": str(archive_path), "bytes": 883881658,
                          "sha256": "a613430411dbef3c0c45a0474f90f4845122964c7d177d69e88965bcb84741bf",
                          "hash_source": "Accepted archive identity; every used member independently re-read and hashed here"}}
    (output / "provenance.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--archive", type=Path, default=ROOT / "game/celeste-linux.zip")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.oracle, args.archive, args.output)
    print(json.dumps({key: result[key] for key in ("frames", "pages", "submitted_player_rgba_bytes", "alpha_counts")}, indent=2))
