# Native Vita room diagnostic

This is our own C++ executable/VPK, not the original game. It composes the
accepted [Normal Player](NATIVE_PLAYER.md), [full merged solidmask](NATIVE_TILEMAP.md)
and [five static Up/Left spikes](NATIVE_HAZARDS.md) for explicitly selected room
`1`. Debug rectangles are **not faithful graphics**. Audio, original respawn,
corpse/freeze/reload lifecycle, other Player states, room transitions and full
gameplay remain excluded. It is not a completed playable port or a hardware
performance result.

## Controls and clock

- DPad: movement/vertical input; opposing directions on either axis resolve to
  neutral (diagnostic policy, not source hardware-input parity).
- Cross: sampled held/rising-edge input to the existing Player VirtualButton.
  Releasing clears held; a subsequent press produces a new edge.
- Triangle rising edge: **manual diagnostic reset**, constructing a fresh Player
  at `(19,144)`. It skips simulation on that reset sample, works alive or dead,
  and is not source respawn. Dead Players are never updated.
- Start: clean guest exit, taking precedence over reset and movement.

One controller sample drives at most one fixed `1/60` core frame. No wall-clock
catch-up, source Engine freeze/timing parity or lifecycle rendering is claimed.
`vglWaitVblankStart(GL_TRUE)` enables vsync once; frames use
`vglSwapBuffers(GL_FALSE)`. Any observed FPS is an emulator diagnostic measurement.

The full black 960×544 buffer is cleared before setting viewport `(0,2,960,540)`:
integer 3× logical 320×180, with two black pixels above/below. Blue-gray quads
are the actual merged occupied cells intersecting the viewport (363); red quads
are the actual spike colliders, not solid tiles. Player movement box is green
(red when dead), overlaid by the smaller yellow hurtbox. Geometry/world/spikes
outlive Player and remain static. There are no textures, fonts or audio.

## Private assets and package

Nothing from the private map/source/SDK, nor binaries/VPKs, is committed.
`stage_native_room.py` reuses existing offline preparation functions, verifies
prepared SHA256 provenance and the pinned executable/map archive hashes, and
reconstructs the full merged mask/hazard list to reject stale or isolated data.
It stages `global.mask`, canonical `hazards.txt` and `provenance.json` beneath
`app0:assets/native-room/`, plus an executable-only checksum/revision header.

The pure native parsers validate CSTM1/CSH1 versions, fixed executable/map hash
metadata, canonical integers/serialization, dimensions/edges, bounded lengths,
cell values, supported directions and sizes. Runtime uses build-pinned FNV-1a32
over each entire asset: **accidental corruption detection, not cryptographic
authentication**. SHA256 is verified at staging/package inspection. Missing,
truncated, altered or wrong-metadata assets fail before the first game frame.
Limits: 4,000,000 mask cells, 64 spikes, spike coordinates ±1,000,000 and size
1–1,000,000. The app additionally requires the actual 541×440 mask at
`(-64,-3272)`, 26,915 occupied cells, 363 visible cells and five spikes.

Build from the repository root using the existing SDK/archive (do not rebuild
the shared library or use the normal SDK splash archive):

```sh
export VITASDK=/home/fred/cloudpunk-vita/tools/vitasdk
export PATH="$VITASDK/bin:$PATH"
python3 -B scripts/prepare_static_tilemap.py
python3 -B scripts/prepare_room_hazards.py
python3 -B scripts/stage_native_room.py
/usr/bin/cmake -S . -B .audit/native-room-vita/vita \
  -DCMAKE_TOOLCHAIN_FILE="$VITASDK/share/vita.toolchain.cmake" \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DCELESTE_VITA=ON \
  -DCELESTE_VITAGL_LIBRARY=/home/fred/cloudpunk-vita/tools/vita3k/vitagl-source/libvitaGL.a \
  -DCELESTE_ROOM_STAGING="$PWD/.audit/native-room-vita/staging"
/usr/bin/cmake --build .audit/native-room-vita/vita -j2
python3 -B scripts/verify_native_room_vpk.py \
  --vpk .audit/native-room-vita/vita/src/vita/celeste_native_room.vpk \
  --build .audit/native-room-vita/vita/src/vita \
  --staging .audit/native-room-vita/staging
```

Staging stamps dirty/untracked source explicitly. Package verification requires
the exact clean commit. Root `CELESTE_VITA` defaults OFF; host tests need no SDK.
`vita-elf-create`, `vita-make-fself`, `vita-mksfoex` and `vita-pack-vpk` are invoked
by the installed VitaSDK CMake macros. Unique title ID: `CELR00001`, version 00.01.
The <2 MiB package size is a goal, not a performance claim.

vitaGL is the existing no-splash archive at revision
`cd3791e29ff7f1c0ab349f12c7231f4871ce6a75`; initialization checks its actual
fallback flag, context, pools and viewport. Stubs/immediate quads follow the
working cloudpunk Vita build/overlay. Context7 had no indexed vitaGL/VitaSDK
API documentation; installed pinned headers/source and working code supplied
the signatures. The pinned library has no real context teardown API
(`eglTerminate` is a no-op); the app drains GPU work with `glFinish`, checks GL
errors, destroys its own objects/closes files and exits the process. Library
global allocations are reclaimed at process exit, not a fabricated teardown.

## Safe Vita3K smoke

Read `/home/fred/cloudpunk-vita/docs/VITA3K.md` first. The supplied launcher does
**not** run the cloudpunk launcher or modify its config, titles, logs or archive.
It reuses that existing emulator binary/Qt libraries. Writable XDG config/data/
cache/temp/preferences and this title live only beneath our chosen state.
Firmware/fonts/shader compiler are symlinked for reading, not copied wholesale.
Bubblewrap mounts the host read-only, with only our state writable, protecting
the symlink targets and all shared titles (`CPVH00001`, `CPVR00001`, others).
Only the minimal user profile is copied; no saves/titles/shared caches are cloned.
No firmware download, library rebuild or original game execution occurs.

```sh
python3 -B scripts/smoke_native_room.py \
  --state .audit/native-room-vita/vita3k-state/unique-run \
  --output .audit/native-room-vita/unique-run \
  --vpk .audit/native-room-vita/vita/src/vita/celeste_native_room.vpk
```

Use a **fresh** state per installation; scripts refuse to overwrite a title or
use an ambiguous existing diagnostic window. The small focused helper installs
the VPK through the emulator first, verifies every installed entry, stops only
that owned installer, then explicitly launches `-r CELR00001` (the pinned build's
positional-VPK auto-boot did not start a game). It uses `--` before the positional
absolute VPK path and the XDG config directory for `-c`. Bubblewrap's
`--die-with-parent` prevents orphaned child emulator processes during cleanup.
The focused helper inventories
existing X11 windows, finds our unique title plus actual OpenGL game-window
title, validates its PID's isolated-config argument, and requires both
`_NET_ACTIVE_WINDOW` and `XGetInputFocus` before XTest input. Physical X11 keycodes
for this host's AZERTY layout: Right 114, Cross 53, Triangle 55, Start 36.
It releases only keys it injected, never drives/closes unrelated windows, and
only terminates its own spawned process. Missing isolation/focus/rendering is a
runtime failure, not permission to bypass protections.

X11/inotify/select events and bounded deadlines coordinate nonvisual input, not
sleep/process polling or polling a buffered guest log. Small explicitly labeled
guest `.ready` signals acknowledge sampled input/death/reset for coordination
only. Final evidence is the **completed** guest log after Start, not readiness
signals. The stdio `fopen`-before-redirect ordering avoids the documented SDK
pitfall. Logs include revision, counts, input edges, bounded-frequency state,
actual death, manual reset counter, clean exit and measured elapsed time.
Linux screenshot commands/APIs are not used: visual verification requires the
user-requested built-in screen-view tool. If that tool is unavailable, visual
verification is explicitly blocked, not inferred from window titles/logs.
The visual step is deferred to the parent; this smoke harness has no capture path.
Preserve guest/host logs and state; distinguish guest clean exit from an emulator
shutdown fault. Historical exploratory captures created before that constraint
are retained privately, not a substitute for a new built-in visual check.

Host tests cover pure parsers/corruption, input edges/opposing axes, fresh reset,
exit precedence and fixed clock/viewport. `native_diagnostic_replay` with the
staged mask/hazards first jumps at spawn, then walks right, reaching actual spike
death without teleporting or calling `die`. Full host/source/static Vita checks
and exact-commit runtime evidence are recorded privately in
`.audit/native-room-vita/finalchecks.json`. Runtime/hardware success must never
be inferred from package construction alone; physical Vita remains untested.
