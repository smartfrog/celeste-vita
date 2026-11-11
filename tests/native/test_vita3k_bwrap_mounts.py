import fcntl
import os
import select
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / "scripts"))
import vita_room_emulator
from vita_room_emulator import launch_command


class RealBubblewrapMountTests(unittest.TestCase):
    def setUp(self):
        if shutil.which("bwrap") is None:
            self.skipTest("bubblewrap unavailable")
        probe = subprocess.run(["bwrap","--ro-bind","/","/","--","/bin/true"],capture_output=True)
        if probe.returncode:
            self.skipTest("bubblewrap user namespaces unavailable")
        directory = ROOT / ".audit/native-room-vita/bwrap-mount-tests"
        self.assertTrue(directory.resolve().is_relative_to(Path.home().resolve()))
        directory.mkdir(parents=True,exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=directory)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / "state"
        (self.state / "tmp").mkdir(parents=True)
        (self.state / "home").mkdir(mode=0o700)
        (self.state / "runtime").mkdir(mode=0o700)
        self.appdir = self.root / "appdir"
        (self.appdir / "bin").mkdir(parents=True)
        (self.appdir / "data.txt").write_text("appdir-data\n")
        self.vpk = self.root / "replay.vpk"
        self.vpk.write_text("vpk-data\n")
        self.existing = self.root / "existing"
        shared = self.existing / "data/Vita3K/Vita3K"
        for name,content in (("vs0","vs0-data"),("sa0","sa0-data"),("ur0/data","shader-data")):
            (shared / name).mkdir(parents=True)
            (shared / name / "marker.txt").write_text(content+"\n")
        self.x11 = self.root / "x11"
        self.x11.mkdir()

    def write_apprun(self,body):
        apprun = self.appdir / "AppRun"
        apprun.write_text("#!/bin/sh\nset -eu\n"+body)
        apprun.chmod(0o755)

    def write_python_apprun(self,body):
        apprun = self.appdir / "AppRun"
        apprun.write_text("#!/usr/bin/python3\n"+body)
        apprun.chmod(0o755)

    def command_for(self,arguments,readonly_paths=(),unshare_pid=False):
        with patch.dict(os.environ,{"DISPLAY":"unit-test-only.invalid:99.0"}), \
             patch.object(vita_room_emulator,"X11_SOCKET_DIR",self.x11):
            return launch_command(self.state,self.existing,arguments,appdir=self.appdir,
                                  readonly_paths=readonly_paths,unshare_pid=unshare_pid)

    def run_probe(self,arguments,readonly_paths=(),unshare_pid=False):
        command,env = self.command_for(arguments,readonly_paths,unshare_pid)
        return subprocess.run(command,env=env,cwd=self.state,capture_output=True,text=True,timeout=30)

    def assert_child_lock_released(self,lock,stop):
        lock_fd = os.open(lock, os.O_RDWR)
        held = True
        try:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
                held = False
            except BlockingIOError:
                writer = os.open(stop, os.O_WRONLY|os.O_NONBLOCK)
                os.write(writer, b"x")
                os.close(writer)
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
        finally:
            os.close(lock_fd)
        self.assertFalse(held)

    def test_state_under_tmp_is_visible_and_writable_after_private_tmp_overlay(self):
        self.write_apprun('pwd\nprintf state > "$1"\nprintf tmp > /tmp/probe.txt\n')
        result = self.run_probe([str(self.state / "probe-state.txt")])
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),str(self.state))
        self.assertEqual((self.state / "probe-state.txt").read_text(),"state")
        self.assertEqual((self.state / "tmp/probe.txt").read_text(),"tmp")

    def test_appdir_vpk_and_firmware_under_tmp_are_readable(self):
        shared = self.existing / "data/Vita3K/Vita3K"
        self.write_apprun('cat "$1"\ncat "$2"\ncat "$3"\ncat "$4"\ncat "$5"\n')
        result = self.run_probe([str(self.appdir / "data.txt"),str(self.vpk),
                                 str(shared / "vs0/marker.txt"),str(shared / "sa0/marker.txt"),
                                 str(shared / "ur0/data/marker.txt")],readonly_paths=[self.vpk])
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.splitlines(),["appdir-data","vpk-data","vs0-data","sa0-data","shader-data"])

    def test_fake_x11_socket_directory_is_readonly_visible_in_private_tmp(self):
        (self.x11 / "marker.txt").write_text("x11-data\n")
        self.write_apprun('cat /tmp/.X11-unix/marker.txt\n'
                          'if printf denied > /tmp/.X11-unix/denied.txt 2>/dev/null; then echo X11WRITE; else echo X11RO; fi\n')
        result = self.run_probe([])
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.splitlines(),["x11-data","X11RO"])

    def test_unmapped_host_tmp_path_stays_hidden(self):
        # A pre-existing host file exercises /tmp masking without writing outside HOME.
        fixture = os.environ.get("CELESTE_TEST_HOST_TMP_FILE")
        self.assertIsNotNone(fixture,"Set CELESTE_TEST_HOST_TMP_FILE to an existing non-sensitive host /tmp file")
        hidden = Path(fixture).resolve()
        self.assertTrue(hidden.is_relative_to("/tmp"))
        self.assertTrue(hidden.is_file(),"The forbidden host path must exist before the sandbox starts")
        for allowed in (self.state,self.appdir,self.existing,self.x11):
            self.assertFalse(hidden.is_relative_to(allowed))
        self.write_apprun('if [ -e "$1" ]; then echo VISIBLE; else echo HIDDEN; fi\n')
        result = self.run_probe([str(hidden)])
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),"HIDDEN")
        self.assertTrue(hidden.is_file(),"The original forbidden host file must remain intact")

    def test_only_state_remains_writable(self):
        shared = self.existing / "data/Vita3K/Vita3K"
        self.write_apprun(
            'if printf denied > "$1" 2>/dev/null; then echo APPWRITE; else echo APPRO; fi\n'
            'if printf denied > "$2" 2>/dev/null; then echo VPKWRITE; else echo VPKRO; fi\n'
            'if printf denied > "$3" 2>/dev/null; then echo FWWRITE; else echo FWRO; fi\n'
            'printf state > "$4"\nprintf tmp > /tmp/allowed.txt\n')
        result = self.run_probe([str(self.appdir / "denied.txt"),str(self.vpk),
                                 str(shared / "vs0/denied.txt"),str(self.state / "allowed.txt")],
                                readonly_paths=[self.vpk])
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.splitlines(),["APPRO","VPKRO","FWRO"])
        self.assertEqual((self.state / "allowed.txt").read_text(),"state")
        self.assertEqual((self.state / "tmp/allowed.txt").read_text(),"tmp")


    def test_network_namespace_exposes_only_loopback(self):
        self.write_apprun("/usr/bin/awk -F: 'NR>2 {gsub(/ /,\"\",$1); print $1}' /proc/net/dev\n")
        result = self.run_probe([])
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(set(result.stdout.split()),{"lo"})

    def test_private_home_runtime_and_sanitized_environment_inside_sandbox(self):
        self.write_apprun(
            'printf "%s\\n" "$HOME" "$XDG_RUNTIME_DIR" "${DBUS_SESSION_BUS_ADDRESS-unset}" '
            '"${SSH_AUTH_SOCK-unset}" "${XAUTHORITY-unset}"\n'
            'printf home > "$HOME/probe.txt"\nprintf runtime > "$XDG_RUNTIME_DIR/probe.txt"\n')
        inherited = {"DBUS_SESSION_BUS_ADDRESS":"unix:path=/run/user/1000/bus",
                     "SSH_AUTH_SOCK":"/tmp/agent.sock","XAUTHORITY":"/tmp/real.Xauthority"}
        with patch.dict(os.environ,inherited,clear=False):
            result = self.run_probe([])
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.splitlines(),[str(self.state / "home"),str(self.state / "runtime"),
                                                     "unset","unset","/tmp/real.Xauthority"])
        self.assertEqual((self.state / "home/probe.txt").read_text(),"home")
        self.assertEqual((self.state / "runtime/probe.txt").read_text(),"runtime")

    def test_original_authority_under_tmp_is_readonly_visible(self):
        original_home = self.root / "original-home"
        original_home.mkdir()
        authority = original_home / ".Xauthority"
        authority.write_bytes(b"generated-fake-auth\n")
        self.write_apprun('/usr/bin/cat "$XAUTHORITY"\n'
                          'if /usr/bin/printf denied > "$XAUTHORITY" 2>/dev/null; then echo AUTHWRITE; else echo AUTHRO; fi\n')
        with patch.dict(os.environ,{"HOME":str(original_home),"PATH":os.environ["PATH"]},clear=True):
            result = self.run_probe([])
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.splitlines(),["generated-fake-auth","AUTHRO"])
        self.assertFalse((self.state / "home/.Xauthority").exists())

    def test_guest_pid_namespace_reaps_detached_launcher_child(self):
        lock = self.state / "child.lock"
        stop = self.state / "stop.fifo"
        os.mkfifo(stop)
        self.write_python_apprun(
            "import fcntl, os, sys\n"
            "lock, stop = sys.argv[1:3]\n"
            "read_fd, write_fd = os.pipe()\n"
            "if os.fork() == 0:\n"
            "    os.close(read_fd)\n"
            "    os.setsid()\n"
            "    lock_fd = os.open(lock, os.O_RDWR|os.O_CREAT, 0o600)\n"
            "    fcntl.flock(lock_fd, fcntl.LOCK_EX)\n"
            "    stop_fd = os.open(stop, os.O_RDWR)\n"
            "    os.write(write_fd, b'r')\n"
            "    os.close(write_fd)\n"
            "    os.read(stop_fd, 1)\n"
            "    os._exit(0)\n"
            "os.close(write_fd)\n"
            "os.read(read_fd, 1)\n")
        result = self.run_probe([str(lock),str(stop)],unshare_pid=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assert_child_lock_released(lock,stop)

    def test_guest_pid_namespace_reaps_detached_child_on_owned_termination(self):
        lock = self.state / "child.lock"
        stop = self.state / "stop.fifo"
        ready = self.state / "ready.fifo"
        os.mkfifo(stop)
        os.mkfifo(ready)
        self.write_python_apprun(
            "import fcntl, os, signal, sys\n"
            "lock, stop, ready = sys.argv[1:4]\n"
            "read_fd, write_fd = os.pipe()\n"
            "if os.fork() == 0:\n"
            "    os.close(read_fd)\n"
            "    os.setsid()\n"
            "    lock_fd = os.open(lock, os.O_RDWR|os.O_CREAT, 0o600)\n"
            "    fcntl.flock(lock_fd, fcntl.LOCK_EX)\n"
            "    stop_fd = os.open(stop, os.O_RDWR)\n"
            "    os.write(write_fd, b'r')\n"
            "    os.close(write_fd)\n"
            "    os.read(stop_fd, 1)\n"
            "    os._exit(0)\n"
            "os.close(write_fd)\n"
            "os.read(read_fd, 1)\n"
            "ready_fd = os.open(ready, os.O_WRONLY)\n"
            "os.write(ready_fd, b'r')\n"
            "os.close(ready_fd)\n"
            "signal.pause()\n")
        command,env = self.command_for([str(lock),str(stop),str(ready)],unshare_pid=True)
        ready_fd = os.open(ready, os.O_RDONLY|os.O_NONBLOCK)
        process = subprocess.Popen(command,env=env,cwd=self.state,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            readable,_,_ = select.select([ready_fd],[],[],30)
            self.assertEqual(readable,[ready_fd],"detached child did not become ready")
        finally:
            process.terminate()
            process.wait(timeout=15)
            os.close(ready_fd)
        self.assert_child_lock_released(lock,stop)


if __name__ == "__main__":
    unittest.main()
