import hashlib
from pathlib import Path
import stat
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from game_input import read_members, normalize_game


class GameInputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.files = {"Celeste.exe": b"synthetic executable", "Content/map.bin": b"synthetic map"}
        self.pins = {name: hashlib.sha256(data).hexdigest() for name, data in self.files.items()}

    def archive(self, files, prefix=""):
        path = self.root / "game.zip"
        with zipfile.ZipFile(path, "w") as package:
            for name, data in files.items():
                package.writestr(prefix + name, data)
        return path

    def installation(self):
        for name, data in self.files.items():
            path = self.root / "installation" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return self.root / "installation"

    def test_reads_compatible_directory(self):
        self.assertEqual(read_members(self.installation(), self.pins), self.files)

    def test_reads_repacked_archive_with_enclosing_directory(self):
        self.assertEqual(read_members(self.archive(self.files, "Celeste/"), self.pins), self.files)

    def test_rejects_changed_required_member(self):
        source = self.archive(self.files | {"Celeste.exe": b"modified"})
        with self.assertRaisesRegex(ValueError, "identity.*Celeste.exe"):
            read_members(source, self.pins)

    def test_rejects_missing_required_member(self):
        with self.assertRaisesRegex(ValueError, "Missing.*Content/map.bin"):
            read_members(self.archive({"Celeste.exe": self.files["Celeste.exe"]}), self.pins)

    def test_rejects_traversal_even_in_unused_member(self):
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            read_members(self.archive(self.files | {"../escape": b"bad"}), self.pins)

    def test_rejects_duplicate_archive_member(self):
        source = self.archive(self.files)
        with zipfile.ZipFile(source, "a") as package:
            with self.assertWarns(UserWarning):
                package.writestr("Celeste.exe", b"duplicate")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            read_members(source, self.pins)

    def test_rejects_ambiguous_game_roots(self):
        source = self.archive(self.files | {"other/Celeste.exe": b"other"})
        with self.assertRaisesRegex(ValueError, "exactly one"):
            read_members(source, self.pins)

    def test_rejects_archive_symlink(self):
        source = self.archive(self.files)
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(source, "a") as package:
            package.writestr(info, "Celeste.exe")
        with self.assertRaisesRegex(ValueError, "regular"):
            read_members(source, self.pins)

    def test_rejects_directory_symlink(self):
        source = self.installation()
        (source / "outside").mkdir()
        (source / "Content/map.bin").rename(source / "outside/map.bin")
        (source / "Content").rmdir()
        (source / "Content").symlink_to(source / "outside", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            read_members(source, self.pins)

    def test_rejects_oversized_required_member(self):
        with self.assertRaisesRegex(ValueError, "bound"):
            read_members(self.archive(self.files), self.pins, max_bytes=3)

    def test_normalization_copies_only_verified_required_files(self):
        source = self.archive(self.files | {"unneeded.txt": b"not copied"}, "Celeste/")
        output = self.root / "prepared"
        normalized = normalize_game(source, output, self.pins)
        self.assertEqual(read_members(normalized, self.pins), self.files)
        self.assertEqual((output / "inputs/Celeste.exe").read_bytes(), self.files["Celeste.exe"])
        with zipfile.ZipFile(normalized) as package:
            self.assertEqual(set(package.namelist()), set(self.files))

    def test_normalization_preserves_existing_output(self):
        output = self.root / "prepared"
        output.mkdir()
        (output / "keep").write_bytes(b"preserved")
        with self.assertRaises(FileExistsError):
            normalize_game(self.archive(self.files), output, self.pins)
        self.assertEqual((output / "keep").read_bytes(), b"preserved")

    def test_normalization_uses_fixed_archive_timestamps(self):
        normalized = normalize_game(self.installation(), self.root / "prepared", self.pins)
        with zipfile.ZipFile(normalized) as package:
            self.assertTrue(all(entry.date_time == (1980, 1, 1, 0, 0, 0) for entry in package.infolist()))

    def test_rejects_other_unsafe_archive_paths(self):
        for name in ("/absolute", "C:/drive", "Content\\escape", "./noncanonical", "a//duplicate"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "Unsafe"):
                    read_members(self.archive(self.files | {name: b"bad"}), self.pins)


if __name__ == "__main__":
    unittest.main()
