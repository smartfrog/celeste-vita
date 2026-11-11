import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import native_room_revision as revision
import stage_native_room as staging
import verify_native_room_vpk as package_verifier
from test_diagnostic_package import synthetic_sfo


def resident_elf(payload):
    image = bytearray(84)
    image[:7] = b"\x7fELF\x01\x01\x01"
    struct.pack_into("<HH", image, 16, 2, 40)
    struct.pack_into("<I", image, 28, 52)
    struct.pack_into("<HH", image, 42, 32, 1)
    struct.pack_into("<8I", image, 52, 1, 84, 0, 0, len(payload), len(payload), 4, 4)
    return bytes(image) + payload


class BuildBindingTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / ".audit/native-player-death-respawn/artifact-tests"
        parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.build = self.root / "build"
        self.staging = self.root / "staging"
        self.sdk = self.root / "sdk"
        self.expected = {"schema": 1, "base_head": "a"*40, "changes": [" M native.cpp"],
                         "paths": {"native.cpp": {"sha256": "b"*64, "bytes": 1, "mode": 420}},
                         "sha256": "c"*64, "count": 1, "bytes": 1}
        self.expected_path = self.root / "expected.json"
        self.expected_path.write_text(json.dumps(self.expected))

    def configure(self):
        import native_room_build as binding
        self.binding = binding
        self.addCleanup(patch.stopall)
        patch.object(binding, "REPO_ROOT", self.root).start()
        patch.object(binding, "validate_source_state", side_effect=lambda expected=None, root=None: self.expected).start()
        assets = self.staging / "assets/native-room"
        assets.mkdir(parents=True)
        for name in ("global.mask", "hazards.txt"):
            (assets / name).write_bytes(b"synthetic " + name.encode())
        self.manifest = {"revision": self.expected["base_head"], "tracked_changes": True, "guest_replay": None,
                         "files": {p.name: revision.file_identity(p) | {"fnv1a32": staging.checksum(p.read_bytes())} for p in assets.iterdir()},
                         "prepared_inputs": {}, "render_style": "debug"}
        self.write_staging()
        self.build.mkdir()
        for name in ("vita.toolchain.cmake", "vita.cmake"):
            path = self.sdk / "share" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic toolchain")
        for name in ("arm-vita-eabi-g++", "arm-vita-eabi-ld", "vita-elf-create", "vita-make-fself"):
            path = self.sdk / "bin" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(name.encode())
        library = self.root / "libvitaGL.a"
        library.write_bytes(b"synthetic static library")
        cache = {"CMAKE_HOME_DIRECTORY": self.root, "CMAKE_GENERATOR": "Unix Makefiles", "CELESTE_ROOM_STAGING": self.staging,
                 "CELESTE_EXPECTED_SOURCE_STATE": self.expected_path, "CMAKE_TOOLCHAIN_FILE": self.sdk / "share/vita.toolchain.cmake",
                 "CMAKE_CXX_COMPILER": self.sdk / "bin/arm-vita-eabi-g++", "CMAKE_LINKER": self.sdk / "bin/arm-vita-eabi-ld",
                 "CELESTE_VITAGL_LIBRARY": library}
        (self.build / "CMakeCache.txt").write_text("".join(f"{k}:STRING={v}\n" for k,v in cache.items()) + "CELESTE_ROOM_GUEST_REPLAY:BOOL=OFF\nCELESTE_ROOM_GUEST_AUTOMATIC:BOOL=OFF\n")
        for target in ("celeste_native_kernel", "celeste_room_diagnostic", "celeste_native_room"):
            folder = self.build / ("src/vita" if target == "celeste_native_room" else "") / "CMakeFiles" / (target + ".dir")
            folder.mkdir(parents=True)
            (folder / "flags.make").write_text("CXX_FLAGS = -O3 -fno-fast-math\n")
            (folder / "link.txt").write_text(f"{self.sdk}/bin/arm-vita-eabi-g++ {library}\n")
        image = self.build / "src/vita"
        for target, command in (("celeste_native_room-velf", f"{self.sdk}/bin/vita-elf-create {image}/celeste_native_room {image}/celeste_native_room.velf"),
                                ("eboot.bin-self", f"{self.sdk}/bin/vita-make-fself -c -s {image}/celeste_native_room.velf {image}/eboot.bin.out")):
            folder = image / "CMakeFiles" / (target + ".dir")
            folder.mkdir()
            (folder / "build.make").write_text(f"\tcd {image} && {command}\n")

    def write_staging(self):
        self.manifest["binding"] = revision.staging_binding(self.manifest, self.expected)
        path = self.staging / "assets/native-room/provenance.json"
        path.write_text(json.dumps(self.manifest))
        (self.staging / "asset_pins.hpp").write_text(staging.asset_pins_text(self.manifest))

    def produce(self):
        record = self.binding.prepare(self.build, self.staging, self.expected)
        payload = b"code\0" + record["token"].encode() + b"\0"
        if self.manifest.get("guest_automatic"):
            payload += self.manifest["guest_automatic_fixture"]["sha256"].encode() + b"\0"
        if self.manifest.get("guest_dash_probe"):
            payload += self.manifest["guest_dash_probe_fixture"]["sha256"].encode() + b"\0"
        image = self.build / "src/vita"
        elf = resident_elf(payload)
        (image / "celeste_native_room").write_bytes(elf)
        (image / "celeste_native_room.velf").write_bytes(b"velf:" + elf)
        (image / "eboot.bin").write_bytes(b"SCE\0" + hashlib.sha256(b"velf:" + elf).digest())
        return record

    def fake_tool(self, command, **kwargs):
        if Path(command[0]).name == "vita-elf-create":
            Path(command[-1]).write_bytes(b"velf:" + Path(command[-2]).read_bytes())
        else:
            Path(command[-1]).write_bytes(b"SCE\0" + hashlib.sha256(Path(command[-2]).read_bytes()).digest())

    def check(self):
        with patch.object(self.binding.subprocess, "run", side_effect=self.fake_tool):
            return self.binding.verify_build(self.build, self.staging, self.expected)

    def package(self, eboot=None):
        path = self.root / "synthetic.vpk"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("sce_sys/param.sfo", synthetic_sfo())
            archive.writestr("eboot.bin", eboot if eboot is not None else (self.build / "src/vita/eboot.bin").read_bytes())
            for name in (*self.manifest["files"], "provenance.json"):
                archive.writestr("assets/native-room/" + name, (self.staging / "assets/native-room" / name).read_bytes())
        return path

    def check_package(self, path):
        with patch.object(package_verifier, "REPO_ROOT", self.root), \
             patch.object(package_verifier, "validate_source_state", side_effect=lambda expected=None, root=None: self.expected), \
             patch.object(self.binding.subprocess, "run", side_effect=self.fake_tool):
            return package_verifier.verify(path, self.build / "src/vita", self.staging, self.expected)

    def test_exact_wip_package_is_verified_end_to_end(self):
        self.configure()
        self.produce()
        self.assertTrue(self.check_package(self.package())["exact_wip"])

    def enable_automatic(self):
        from native_room_automatic import automatic_intent
        header = self.root / "src/vita/guest_automatic_replay.hpp"
        header.parent.mkdir(parents=True)
        header.write_text("synthetic automatic raw input fixture")
        self.manifest.update(guest_automatic="first_room_auto_death_v2", guest_automatic_fixture=automatic_intent(self.root))
        self.write_staging()
        cache = self.build / "CMakeCache.txt"
        cache.write_text(cache.read_text().replace("CELESTE_ROOM_GUEST_AUTOMATIC:BOOL=OFF", "CELESTE_ROOM_GUEST_AUTOMATIC:BOOL=ON") +
                         "CELESTE_ROOM_ANIMATED_PLAYER:BOOL=ON\n")
        flags = self.build / "src/vita/CMakeFiles/celeste_native_room.dir/flags.make"
        flags.write_text(flags.read_text() + "CXX_DEFINES = -DCELESTE_ROOM_GUEST_AUTOMATIC -DCELESTE_ROOM_ANIMATED_PLAYER\n")

    def test_automatic_exact_wip_package_is_verified(self):
        self.configure()
        self.enable_automatic()
        self.produce()
        self.assertEqual(self.check_package(self.package())["staging"]["guest_automatic"], "first_room_auto_death_v2")

    def enable_probe(self):
        from native_room_dash_probe import dash_probe_intent
        header = self.root / "src/vita/guest_dash_probe.hpp"
        header.parent.mkdir(parents=True)
        header.write_text("synthetic probe raw input fixture")
        self.manifest.update(guest_dash_probe="first_room_dash_trails_v1", guest_dash_probe_fixture=dash_probe_intent(self.root),
                             render_style="animated_player_partial", player={"pages": 1, "bank_sha256": "0"*64})
        assets = self.staging / "assets/native-room"
        for name in ("player.txt", "player0.rgba", "visuals.txt", *(f"texture{i}.rgba" for i in range(6))):
            path = assets / name
            path.write_bytes(b"synthetic probe " + name.encode())
            self.manifest["files"][name] = revision.file_identity(path) | {"fnv1a32": staging.checksum(path.read_bytes())}
        self.write_staging()
        cache = self.build / "CMakeCache.txt"
        cache.write_text(cache.read_text() + "CELESTE_ROOM_DASH_PROBE:BOOL=ON\nCELESTE_ROOM_ANIMATED_PLAYER:BOOL=ON\n")
        flags = self.build / "src/vita/CMakeFiles/celeste_native_room.dir/flags.make"
        flags.write_text(flags.read_text() + "CXX_DEFINES = -DCELESTE_ROOM_DASH_PROBE -DCELESTE_ROOM_ANIMATED_PLAYER\n")

    def test_probe_exact_wip_binding_and_package(self):
        self.configure()
        self.enable_probe()
        record = self.produce()
        self.assertEqual(record["context"]["capture_policy"], "dash_trails")
        self.assertEqual(self.check_package(self.package())["staging"]["guest_dash_probe"], "first_room_dash_trails_v1")

    def test_probe_build_rejects_production_staging(self):
        self.configure()
        self.enable_probe()
        self.manifest.pop("guest_dash_probe")
        self.manifest.pop("guest_dash_probe_fixture")
        self.write_staging()
        with self.assertRaisesRegex(ValueError, "probe intent"):
            self.binding.prepare(self.build, self.staging, self.expected)

    def test_production_build_rejects_probe_staging(self):
        self.configure()
        self.enable_probe()
        path = self.build / "CMakeCache.txt"
        path.write_text(path.read_text().replace("CELESTE_ROOM_DASH_PROBE:BOOL=ON", "CELESTE_ROOM_DASH_PROBE:BOOL=OFF"))
        with self.assertRaisesRegex(ValueError, "probe intent"):
            self.binding.prepare(self.build, self.staging, self.expected)

    def test_probe_staged_hash_tampering_is_rejected(self):
        self.configure()
        self.enable_probe()
        self.manifest["guest_dash_probe_fixture"]["sha256"] = "0"*64
        self.write_staging()
        with self.assertRaisesRegex(ValueError, "fixture identity"):
            self.binding.prepare(self.build, self.staging, self.expected)

    def test_probe_source_header_tampering_is_rejected(self):
        self.configure()
        self.enable_probe()
        (self.root / "src/vita/guest_dash_probe.hpp").write_text("changed synthetic input fixture")
        with self.assertRaisesRegex(ValueError, "fixture identity"):
            self.binding.prepare(self.build, self.staging, self.expected)

    def test_probe_elf_requires_its_fixture_hash(self):
        self.configure()
        self.enable_probe()
        self.produce()
        image = self.build / "src/vita"
        elf = (image / "celeste_native_room").read_bytes().replace(self.manifest["guest_dash_probe_fixture"]["sha256"].encode(), b"0"*64)
        (image / "celeste_native_room").write_bytes(elf)
        velf = b"velf:" + elf
        (image / "celeste_native_room.velf").write_bytes(velf)
        (image / "eboot.bin").write_bytes(b"SCE\0" + hashlib.sha256(velf).digest())
        with self.assertRaisesRegex(ValueError, "probe ELF.*fixture"):
            self.check_package(self.package())

    def test_automatic_binding_records_initial_respawn_capture_policy(self):
        self.configure()
        self.enable_automatic()
        record = self.produce()
        self.assertEqual(record["context"]["capture_policy"], "initial_respawn")

    def test_stale_frame_zero_binary_cannot_be_rebound_to_initial_respawn(self):
        self.configure()
        self.enable_automatic()
        record = self.produce()
        old_context = record["context"] | {"capture_policy": "spawn"}
        old_token = "CELESTE_NATIVE_BINDING_V1:" + revision.canonical_digest(old_context)
        path = self.build / "src/vita/celeste_native_room"
        path.write_bytes(path.read_bytes().replace(record["token"].encode(), old_token.encode()))
        with self.assertRaisesRegex(ValueError, "resident.*binding"):
            self.check()

    def test_capture_override_definition_must_match_its_cache_pin(self):
        self.configure()
        self.enable_automatic()
        cache = self.build / "CMakeCache.txt"
        cache.write_text(cache.read_text() + "CELESTE_ROOM_CAPTURE_AFTER_CLIMB:BOOL=ON\n")
        with self.assertRaisesRegex(ValueError, "capture.*definition"):
            self.binding.prepare(self.build, self.staging, self.expected)

    def test_capture_policy_tracks_profile_and_explicit_overrides_parameterized(self):
        from native_room_build import build_capture_policy
        for names, expected in [([], "spawn"), (["ANIMATED_PLAYER"], "initial_respawn"),
                                (["ANIMATED_PLAYER", "GUEST_REPLAY"], "spawn"),
                                (["CAPTURE_AFTER_WALL_JUMP"], "wall_jump"), (["CAPTURE_AFTER_CLIMB"], "climb"),
                                (["ANIMATED_PLAYER", "CAPTURE_AFTER_WALL_JUMP"], "wall_jump"),
                                (["ANIMATED_PLAYER", "GUEST_REPLAY", "CAPTURE_AFTER_CLIMB"], "climb")]:
            with self.subTest(names=names):
                cache = {"CELESTE_ROOM_" + name: "ON" for name in names}
                defines = ["-DCELESTE_ROOM_" + name for name in names]
                self.assertEqual(build_capture_policy(cache, defines), expected)

    def test_dual_capture_override_is_rejected(self):
        from native_room_build import build_capture_policy
        cache = {"CELESTE_ROOM_CAPTURE_AFTER_WALL_JUMP": "ON", "CELESTE_ROOM_CAPTURE_AFTER_CLIMB": "ON"}
        with self.assertRaisesRegex(ValueError, "mutually exclusive"):
            build_capture_policy(cache, ["-D" + name for name in cache])

    def test_automatic_provenance_cannot_label_a_production_build(self):
        self.configure()
        self.enable_automatic()
        cache = self.build / "CMakeCache.txt"
        cache.write_text(cache.read_text().replace("CELESTE_ROOM_GUEST_AUTOMATIC:BOOL=ON", "CELESTE_ROOM_GUEST_AUTOMATIC:BOOL=OFF"))
        with self.assertRaisesRegex(ValueError, "automatic.*mode|automatic.*intent"):
            self.binding.prepare(self.build, self.staging, self.expected)

    def test_automatic_build_cannot_label_production_provenance(self):
        self.configure()
        self.enable_automatic()
        self.manifest["guest_automatic"] = None
        self.manifest["guest_automatic_fixture"] = None
        self.write_staging()
        with self.assertRaisesRegex(ValueError, "automatic.*mode|automatic.*intent"):
            self.binding.prepare(self.build, self.staging, self.expected)

    def test_cache_automatic_mode_requires_its_actual_compile_definition(self):
        self.configure()
        self.enable_automatic()
        flags = self.build / "src/vita/CMakeFiles/celeste_native_room.dir/flags.make"
        flags.write_text(flags.read_text().replace("-DCELESTE_ROOM_GUEST_AUTOMATIC", ""))
        with self.assertRaisesRegex(ValueError, "automatic.*definition"):
            self.binding.prepare(self.build, self.staging, self.expected)

    def test_stale_production_binary_cannot_be_rebound_as_automatic(self):
        self.configure()
        self.produce()
        self.enable_automatic()
        record = self.binding.build_context(self.build, self.staging, self.expected, True)
        (self.build / "src/vita/native-build-binding.json").write_text(json.dumps(record))
        (self.build / "src/vita/native-build-binding.cpp").write_text(self.binding.binding_source(record["token"]))
        with self.assertRaisesRegex(ValueError, "resident.*binding"):
            self.check()

    def test_stale_automatic_binary_cannot_be_rebound_as_production(self):
        self.configure()
        self.enable_automatic()
        self.produce()
        self.manifest.update(guest_automatic=None, guest_automatic_fixture=None)
        self.write_staging()
        cache = self.build / "CMakeCache.txt"
        cache.write_text(cache.read_text().replace("CELESTE_ROOM_GUEST_AUTOMATIC:BOOL=ON", "CELESTE_ROOM_GUEST_AUTOMATIC:BOOL=OFF"))
        flags = self.build / "src/vita/CMakeFiles/celeste_native_room.dir/flags.make"
        flags.write_text(flags.read_text().replace("-DCELESTE_ROOM_GUEST_AUTOMATIC", ""))
        record = self.binding.build_context(self.build, self.staging, self.expected, True)
        (self.build / "src/vita/native-build-binding.json").write_text(json.dumps(record))
        (self.build / "src/vita/native-build-binding.cpp").write_text(self.binding.binding_source(record["token"]))
        with self.assertRaisesRegex(ValueError, "resident.*binding"):
            self.check()

    def test_automatic_elf_requires_its_fixture_header_hash(self):
        self.configure()
        self.enable_automatic()
        self.produce()
        image = self.build / "src/vita"
        elf = (image / "celeste_native_room").read_bytes().replace(self.manifest["guest_automatic_fixture"]["sha256"].encode(), b"0"*64)
        (image / "celeste_native_room").write_bytes(elf)
        velf = b"velf:" + elf
        (image / "celeste_native_room.velf").write_bytes(velf)
        (image / "eboot.bin").write_bytes(b"SCE\0" + hashlib.sha256(velf).digest())
        with self.assertRaisesRegex(ValueError, "automatic ELF.*fixture"):
            self.check_package(self.package())

    def test_dirty_default_remains_rejected_without_opt_in(self):
        self.configure()
        self.produce()
        with patch.object(package_verifier, "REPO_ROOT", self.root), \
             patch.object(package_verifier, "source_state", return_value=(self.expected["base_head"], self.expected["changes"])):
            with self.assertRaisesRegex(ValueError, "not clean"):
                package_verifier.verify(self.package(), self.build / "src/vita", self.staging)

    def test_altered_packaged_binary_is_rejected(self):
        self.configure()
        self.produce()
        with self.assertRaisesRegex(ValueError, "Packaged SELF"):
            self.check_package(self.package(b"SCE\0altered package"))

    def test_exact_build_and_self_chain_are_bound(self):
        self.configure()
        self.produce()
        self.assertTrue(self.check()["self_matches_rebuilt_chain"])

    def test_same_head_different_wip_binary_is_rejected_even_after_rebinding_receipts(self):
        self.configure()
        self.produce()
        self.expected["paths"]["native.cpp"]["sha256"] = "d"*64
        self.expected_path.write_text(json.dumps(self.expected))
        self.write_staging()
        with self.assertRaisesRegex(ValueError, "fresh build"):
            self.binding.prepare(self.build, self.staging, self.expected)
        record = self.binding.build_context(self.build, self.staging, self.expected, True)
        (self.build / "src/vita/native-build-binding.json").write_text(json.dumps(record))
        (self.build / "src/vita/native-build-binding.cpp").write_text(self.binding.binding_source(record["token"]))
        with self.assertRaisesRegex(ValueError, "resident.*binding"):
            self.check()

    def test_unbound_existing_build_cannot_be_relabelled(self):
        self.configure()
        (self.build / "src/vita/celeste_native_room").write_bytes(resident_elf(b"old binary"))
        with self.assertRaisesRegex(ValueError, "fresh build"):
            self.binding.prepare(self.build, self.staging, self.expected)

    def test_unbound_existing_object_cannot_be_reused(self):
        self.configure()
        (self.build / "CMakeFiles/celeste_native_kernel.dir/old.cpp.obj").write_bytes(b"old compiled code")
        with self.assertRaisesRegex(ValueError, "fresh build"):
            self.binding.prepare(self.build, self.staging, self.expected)

    def test_modified_elf_code_is_rejected_by_the_self_chain(self):
        self.configure()
        self.produce()
        path = self.build / "src/vita/celeste_native_room"
        path.write_bytes(path.read_bytes().replace(b"code\0", b"evil\0"))
        with self.assertRaisesRegex(ValueError, "VELF"):
            self.check()

    def test_modified_self_is_rejected(self):
        self.configure()
        self.produce()
        (self.build / "src/vita/eboot.bin").write_bytes(b"SCE\0different binary")
        with self.assertRaisesRegex(ValueError, "SELF"):
            self.check()

    def test_changed_asset_pins_are_rejected(self):
        self.configure()
        self.produce()
        (self.staging / "asset_pins.hpp").write_text("edited pins")
        with self.assertRaisesRegex(ValueError, "pins"):
            self.check()

    def test_changed_payload_is_rejected(self):
        self.configure()
        self.produce()
        (self.staging / "assets/native-room/global.mask").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "payload"):
            self.check()

    def test_edited_build_receipt_is_not_trusted(self):
        self.configure()
        self.produce()
        path = self.build / "src/vita/native-build-binding.json"
        record = json.loads(path.read_text())
        record["token"] = "manually changed"
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, "binding record"):
            self.check()

    def test_library_drift_is_rejected_without_trusting_old_receipts(self):
        self.configure()
        self.produce()
        (self.root / "libvitaGL.a").write_bytes(b"changed dependency")
        with self.assertRaisesRegex(ValueError, "binding record"):
            self.check()

    def test_sdk_tool_drift_is_rejected(self):
        self.configure()
        self.produce()
        (self.sdk / "bin/vita-make-fself").write_bytes(b"changed SDK tool")
        with self.assertRaisesRegex(ValueError, "binding record"):
            self.check()

    def test_build_flag_drift_is_rejected(self):
        self.configure()
        self.produce()
        (self.build / "src/vita/CMakeFiles/celeste_native_room.dir/flags.make").write_text("CXX_FLAGS = -Ofast\n")
        with self.assertRaisesRegex(ValueError, "binding record"):
            self.check()

    def test_changed_prepared_evidence_is_rejected(self):
        self.configure()
        evidence = self.root / "bank.json"
        evidence.write_bytes(b"original bank evidence")
        self.manifest["prepared_inputs"][str(evidence)] = revision.file_identity(evidence)
        self.write_staging()
        self.produce()
        evidence.write_bytes(b"changed evidence")
        with self.assertRaisesRegex(ValueError, "Pinned input"):
            self.check()

    def test_edited_staging_provenance_is_rejected(self):
        self.configure()
        self.produce()
        self.manifest["prepared_inputs"] = {"removed-input": {"bytes": 0, "sha256": "0"*64}}
        (self.staging / "assets/native-room/provenance.json").write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError, "Staging binding"):
            self.check()

    def test_unknown_staged_file_is_rejected(self):
        self.configure()
        self.produce()
        (self.staging / "assets/native-room/bank.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "inventory"):
            self.check()

    def test_binding_appended_outside_loadable_elf_is_rejected(self):
        self.configure()
        record = self.produce()
        path = self.build / "src/vita/celeste_native_room"
        path.write_bytes(resident_elf(b"unbound old code") + record["token"].encode())
        with self.assertRaisesRegex(ValueError, "resident.*binding"):
            self.check()


if __name__ == "__main__":
    unittest.main()
