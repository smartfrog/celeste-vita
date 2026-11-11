#!/usr/bin/env python3
"""Launch only this diagnostic in an isolated writable Vita3K filesystem."""

import argparse
import os
from pathlib import Path
import shutil

TITLE = "CELR00001"
X11_SOCKET_DIR = Path("/tmp/.X11-unix")
PROFILE_USER_ID = "00"
CONTROLLER_BINDS = tuple(range(15))
CONTROLLER_AXIS_BINDS = tuple(range(6))
PRIVATE_ENVIRONMENT = ("DBUS_SESSION_BUS_ADDRESS", "DBUS_SESSION_BUS_PID", "SSH_AUTH_SOCK", "SSH_AGENT_PID")


def _seed_list(lines, key, values):
    items = [f"  - {value}" for value in values]
    for index,line in enumerate(lines):
        if line == f"{key}: []":
            lines[index:index+1] = [f"{key}:", *items]
            return
        if line == f"{key}:":
            if index+1 < len(lines) and lines[index+1].strip() == "[]":
                lines[index+1:index+2] = items
            return
    lines.extend([f"{key}:", *items])


def launcher_kind(appdir):
    appdir = Path(appdir)
    if not appdir.is_dir():
        raise FileNotFoundError(f"Missing Vita3K AppDir: {appdir}")
    apprun = appdir / "AppRun"
    if apprun.exists():
        if not apprun.is_file():
            raise FileNotFoundError(f"AppRun is not a regular file: {apprun}")
        if not os.access(apprun,os.X_OK):
            raise PermissionError(f"AppRun is not executable: {apprun}")
        return "apprun"
    binary = appdir / "usr/bin/Vita3K"
    if not binary.is_file():
        raise FileNotFoundError(f"AppDir has neither AppRun nor legacy launcher: {binary}")
    hook = appdir / "apprun-hooks/linuxdeploy-plugin-qt-hook.sh"
    if not hook.is_file():
        raise FileNotFoundError(f"Missing legacy Linuxdeploy Qt hook: {hook}")
    return "linuxdeploy"


def prepare(state, existing):
    state = state.resolve()
    if not state.is_relative_to(Path(__file__).resolve().parents[1] / ".audit/native-room-vita"):
        raise ValueError("Emulator state must be beneath .audit/native-room-vita")
    shared = existing / "data/Vita3K/Vita3K"
    if (shared / "ux0/app" / TITLE).exists():
        raise ValueError("Diagnostic title ID already exists in shared state; refusing")
    fs = state / "data/Vita3K/Vita3K"
    for relative in ("data", "data/Vita3K", "data/Vita3K/Vita3K", "config", "config/Vita3K",
                     "config/Vita3K/config.yml", "cache", "cache/fontconfig", "tmp", "tmp/.X11-unix", "home", "runtime",
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
    replacements = {"pref-path": str(fs), "discord-rich-presence": "false", "check-for-updates-mode": "0",
                    "http-enable": "false", "backend-renderer": "OpenGL", "resolution-multiplier": "1",
                    "disable-surface-sync": "false", "user-id": PROFILE_USER_ID}
    if not config.exists():
        text = (existing / "config/Vita3K/config.yml").read_text()
        lines = []
        seen = set()
        for line in text.splitlines():
            key = line.split(":", 1)[0]
            seen.add(key)
            lines.append(f"{key}: {replacements[key]}" if key in replacements else line)
        lines.extend(f"{key}: {value}" for key,value in replacements.items() if key not in seen)
        _seed_list(lines,"controller-binds",CONTROLLER_BINDS)
        _seed_list(lines,"controller-axis-binds",CONTROLLER_AXIS_BINDS)
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text("\n".join(lines) + "\n")
    if f"pref-path: {fs}\n" not in config.read_text():
        raise ValueError("Configuration does not select our isolated filesystem")
    for key in ("backend-renderer","resolution-multiplier","disable-surface-sync"):
        if [line for line in config.read_text().splitlines() if line.startswith(key+":")] != [f"{key}: {replacements[key]}"]:
            raise ValueError("Private readback requires OpenGL 1x with surface synchronization enabled")
    for directory in ("cache", "tmp", "tmp/.X11-unix", "home", "runtime"):
        (state / directory).mkdir(exist_ok=True)
    (state / "cache/fontconfig").mkdir(mode=0o700,exist_ok=True)
    for directory in ("home", "runtime"):
        (state / directory).chmod(0o700)
    return fs, config


def _authority_path(environment):
    if "XAUTHORITY" in environment:
        return environment["XAUTHORITY"]
    home = environment.get("HOME")
    return str(Path(home) / ".Xauthority") if home else ""


def _narrow_readonly_mounts(state, existing, appdir, readonly_paths):
    shared = existing / "data/Vita3K/Vita3K"
    dependencies = [appdir, shared / "vs0", shared / "sa0", shared / "ur0/data",
                    *(Path(path) for path in readonly_paths)]
    mounts, seen = [], set()
    for dependency in dependencies:
        if not dependency.is_absolute():
            dependency = dependency.resolve()
        if not dependency.is_relative_to("/tmp") or dependency.is_relative_to(state):
            continue
        if state.is_relative_to(dependency):
            raise ValueError(f"Read-only dependency contains writable emulator state: {dependency}")
        if dependency in seen or not dependency.exists():
            continue
        seen.add(dependency)
        mounts.extend(["--ro-bind", str(dependency), str(dependency)])
    return mounts


def launch_command(state, existing, arguments, appdir=None, readonly_paths=(), unshare_pid=False):
    if not os.environ.get("DISPLAY", "").strip():
        raise ValueError("Vita3K real GUI launch requires a nonblank DISPLAY; set it to an operator-verified existing display")
    state = state.resolve()
    appdir = Path(appdir).resolve() if appdir is not None else (existing / "squashfs-root").resolve()
    kind = launcher_kind(appdir)
    authority = _authority_path(os.environ)
    env = os.environ | {"XDG_CONFIG_HOME": str(state / "config"), "XDG_DATA_HOME": str(state / "data"),
                        "XDG_CACHE_HOME": str(state / "cache"), "QT_QPA_PLATFORM": "xcb",
                        "TMPDIR": str(state / "tmp"), "HOME": str(state / "home"),
                        "XDG_RUNTIME_DIR": str(state / "runtime"), "XAUTHORITY": authority,
                        "DISABLE_AUTO_UPDATES": "1", "APPDIR": str(appdir)}
    for name in PRIVATE_ENVIRONMENT:
        env.pop(name,None)
    if kind == "linuxdeploy":
        env["APPIMAGE"] = str(state / "Vita3K.AppImage")
    else:
        env.pop("APPIMAGE",None)
    protected_paths = list(readonly_paths)
    if authority and Path(authority).is_absolute():
        protected_paths.append(Path(authority))
    mounts = ["--bind", str(state / "tmp"), "/tmp", "--bind", str(state), str(state)]
    mounts.extend(_narrow_readonly_mounts(state,existing,appdir,protected_paths))
    if X11_SOCKET_DIR.is_dir():
        mounts.extend(["--ro-bind", str(X11_SOCKET_DIR), "/tmp/.X11-unix"])
    command = ["bwrap", "--ro-bind", "/", "/", *mounts, "--unshare-net",
               *(["--unshare-pid"] if unshare_pid else []),
               "--dev", "/dev", "--dev-bind", "/dev/dri", "/dev/dri", "--proc", "/proc",
               "--die-with-parent", "--new-session", "--chdir", str(state), "--"]
    if kind == "apprun":
        command.append(str(appdir / "AppRun"))
    else:
        command.extend(["bash", "-c", 'source "$APPDIR/apprun-hooks/linuxdeploy-plugin-qt-hook.sh"\nexec "$APPDIR/usr/bin/Vita3K" "$@"',
                        "vita-room-emulator"])
    command.extend(arguments)
    return command, env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--existing", type=Path, default=Path("/home/fred/cloudpunk-vita/tools/vita3k"))
    parser.add_argument("--appdir", type=Path, help="Extracted AppDir; default is <existing>/squashfs-root")
    parser.add_argument("--state", type=Path, default=Path(".audit/native-room-vita/vita3k-state"))
    parser.add_argument("--vpk", type=Path)
    parser.add_argument("--run-existing", action="store_true")
    args = parser.parse_args()
    state, existing = args.state.resolve(), args.existing.resolve()
    appdir = (args.appdir or existing / "squashfs-root").resolve()
    launcher_kind(appdir)
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
    command, env = launch_command(state, existing, arguments, appdir,
                                  readonly_paths=[args.vpk.resolve()] if args.vpk else [])
    os.execvpe(command[0], command, env)


if __name__ == "__main__":
    main()
