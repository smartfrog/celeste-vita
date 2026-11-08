import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from check_player_runtime_reuse import normalize_build, normalized_revision, require_equal, resident_sections


class RuntimeReuseProofTests(unittest.TestCase):
    def test_only_declared_revision_text_is_normalized(self):
        self.assertEqual(normalized_revision(b"code old-revision other-data", "old-revision"), b"code <REVISION> other-data")

    def test_changed_runtime_bytes_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "differs"):
            require_equal(b"old-code", b"new-code", "runtime")

    def test_full_revision_build_and_staging_paths_are_normalized(self):
        old_revision, new_revision = "a" * 40, "b" * 40
        old_root = Path("/synthetic/baseline") / old_revision
        new_root = Path("/synthetic/current") / new_revision
        template = "CXX_INCLUDES = -I{staging}\nLINK = -L{build}\nREVISION = {revision}\n"
        before = normalize_build(template.format(staging=old_root / "staging", build=old_root / "build", revision=old_revision).encode(),
                                 old_root / "build", old_root / "staging", old_revision)
        after = normalize_build(template.format(staging=new_root / "staging", build=new_root / "build", revision=new_revision).encode(),
                                new_root / "build", new_root / "staging", new_revision)
        self.assertEqual(before, after)
        self.assertEqual(after, b"CXX_INCLUDES = -I<STAGING>\nLINK = -L<BUILD>\nREVISION = <REVISION>\n")

    def test_real_compile_and_link_changes_are_not_normalized(self):
        old_revision, new_revision = "a" * 40, "b" * 40
        old_root = Path("/synthetic/baseline") / old_revision
        new_root = Path("/synthetic/current") / new_revision
        cases = (
            ("compile definition", b"CXX_DEFINES = -DCELESTE_ROOM_ANIMATED_PLAYER", b"CXX_DEFINES = -DCELESTE_ROOM_TEXTURED"),
            ("compile flag", b"CXX_FLAGS = -O3 -fno-fast-math", b"CXX_FLAGS = -O3 -ffast-math"),
            ("linked dependency", b"LINK = /sdk/libvitaGL.a", b"LINK = /sdk/libdifferent.a"),
            ("link option", b"LINK_FLAGS = -Wl,-q", b"LINK_FLAGS = -Wl,-r"),
        )
        for label, before, after in cases:
            with self.subTest(setting=label):
                old_data = f"-I{old_root / 'staging'} -L{old_root / 'build'}\n".encode() + before
                new_data = f"-I{new_root / 'staging'} -L{new_root / 'build'}\n".encode() + after
                with self.assertRaisesRegex(ValueError, "differs"):
                    require_equal(normalize_build(old_data, old_root / "build", old_root / "staging", old_revision),
                                  normalize_build(new_data, new_root / "build", new_root / "staging", new_revision), label)

    def test_equal_asset_bytes_are_hash_recorded(self):
        result = require_equal(b"synthetic-owned-asset", b"synthetic-owned-asset", "asset")
        self.assertEqual(result["baseline_sha256"], result["current_sha256"])
        self.assertTrue(result["equal"])

    def test_non_elf_resident_image_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "not-elf"
            path.write_bytes(b"not an executable")
            with self.assertRaisesRegex(ValueError, "ELF32"):
                resident_sections(path, "revision")


if __name__ == "__main__":
    unittest.main()
