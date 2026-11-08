from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from vita_room_emulator import TITLE, prepare, launch_command


class EmulatorIsolationTests(unittest.TestCase):
    def setUp(self):
        root = ROOT / ".audit/native-room-vita/isolation-tests"
        root.mkdir(parents=True,exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.existing = self.root / "existing"
        self.shared = self.existing / "data/Vita3K/Vita3K"
        for directory in ("vs0", "sa0", "ur0/data", "ux0/user/00", "ux0/app"):
            (self.shared / directory).mkdir(parents=True)
        (self.shared / "ur0/data/libshacccg.suprx").write_bytes(b"synthetic")
        (self.shared / "ux0/user/00/user.xml").write_text("synthetic")
        config = self.existing / "config/Vita3K/config.yml"
        config.parent.mkdir(parents=True)
        config.write_text("pref-path: /shared\nbackend-renderer: OpenGL\n")
        self.state = self.root / "state"

    def test_writable_filesystem_symlink_is_rejected(self):
        fs = self.state / "data/Vita3K/Vita3K"
        fs.mkdir(parents=True)
        (fs / "ux0").symlink_to(self.shared / "ux0",target_is_directory=True)
        with self.assertRaisesRegex(ValueError,"Writable path escapes"):
            prepare(self.state,self.existing)

    def test_shared_title_id_conflict_is_rejected(self):
        (self.shared / "ux0/app" / TITLE).mkdir()
        with self.assertRaisesRegex(ValueError,"already exists"):
            prepare(self.state,self.existing)

    def test_writable_state_and_readonly_dependencies_are_separate(self):
        fs, config = prepare(self.state,self.existing)
        self.assertEqual((fs / "vs0").resolve(),self.shared / "vs0")
        self.assertEqual((fs / "sa0").resolve(),self.shared / "sa0")
        self.assertFalse((fs / "ux0").is_symlink())
        self.assertIn(f"pref-path: {fs}\n",config.read_text())

    def test_launcher_mounts_host_readonly_and_only_state_writable(self):
        command, env = launch_command(self.state,self.existing,["--help"])
        self.assertEqual(command[:7],["bwrap","--ro-bind","/","/","--bind",str(self.state),str(self.state)])
        self.assertEqual(env["XDG_DATA_HOME"],str(self.state / "data"))

    def test_readback_enables_surface_sync_only_in_private_config(self):
        shared_config = self.existing / "config/Vita3K/config.yml"
        shared_text = "pref-path: /shared\nbackend-renderer: OpenGL\nresolution-multiplier: 1\ndisable-surface-sync: true\n"
        shared_config.write_text(shared_text)
        fs, config = prepare(self.state,self.existing)
        text = config.read_text()
        self.assertIn("disable-surface-sync: false\n",text)
        self.assertIn("resolution-multiplier: 1\n",text)
        self.assertIn("backend-renderer: OpenGL\n",text)
        self.assertEqual(shared_config.read_text(),shared_text)

    def test_existing_private_config_with_disabled_surface_sync_is_rejected(self):
        fs, config = prepare(self.state,self.existing)
        config.write_text(config.read_text().replace("disable-surface-sync: false","disable-surface-sync: true"))
        with self.assertRaisesRegex(ValueError,"surface synchronization"):
            prepare(self.state,self.existing)
