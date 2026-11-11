from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

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
        legacy = self.existing / "squashfs-root"
        (legacy / "usr/bin").mkdir(parents=True)
        (legacy / "usr/bin/Vita3K").write_bytes(b"synthetic")
        (legacy / "apprun-hooks").mkdir()
        (legacy / "apprun-hooks/linuxdeploy-plugin-qt-hook.sh").write_text("synthetic hook\n")
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
        with patch.dict("os.environ",{"DISPLAY":"unit-test-only.invalid:99.0"}):
            command, env = launch_command(self.state,self.existing,["--help"])
        self.assertEqual(command[:7],["bwrap","--ro-bind","/","/","--bind",str(self.state / "tmp"),"/tmp"])
        self.assertEqual(command[7:10],["--bind",str(self.state),str(self.state)])
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

    def test_private_config_seeds_verified_profile_and_controller_defaults(self):
        fs, config = prepare(self.state,self.existing)
        text = config.read_text()
        self.assertIn("user-id: 00\n",text)
        self.assertIn("controller-binds:\n"+"".join(f"  - {value}\n" for value in range(15)),text)
        self.assertIn("controller-axis-binds:\n"+"".join(f"  - {value}\n" for value in range(6)),text)

    def test_private_home_and_runtime_are_fresh_private_directories(self):
        prepare(self.state,self.existing)
        for name in ("home","runtime"):
            path = self.state / name
            self.assertTrue(path.is_dir())
            self.assertEqual(path.stat().st_mode & 0o777,0o700)

    def test_fresh_fontconfig_cache_is_created_private_and_owned(self):
        prepare(self.state,self.existing)
        cache = self.state / 'cache/fontconfig'
        self.assertTrue(cache.is_dir())
        self.assertFalse(cache.is_symlink())
        self.assertEqual(cache.stat().st_mode & 0o777,0o700)
        self.assertEqual(cache.stat().st_uid,os.geteuid())

    def test_existing_fontconfig_cache_mode_and_bytes_are_preserved(self):
        cache = self.state / 'cache/fontconfig'
        cache.mkdir(parents=True)
        cache.chmod(0o755)
        sentinel = cache / 'existing.cache'
        sentinel.write_bytes(b'private test cache remains unchanged')
        sentinel.chmod(0o600)
        before = (cache.stat().st_ino,cache.stat().st_mode,sentinel.stat().st_mode,sentinel.read_bytes())
        prepare(self.state,self.existing)
        self.assertEqual((cache.stat().st_ino,cache.stat().st_mode,sentinel.stat().st_mode,sentinel.read_bytes()),before)

    def test_escaping_fontconfig_symlinks_are_rejected_before_writes_parameterized(self):
        for exists in (True,False):
            with self.subTest(target_exists=exists):
                state = self.root / f'escaping-state-{exists}'
                cache = state / 'cache'
                cache.mkdir(parents=True)
                outside = self.root / f'outside-fontconfig-{exists}'
                if exists:
                    outside.mkdir()
                    (outside / 'sentinel').write_bytes(b'private outside fixture')
                fontconfig = cache / 'fontconfig'
                fontconfig.symlink_to(outside,target_is_directory=True)
                link_before = (fontconfig.lstat().st_ino,fontconfig.lstat().st_mode,fontconfig.readlink())
                with patch.object(Path,'mkdir',side_effect=AssertionError('Validation must precede writes')), \
                     patch.object(Path,'write_text',side_effect=AssertionError('No config writes')), \
                     patch.object(Path,'symlink_to',side_effect=AssertionError('No dependency writes')), \
                     patch.object(Path,'chmod',side_effect=AssertionError('No permission changes')), \
                     patch('vita_room_emulator.shutil.copyfile',side_effect=AssertionError('No user data copies')), \
                     self.assertRaisesRegex(ValueError,'Writable path escapes.*cache/fontconfig'):
                    prepare(state,self.existing)
                self.assertEqual((fontconfig.lstat().st_ino,fontconfig.lstat().st_mode,fontconfig.readlink()),link_before)
                self.assertFalse((state / 'data').exists())
                self.assertFalse((state / 'config').exists())
                if exists:
                    self.assertEqual((outside / 'sentinel').read_bytes(),b'private outside fixture')
                else:
                    self.assertFalse(outside.exists())

    def test_existing_within_state_fontconfig_symlink_remains_operative(self):
        target = self.state / 'owned-fontconfig'
        target.mkdir(parents=True)
        target.chmod(0o755)
        (target / 'sentinel').write_bytes(b'owned linked cache')
        cache = self.state / 'cache'
        cache.mkdir()
        fontconfig = cache / 'fontconfig'
        fontconfig.symlink_to(target,target_is_directory=True)
        before = (fontconfig.lstat().st_ino,fontconfig.readlink(),target.stat().st_ino,target.stat().st_mode)
        prepare(self.state,self.existing)
        self.assertTrue(fontconfig.is_symlink())
        self.assertEqual((fontconfig.lstat().st_ino,fontconfig.readlink(),target.stat().st_ino,target.stat().st_mode),before)
        self.assertEqual((fontconfig / 'sentinel').read_bytes(),b'owned linked cache')

    def test_existing_fontconfig_regular_file_is_preserved_and_rejected(self):
        cache = self.state / 'cache'
        cache.mkdir(parents=True)
        fontconfig = cache / 'fontconfig'
        fontconfig.write_bytes(b'not a cache directory')
        fontconfig.chmod(0o600)
        before = (fontconfig.stat().st_ino,fontconfig.stat().st_mode,fontconfig.read_bytes())
        with self.assertRaises(FileExistsError):
            prepare(self.state,self.existing)
        self.assertEqual((fontconfig.stat().st_ino,fontconfig.stat().st_mode,fontconfig.read_bytes()),before)
