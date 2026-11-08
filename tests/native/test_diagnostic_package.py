from contextlib import chdir
import hashlib
import json
from pathlib import Path
import struct
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / "scripts"))
from verify_native_room_vpk import verify
from native_room_replay import replay_intent


def synthetic_sfo():
    keys, values, entries = b"", b"", b""
    for key,value in {"TITLE_ID":"CELR00001","TITLE":"Celeste Native Room Diagnostic","APP_VER":"00.01"}.items():
        data = value.encode()+b"\0"
        entries += struct.pack("<HHIII",len(keys),0x204,len(data),len(data),len(values))
        keys += key.encode()+b"\0"
        values += data
    return struct.pack("<5I",0x46535000,0x101,20+len(entries),20+len(entries)+len(keys),3)+entries+keys+values


class CurrentPackageStateTests(unittest.TestCase):
    def setUp(self):
        directory = ROOT / ".audit/native-room-vita/correction-tests"
        directory.mkdir(parents=True,exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=directory)
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        self.git("init","-q")
        (self.repo / "src").mkdir()
        (self.repo / "src/input.cpp").write_text("synthetic clean source\n")
        self.git("add","src/input.cpp")
        self.git("-c","user.name=Synthetic","-c","user.email=synthetic@example.invalid","commit","-qm","Synthetic base")
        self.revision = self.git("rev-parse","HEAD").strip()
        (self.repo / ".gitignore").write_text(".audit/\n")
        self.git("add",".gitignore")
        self.git("-c","user.name=Synthetic","-c","user.email=synthetic@example.invalid","commit","-qm","Ignore private synthetic outputs")
        self.revision = self.git("rev-parse","HEAD").strip()
        self.build = self.repo / ".audit/build"
        self.staging = self.repo / ".audit/staging"
        self.build.mkdir(parents=True)
        assets = self.staging / "assets/native-room"
        assets.mkdir(parents=True)
        elf = bytearray(52)
        elf[:7] = b"\x7fELF\x01\x01\x01"
        struct.pack_into("<H",elf,18,40)
        (self.build / "celeste_native_room").write_bytes(elf)
        (self.build / "eboot.bin").write_bytes(b"SCE\0synthetic")
        files = {"global.mask":b"synthetic mask","hazards.txt":b"synthetic hazards"}
        manifest = {"revision":self.revision,"tracked_changes":False,
                    "files":{name:{"sha256":hashlib.sha256(data).hexdigest()} for name,data in files.items()}}
        for name,data in files.items():
            (assets / name).write_bytes(data)
        (assets / "provenance.json").write_text(json.dumps(manifest))
        self.vpk = self.repo / ".audit/synthetic.vpk"
        with zipfile.ZipFile(self.vpk,"w") as archive:
            archive.writestr("sce_sys/param.sfo",synthetic_sfo())
            archive.write(self.build / "eboot.bin","eboot.bin")
            for file in assets.iterdir():
                archive.write(file,"assets/native-room/"+file.name)

    def git(self,*arguments):
        return subprocess.check_output(["git","-C",str(self.repo),*arguments],text=True,stderr=subprocess.STDOUT)

    def checked_package(self):
        with chdir(self.repo), patch("verify_native_room_vpk.REPO_ROOT",self.repo,create=True):
            return verify(self.vpk,self.build,self.staging)

    def replay_package(self):
        fixture=self.repo/"src/vita/guest_replay.hpp"
        fixture.parent.mkdir()
        shutil.copyfile(ROOT/"src/vita/guest_replay.hpp",fixture)
        self.git("add",str(fixture))
        self.git("-c","user.name=Synthetic","-c","user.email=synthetic@example.invalid","commit","-qm","Add typed diagnostic fixture")
        self.revision=self.git("rev-parse","HEAD").strip()
        assets=self.staging/"assets/native-room"
        path=assets/"provenance.json"
        manifest=json.loads(path.read_text())|{"revision":self.revision,"guest_replay":replay_intent(self.repo)}
        path.write_text(json.dumps(manifest))
        elf=self.build/"celeste_native_room"
        elf.write_bytes(elf.read_bytes()+manifest["guest_replay"]["sha256"].encode())
        (self.build.parent/"CMakeCache.txt").write_text("CELESTE_ROOM_GUEST_REPLAY:BOOL=ON\n")
        with zipfile.ZipFile(self.vpk,"w") as archive:
            archive.writestr("sce_sys/param.sfo",synthetic_sfo())
            archive.write(self.build/"eboot.bin","eboot.bin")
            for file in assets.iterdir(): archive.write(file,"assets/native-room/"+file.name)

    def test_replay_package_requires_clean_revision_fixture_pin_and_explicit_build_intent(self):
        self.replay_package()
        self.assertEqual(self.checked_package()["revision"],self.revision)

    def test_replay_package_rejects_manual_build_intent(self):
        self.replay_package()
        (self.build.parent/"CMakeCache.txt").write_text("CELESTE_ROOM_GUEST_REPLAY:BOOL=OFF\n")
        with self.assertRaisesRegex(ValueError,"intent"): self.checked_package()

    def test_replay_package_rejects_elf_without_fixture_pin(self):
        self.replay_package()
        elf=self.build/"celeste_native_room"
        elf.write_bytes(elf.read_bytes()[:-64])
        with self.assertRaisesRegex(ValueError,"fixture"): self.checked_package()

    def test_clean_staging_then_current_dirty_tracked_source_is_rejected(self):
        self.checked_package()
        (self.repo / "src/input.cpp").write_text("edited after clean staging\n")
        elf = self.build / "celeste_native_room"
        elf.write_bytes(elf.read_bytes()+b"synthetic rebuilt source at unchanged HEAD")
        self.assertEqual(self.git("rev-parse","HEAD").strip(),self.revision)
        with self.assertRaisesRegex(ValueError,"Current source/config"):
            self.checked_package()

    def test_clean_package_check_is_independent_of_working_directory(self):
        with chdir(ROOT), patch("verify_native_room_vpk.REPO_ROOT",self.repo,create=True):
            self.assertEqual(verify(self.vpk,self.build,self.staging)["revision"],self.revision)

    def test_current_untracked_source_is_rejected(self):
        (self.repo / "src/untracked.cpp").write_text("synthetic\n")
        with self.assertRaisesRegex(ValueError,"Current source/config"):
            self.checked_package()

    def test_only_exact_untracked_coordination_paths_are_exempt(self):
        for name in (".opencode/orchestrator.md",".opencode/memory/memory.db",".opencode/memory/memory.db-shm",".opencode/memory/memory.db-wal"):
            path = self.repo / name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text("synthetic coordination\n")
        self.checked_package()
        (self.repo / ".opencode/memory/memory.db.extra").write_text("not exempt\n")
        with self.assertRaisesRegex(ValueError,"Current source/config"):
            self.checked_package()
