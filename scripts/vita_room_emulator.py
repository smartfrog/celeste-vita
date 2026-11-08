#!/usr/bin/env python3
"""Launch only this diagnostic in an isolated writable Vita3K filesystem."""

import argparse
import os
from pathlib import Path
import shutil

TITLE = "CELR00001"


def prepare(state, existing):
    state = state.resolve()
    if not state.is_relative_to(Path(".audit/native-room-vita").resolve()):
        raise ValueError("Emulator state must be beneath .audit/native-room-vita")
    shared = existing / "data/Vita3K/Vita3K"
    if (shared / "ux0/app" / TITLE).exists():
        raise ValueError("Diagnostic title ID already exists in shared state; refusing")
    fs = state / "data/Vita3K/Vita3K"
    for relative in ("data", "data/Vita3K", "data/Vita3K/Vita3K", "config", "config/Vita3K",
                     "config/Vita3K/config.yml", "cache", "tmp",
                     "data/Vita3K/Vita3K/ux0", "data/Vita3K/Vita3K/ur0"):
        if not (state / relative).resolve().is_relative_to(state):
            raise ValueError(f"Writable path escapes isolated state: {relative}")
    for relative in ("ur0/data", "ux0/data", "ux0/user", "ux0/user/00", "ux0/user/00/user.xml", "ux0/app"):
        if not (fs / relative).resolve().is_relative_to(state):
            raise ValueError(f"Writable path escapes isolated state: {relative}")
    fs.mkdir(parents=True, exist_ok=True)
    for name in ("vs0", "sa0"):
        target = fs / name
        source = shared / name
        if not source.is_dir():
            raise ValueError(f"Missing existing firmware/fonts: {source}")
        if not target.exists():
            target.symlink_to(source, target_is_directory=True)
        if target.resolve() != source.resolve():
            raise ValueError(f"Unexpected firmware symlink: {target}")
    for directory in ("ur0/data", "ux0/data", "ux0/user/00", "ux0/app"):
        (fs / directory).mkdir(parents=True, exist_ok=True)
    shader = fs / "ur0/data/libshacccg.suprx"
    source = shared / "ur0/data/libshacccg.suprx"
    if not source.is_file():
        raise ValueError("Missing existing shader compiler")
    if not shader.exists():
        shader.symlink_to(source)
    if shader.resolve() != source.resolve():
        raise ValueError("Unexpected shader compiler symlink")
    user = fs / "ux0/user/00/user.xml"
    if not user.exists():
        shutil.copyfile(shared / "ux0/user/00/user.xml", user)
    config = state / "config/Vita3K/config.yml"
    if not config.exists():
        text = (existing / "config/Vita3K/config.yml").read_text()
        lines = []
        replacements = {"pref-path": str(fs), "discord-rich-presence": "false", "check-for-updates-mode": "0",
                        "http-enable": "false", "backend-renderer": "OpenGL"}
        for line in text.splitlines():
            key = line.split(":", 1)[0]
            lines.append(f"{key}: {replacements[key]}" if key in replacements else line)
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text("\n".join(lines) + "\n")
    if f"pref-path: {fs}\n" not in config.read_text():
        raise ValueError("Configuration does not select our isolated filesystem")
    for directory in ("cache", "tmp"):
        (state / directory).mkdir(exist_ok=True)
    return fs, config


def launch_command(state, existing, arguments):
    env = os.environ | {"APPIMAGE": str(state / "Vita3K.AppImage"), "APPDIR": str(existing / "squashfs-root"),
                        "XDG_CONFIG_HOME": str(state / "config"), "XDG_DATA_HOME": str(state / "data"),
                        "XDG_CACHE_HOME": str(state / "cache"), "QT_QPA_PLATFORM": "xcb", "TMPDIR": str(state / "tmp")}
    command = ["bwrap", "--ro-bind", "/", "/", "--bind", str(state), str(state), "--dev", "/dev",
               "--dev-bind", "/dev/dri", "/dev/dri", "--proc", "/proc", "--chdir", str(state), "--",
               "bash", "-c", 'source "$APPDIR/apprun-hooks/linuxdeploy-plugin-qt-hook.sh"\nexec "$APPDIR/usr/bin/Vita3K" "$@"',
               "vita-room-emulator", *arguments]
    return command, env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--existing", type=Path, default=Path("/home/fred/cloudpunk-vita/tools/vita3k"))
    parser.add_argument("--state", type=Path, default=Path(".audit/native-room-vita/vita3k-state"))
    parser.add_argument("--vpk", type=Path)
    parser.add_argument("--run-existing", action="store_true")
    args = parser.parse_args()
    state, existing = args.state.resolve(), args.existing.resolve()
    fs, config = prepare(state, existing)
    if args.vpk:
        if args.run_existing or (fs / "ux0/app" / TITLE).exists():
            parser.error("Refusing an ambiguous launch or installation over an existing title")
        arguments = ["-c", str(config.parent), "--keep-config", "--", str(args.vpk.resolve())]
    elif args.run_existing:
        if not (fs / "ux0/app" / TITLE / "eboot.bin").is_file():
            parser.error("Our isolated title is not installed")
        arguments = ["-c", str(config.parent), "--keep-config", "-r", TITLE]
    else:
        parser.error("Choose --vpk for first installation or --run-existing")
    command, env = launch_command(state, existing, arguments)
    os.execvpe(command[0], command, env)


if __name__ == "__main__":
    main()
