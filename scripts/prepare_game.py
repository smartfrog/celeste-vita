#!/usr/bin/env python3
"""Prepare the bounded Vita diagnostic from your own unmodified PC 1.4.0.0 files."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

from binary_map import Reader
from bootstrap_game_tools import ensure_tools
from extract_native_oracle import SOURCE_HASHES
from game_input import normalize_game
from native_room_revision import REPO_ROOT, source_identity, validate_source_state
from prepare_decals_oracle import DISCOVERY_PINS
from prepare_room_visual_oracle import VISUAL_SOURCES
from prepare_room_visuals import MEMBERS
from prepare_static_tilemap import MEMBER
from read_player_presentation_sources import extract

GAME_PINS = MEMBERS | {
    "Celeste.Content.dll": "0b8d6195992c8970e8602bf48a7bf89104b83a98e34a07dc0c18d01581711d15",
    "System.Core.dll": "bb65859a1ec3a6406cd61d3fce348380fac4c50c2ebbfce5ec92f171ff4432c7",
    "System.dll": "f7bec4be4fb5b4cade309522306441920b409eedd4741c3963355d7a08604b68",
    "System.Xml.dll": "0c251c5ea2405a58387c58241813d07e3a199ce704d6bade55a0d340093850ff",
}


def preparation_output(output, root=REPO_ROOT):
    output = output.resolve()
    private = root.resolve() / ".audit"
    if not output.is_relative_to(private) or output == private:
        raise ValueError("Output must remain in a private subdirectory beneath this checkout's .audit")
    if output.exists():
        raise FileExistsError("Use a fresh output directory; existing preparations are preserved: " + str(output))
    return output


def raw_room_text(root):
    levels = next(group["children"] for group in root["children"] if group["name"] == "levels")
    rooms = [room for room in levels if room["attributes"]["name"] == "lvl_1"]
    if len(rooms) != 1:
        raise ValueError("Expected exactly one raw first room")
    return json.dumps(rooms[0], indent=2) + "\n"


def prepare(game, output, offline=False, root=REPO_ROOT):
    output = preparation_output(output, root)
    if game.is_dir() and output.is_relative_to(game.resolve()):
        raise ValueError("Preparation must not write inside the original game directory")
    archive = normalize_game(game, output, GAME_PINS)
    report = {"schema": 1, "status": "preparing", "archive": str(archive), "commands": [],
              "scope": "Bounded first-room diagnostic, not the full game; generated assets are private"}
    report_path = output / "preparation.json"

    def save():
        report_path.write_text(json.dumps(report, indent=2) + "\n")

    def run(label, script, *arguments):
        command = [sys.executable, "-B", str(root / "scripts" / script), *map(str, arguments)]
        print(label, flush=True)
        log = output / (label + ".log")
        with log.open("x") as stream:
            result = subprocess.run(command, cwd=root, env=environment, stdout=stream, stderr=subprocess.STDOUT)
        report["commands"].append({"label": label, "argv": command, "exit_code": result.returncode, "log": str(log)})
        save()
        if result.returncode:
            raise RuntimeError(f"{label} failed ({result.returncode}); see {log}")

    save()
    try:
        temporary = output / "tmp"
        temporary.mkdir()
        environment = os.environ | {"TMPDIR": str(temporary), "PYTHONDONTWRITEBYTECODE": "1"}
        print("Checking pinned local preparation tools", flush=True)
        ensure_tools(offline)
        before = source_identity(root)
        sources, visual_sources = output / "player-sources", output / "visual-sources"
        print("Extracting pinned presentation types locally", flush=True)
        extract(output / "inputs", archive, sources)
        pins = {**VISUAL_SOURCES, **DISCOVERY_PINS,
                **{name: SOURCE_HASHES[name] for name in ("Celeste.LevelData.cs", "Celeste.MapData.cs", "Celeste.LevelLoader.cs")}}
        print("Extracting pinned loader, autotiler and decal types locally", flush=True)
        extract(output / "inputs", archive, visual_sources, pins)
        with zipfile.ZipFile(archive) as package:
            for name in MEMBERS:
                if name.endswith(".xml"):
                    (visual_sources / Path(name).name).write_bytes(package.read(name))
            _, raw = Reader(package.read(MEMBER)).map()
        raw_room = output / "raw-room.json"
        raw_room.write_text(raw_room_text(raw))
        mask, hazards = output / "mask", output / "hazards"
        visual_oracle, base_visuals = output / "visual-oracle", output / "base-visuals"
        player_oracle, player = output / "player-oracle", output / "player"
        spike_oracle, visuals = output / "spike-oracle", output / "visuals"
        decal_oracle, decals = output / "decal-oracle", output / "decals"
        run("mask", "prepare_static_tilemap.py", "--archive", archive, "--output", mask)
        run("hazards", "prepare_room_hazards.py", "--archive", archive, "--mask", mask / "global.mask", "--output", hazards)
        run("visual-oracle", "prepare_room_visual_oracle.py", "--source", visual_sources, "--inputs", output / "inputs",
            "--prepared", mask, "--output", visual_oracle)
        run("base-visuals", "prepare_room_visuals.py", "--archive", archive, "--oracle", visual_oracle, "--output", base_visuals)
        run("player-oracle", "prepare_player_presentation_oracle.py", "--source", sources, "--output", player_oracle)
        run("player", "prepare_player_presentation.py", "--archive", archive, "--oracle", player_oracle, "--death", "--output", player)
        run("spike-oracle", "prepare_spike_art_oracle.py", "--source", sources, "--hazards", hazards / "hazards.json", "--output", spike_oracle)
        run("visuals", "prepare_spike_art.py", "--archive", archive, "--oracle", spike_oracle, "--visuals", base_visuals, "--output", visuals)
        run("decal-oracle", "prepare_decals_oracle.py", "--archive", archive, "--discovery", visual_sources,
            "--pins", sources, "--raw-room", raw_room, "--output", decal_oracle)
        run("decals", "prepare_decals.py", "--archive", archive, "--oracle", decal_oracle, "--raw-room", raw_room,
            "--visuals", visuals, "--hazards", hazards / "hazards.json", "--output", decals)
        validate_source_state(before, root)
        report.update(status="prepared", source=before, mask_dir=str(mask), hazard_dir=str(hazards),
                      visual_dir=str(visuals), player_dir=str(player), decal_dir=str(decals))
        save()
    except Exception as error:
        report.update(status="failed", error={"type": type(error).__name__, "message": str(error)})
        save()
        raise
    print("PREPARATION_JSON " + str(report_path), flush=True)
    return report_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, required=True, help="Owned PC 1.4.0.0 game directory or ZIP; never modified")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / ".audit/prepared-game", help="Fresh private output directory")
    parser.add_argument("--offline", action="store_true", help="Never download missing .NET/ILSpy tools")
    args = parser.parse_args()
    prepare(args.game.absolute(), args.output, args.offline)


if __name__ == "__main__":
    main()
