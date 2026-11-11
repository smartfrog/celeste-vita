from pathlib import Path
import ctypes
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / "scripts"))
import vita_room_emulator
from smoke_native_room import main as smoke_main
from vita_room_emulator import launch_command, launcher_kind, main as emulator_main, prepare


class RuntimeLauncherTests(unittest.TestCase):
    def setUp(self):
        display = patch.dict(os.environ,{"DISPLAY":"unit-test-only.invalid:99.0"})
        display.start()
        self.addCleanup(display.stop)
        directory = ROOT / ".audit/native-room-vita/runtime-launcher-tests"
        directory.mkdir(parents=True,exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=directory)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / "state"
        self.existing = self.root / "existing"
        self.shared = self.existing / "data/Vita3K/Vita3K"
        for name in ("vs0", "sa0", "ur0/data", "ux0/user/00", "ux0/app"):
            (self.shared / name).mkdir(parents=True)
        (self.shared / "ur0/data/libshacccg.suprx").write_bytes(b"synthetic")
        (self.shared / "ux0/user/00/user.xml").write_text("synthetic")
        config = self.existing / "config/Vita3K/config.yml"
        config.parent.mkdir(parents=True)
        config.write_text("pref-path: /shared\nbackend-renderer: OpenGL\n")
        self.legacy = self.existing / "squashfs-root"
        (self.legacy / "usr/bin").mkdir(parents=True)
        (self.legacy / "usr/bin/Vita3K").write_bytes(b"synthetic")
        (self.legacy / "apprun-hooks").mkdir()
        (self.legacy / "apprun-hooks/linuxdeploy-plugin-qt-hook.sh").write_text("synthetic hook\n")

    def modern_appdir(self):
        appdir = self.root / "modern"
        (appdir / "bin").mkdir(parents=True)
        (appdir / "bin/Vita3K").write_bytes(b"synthetic")
        (appdir / "AppRun.sh").write_text("synthetic\n")
        apprun = appdir / "AppRun"
        apprun.write_bytes(b"synthetic")
        apprun.chmod(0o755)
        return appdir

    def assert_scripted_launch_rejects_display(self, display):
        for automatic in (False,True):
            with self.subTest(automatic=automatic), patch.dict(os.environ):
                if display is None:
                    os.environ.pop("DISPLAY",None)
                else:
                    os.environ["DISPLAY"] = display
                vpk = self.root / "synthetic.vpk"
                provenance = {"revision":"synthetic","tracked_changes":False,
                              "guest_replay":None if automatic else {"id":"synthetic-legacy"},
                              "guest_automatic":"first_room_auto_death_v2" if automatic else None}
                if automatic:
                    provenance["render_style"] = "animated_player_partial"
                with zipfile.ZipFile(vpk,"w") as package:
                    package.writestr("assets/native-room/provenance.json",json.dumps(provenance))
                config = self.root / "config.yml"
                config.write_text("synthetic private config\n")
                arguments = ["smoke_native_room.py","--state",str(self.state),"--output",str(self.root / str(automatic)),
                             "--vpk",str(vpk),"--appdir",str(self.legacy)]
                arguments += (["--guest-automatic","--source-root",str(self.root),"--build",str(self.root / "build"),
                               "--staging",str(self.root / "staging")] if automatic else ["--guest-replay","--after-climb"])
                pin = {"package":{"vpk_sha256":hashlib.sha256(vpk.read_bytes()).hexdigest(),
                                   "build_binding":{"capture_policy":"initial_respawn"}}}
                with patch("sys.argv",arguments), patch("smoke_native_room.prepare",return_value=(self.state,config)), \
                     patch("smoke_native_room.verify_replay_source",return_value={}), \
                     patch("smoke_native_room.verify_automatic_source",return_value=pin), \
                     patch("smoke_native_room.X11",side_effect=AssertionError("No desktop API")), \
                     patch("smoke_native_room.subprocess.Popen",side_effect=AssertionError("No installer/runtime may spawn")) as spawn:
                    with self.assertRaisesRegex(ValueError,"DISPLAY.*operator-verified"):
                        smoke_main()
                spawn.assert_not_called()

    def test_absent_display_blocks_scripted_launches_parameterized(self):
        self.assert_scripted_launch_rejects_display(None)

    def test_empty_display_blocks_scripted_launches_parameterized(self):
        self.assert_scripted_launch_rejects_display("")

    def test_whitespace_display_blocks_scripted_launches_parameterized(self):
        self.assert_scripted_launch_rejects_display(" \t\n ")

    def test_explicit_display_is_preserved_without_format_guessing_parameterized(self):
        for display in (":7",":7.1","example.invalid:9.2","unix/:8"," :7 "):
            with self.subTest(display=display), patch.dict(os.environ,{"DISPLAY":display}):
                _, env = launch_command(self.state,self.existing,["--help"])
                self.assertEqual(env["DISPLAY"],display)

    def test_absent_display_blocks_direct_emulator_exec(self):
        arguments = ["vita_room_emulator.py","--existing",str(self.existing),"--state",str(self.state),
                     "--vpk",str(self.root / "synthetic.vpk")]
        with patch.dict(os.environ), patch("sys.argv",arguments), \
             patch("vita_room_emulator.prepare",return_value=(self.state,self.root / "config.yml")), \
             patch("vita_room_emulator.os.execvpe",side_effect=AssertionError("No GUI exec")) as execute:
            os.environ.pop("DISPLAY",None)
            with self.assertRaisesRegex(ValueError,"DISPLAY.*operator-verified"):
                emulator_main()
        execute.assert_not_called()

    def test_legacy_linuxdeploy_packaging_keeps_existing_hook_launch(self):
        command,env = launch_command(self.state,self.existing,["--help"])
        self.assertEqual(launcher_kind(self.legacy),"linuxdeploy")
        self.assertIn("linuxdeploy-plugin-qt-hook.sh",command[-3])
        self.assertIn("usr/bin/Vita3K",command[-3])
        self.assertEqual(command[-2:],["vita-room-emulator","--help"])
        self.assertEqual(env["APPDIR"],str(self.legacy.resolve()))
        self.assertEqual(env["APPIMAGE"],str(self.state / "Vita3K.AppImage"))
        self.assertEqual(env["DISABLE_AUTO_UPDATES"],"1")

    def test_modern_sharun_packaging_runs_actual_apprun(self):
        appdir = self.modern_appdir()
        with patch.dict(os.environ,{"APPIMAGE":"/host/leaked.AppImage"}):
            command,env = launch_command(self.state,self.existing,["--help"],appdir=appdir)
        self.assertEqual(launcher_kind(appdir),"apprun")
        self.assertEqual(command[-2:],[str(appdir.resolve() / "AppRun"),"--help"])
        self.assertNotIn("bash",command)
        self.assertEqual(env["APPDIR"],str(appdir.resolve()))
        self.assertNotIn("APPIMAGE",env)
        self.assertEqual(env["DISABLE_AUTO_UPDATES"],"1")

    def test_explicit_appdir_is_independent_of_existing_firmware_prefix(self):
        appdir = self.modern_appdir()
        shutil.rmtree(self.legacy)
        prepare(self.state,self.existing)
        command,env = launch_command(self.state,self.existing,["--help"],appdir=appdir)
        self.assertEqual(command[-2:],[str(appdir.resolve() / "AppRun"),"--help"])
        self.assertEqual(env["APPDIR"],str(appdir.resolve()))

    def test_cli_explicit_appdir_is_forwarded_to_launch(self):
        appdir = self.modern_appdir()
        arguments = ["vita_room_emulator.py","--appdir",str(appdir),"--existing",str(self.existing),
                     "--state",str(self.state),"--vpk",str(self.root / "synthetic.vpk")]
        with patch("sys.argv",arguments), \
             patch("vita_room_emulator.prepare",return_value=(self.state,self.root / "config.yml")) as prepared, \
             patch("vita_room_emulator.launch_command",return_value=(["true"],{})) as launch, \
             patch("vita_room_emulator.os.execvpe") as execute:
            emulator_main()
        prepared.assert_called_once_with(self.state.resolve(),self.existing.resolve())
        self.assertEqual(launch.call_args.args[3],appdir.resolve())
        execute.assert_called_once()

    def test_absent_launcher_fails_explicitly(self):
        appdir = self.root / "empty"
        appdir.mkdir()
        with self.assertRaisesRegex(FileNotFoundError,"neither AppRun nor legacy"):
            launcher_kind(appdir)

    def test_smoke_absent_launcher_fails_before_state_or_x11(self):
        appdir = self.root / "empty"
        appdir.mkdir()
        vpk = self.root / "synthetic.vpk"
        with zipfile.ZipFile(vpk,"w") as package:
            package.writestr("assets/native-room/provenance.json",
                             json.dumps({"revision":"synthetic","tracked_changes":False}))
        arguments = ["smoke_native_room.py","--state",str(self.state),"--output",str(self.root / "output"),
                     "--vpk",str(vpk),"--appdir",str(appdir),"--frame-only"]
        with patch("sys.argv",arguments), patch("smoke_native_room.prepare") as prepare, \
             patch("smoke_native_room.X11") as x11:
            with self.assertRaisesRegex(FileNotFoundError,"neither AppRun nor legacy"):
                smoke_main()
        prepare.assert_not_called()
        x11.assert_not_called()
        self.assertFalse(self.state.exists())

    def test_non_executable_apprun_fails_explicitly(self):
        appdir = self.modern_appdir()
        (appdir / "AppRun").chmod(0o644)
        with self.assertRaisesRegex(PermissionError,"not executable"):
            launcher_kind(appdir)

    def test_missing_legacy_qt_hook_fails_explicitly(self):
        (self.legacy / "apprun-hooks/linuxdeploy-plugin-qt-hook.sh").unlink()
        with self.assertRaisesRegex(FileNotFoundError,"Linuxdeploy Qt hook"):
            launcher_kind(self.legacy)

    def test_private_state_tmp_replaces_host_tmp(self):
        prepare(self.state,self.existing)
        self.assertTrue((self.state / "tmp/.X11-unix").is_dir())
        command,env = launch_command(self.state,self.existing,["--help"])
        self.assertEqual(command[:10],["bwrap","--ro-bind","/","/","--bind",str(self.state / "tmp"),"/tmp",
                                       "--bind",str(self.state),str(self.state)])
        self.assertEqual(env["TMPDIR"],str(self.state / "tmp"))
        self.assertNotIn("--tmpfs",command)

    def test_x11_socket_binding_is_read_only_and_driver_access_is_unchanged(self):
        sockets = self.root / "x11-sockets"
        sockets.mkdir()
        with patch.object(vita_room_emulator,"X11_SOCKET_DIR",sockets):
            command,env = launch_command(self.state,self.existing,["--help"])
        index = command.index("/tmp/.X11-unix")
        self.assertEqual(command[index-2:index+1],["--ro-bind",str(sockets),"/tmp/.X11-unix"])
        index = command.index("--dev-bind")
        self.assertEqual(command[index:index+3],["--dev-bind","/dev/dri","/dev/dri"])
        self.assertEqual(env["XAUTHORITY"],str(Path(os.environ["HOME"]) / ".Xauthority") if os.environ.get("HOME") else "")

    def test_appdir_containing_writable_state_is_rejected(self):
        appdir = Path("/tmp/native-room-path-validation")
        state = appdir / "state"
        with self.assertRaisesRegex(ValueError,"contains writable emulator state"):
            vita_room_emulator._narrow_readonly_mounts(state,self.existing,appdir,())

    def test_vendor_auto_update_is_disabled_without_network_permission(self):
        appdir = self.modern_appdir()
        command,env = launch_command(self.state,self.existing,["--help"],appdir=appdir)
        self.assertEqual(env["DISABLE_AUTO_UPDATES"],"1")
        self.assertNotIn("--share-net",command)

    def test_host_environment_is_private_and_agent_channels_are_removed(self):
        inherited = {"DBUS_SESSION_BUS_ADDRESS":"unix:path=/run/user/1000/bus",
                     "DBUS_SESSION_BUS_PID":"123", "SSH_AUTH_SOCK":"/tmp/agent.sock",
                     "SSH_AGENT_PID":"456", "XAUTHORITY":"/tmp/real.Xauthority"}
        with patch.dict(os.environ,inherited,clear=False):
            command,env = launch_command(self.state,self.existing,["--help"])
        self.assertEqual(env["HOME"],str(self.state / "home"))
        self.assertEqual(env["XDG_RUNTIME_DIR"],str(self.state / "runtime"))
        for name in ("DBUS_SESSION_BUS_ADDRESS","DBUS_SESSION_BUS_PID","SSH_AUTH_SOCK","SSH_AGENT_PID"):
            self.assertNotIn(name,env)
        self.assertEqual(env["XAUTHORITY"],"/tmp/real.Xauthority")
        self.assertIn("--unshare-net",command)

    def test_unset_xauthority_keeps_original_home_authority_path(self):
        original_home = self.root / "original-home"
        original_home.mkdir()
        authority = original_home / ".Xauthority"
        authority.write_bytes(b"generated-fake-bytes")
        with patch.dict(os.environ,{"HOME":str(original_home),"PATH":os.environ["PATH"],"DISPLAY":"unit-test-only.invalid:99.0"},clear=True):
            command,env = launch_command(self.state,self.existing,["--help"])
        self.assertEqual(env["HOME"],str(self.state / "home"))
        self.assertEqual(env["XAUTHORITY"],str(authority))
        self.assertFalse((self.state / "home/.Xauthority").exists())

    def test_missing_original_authority_is_not_replaced_by_private_home(self):
        original_home = self.root / "empty-home"
        original_home.mkdir()
        with patch.dict(os.environ,{"HOME":str(original_home),"PATH":os.environ["PATH"],"DISPLAY":"unit-test-only.invalid:99.0"},clear=True):
            command,env = launch_command(self.state,self.existing,["--help"])
        self.assertEqual(env["XAUTHORITY"],str(original_home / ".Xauthority"))
        self.assertFalse((self.state / "home/.Xauthority").exists())

    def test_explicit_empty_xauthority_stays_explicitly_empty(self):
        with patch.dict(os.environ,{"HOME":str(self.root),"XAUTHORITY":"","PATH":os.environ["PATH"],"DISPLAY":"unit-test-only.invalid:99.0"},clear=True):
            command,env = launch_command(self.state,self.existing,["--help"])
        self.assertEqual(env["XAUTHORITY"],"")

    def test_authority_path_matches_connection_free_xau_resolver(self):
        try:
            xau = ctypes.CDLL("libXau.so.6")
        except OSError:
            self.skipTest("libXau unavailable")
        xau.XauFileName.restype = ctypes.c_char_p
        for environment in ({"HOME":"/tmp/generated-home"},
                            {"HOME":"/tmp/generated-home","XAUTHORITY":""},
                            {"HOME":"/tmp/generated-home","XAUTHORITY":"/tmp/generated-auth"},
                            {}):
            with self.subTest(environment=environment):
                with patch.dict(os.environ,environment | {"DISPLAY":"unit-test-only.invalid:99.0"},clear=True):
                    expected = xau.XauFileName()
                    command,env = launch_command(self.state,self.existing,["--help"])
                self.assertEqual(env["XAUTHORITY"],"" if expected is None else os.fsdecode(expected))


if __name__ == "__main__":
    unittest.main()
