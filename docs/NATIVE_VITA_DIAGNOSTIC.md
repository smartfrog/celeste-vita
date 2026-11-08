# Native Vita room diagnostic

This is our own C++ executable/VPK, not the original game. It composes the
accepted [Normal Player](NATIVE_PLAYER.md), [bounded Dash](NATIVE_DASH.md), [full merged solidmask](NATIVE_TILEMAP.md)
and [five static Up/Left spikes](NATIVE_HAZARDS.md) for explicitly selected room
`1`. Debug rectangles are **not faithful graphics**. Audio, original respawn,
corpse/reload lifecycle, other Player states, room transitions and full
gameplay remain excluded. It is not a completed playable port or a hardware
performance result.

## Controls and clock

- DPad: movement/vertical input; opposing directions on either axis resolve to
  neutral (diagnostic policy, not source hardware-input parity).
- Cross: sampled held/rising-edge input to the existing Player VirtualButton.
  Releasing clears held; a subsequent press produces a new edge.
- Square: sampled Dash VirtualButton; DPad also supplies resolved independent
  digital aim. Cross/Jump, Triangle/manual reset and Start/exit remain separate.
- Triangle rising edge: **manual diagnostic reset**, constructing a fresh Player
  at `(19,144)`. It skips simulation on that reset sample, works alive or dead,
  and is not source respawn. Dead Players are never updated.
- Start: clean guest exit, taking precedence over reset and movement.

One controller sample drives at most one fixed `1/60` raw-float core frame.
Both buffered buttons update during the bounded Dash freeze; its crossing tick
still skips simulation. No wall-clock catch-up, full Engine/GameTime conversion
parity or lifecycle rendering is claimed.
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

Staging and package verification share the same canonical-root current Git-state
reader. Staging stamps dirty/untracked source explicitly; verification also rejects
current source/config changes, even when HEAD and an older clean manifest match.
Only the four exact untracked `.opencode` coordination paths are exempt.
Root `CELESTE_VITA` defaults OFF; host tests need no SDK.
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

### One-command native-renderer feedback loop

From a clean delivery commit, run once with a fresh output directory:

```sh
python3 -B scripts/feedback_native_room.py \
  --output .audit/native-room-vita/feedback-unique-run
```

For the [jump-family](NATIVE_WALL_JUMPS.md) checkpoint, add `--after-wall-jump`.
It exports once after an actual input-driven WallJump instead of frame zero,
logs the launch and following forced-right movement, then manually resets before
the retained Jump/Dash/death/reset/exit smoke. Startup readiness is independent
of image completion. `--frame-only` is incompatible with this input-driven mode.
The receipt records actual frame/state/jump kind; feedback joins the VPK hash.

This stages verified private assets, builds the exact revision/VPK with the
existing no-splash archive, verifies the current-clean package, installs/runs it
in isolated Vita3K state, and preserves `feedback.json`. The app exports **one
frame from its own native render buffer**, not a desktop/window screenshot.
The structured report is updated as soon as the closed image is available,
before input testing; image/startup/input/clean-exit/full-completion flags are
separate. A later input failure returns nonzero while preserving the frame,
logs, state, exact revision/VPK hash and concrete error. No required image stage
is replaced by a `ready frame=0` marker.
Build/non-input subprocesses keep a 600-second timeout. Runtime has no outer
force-kill timeout: the smoke helper's bounded phases must unwind its owned-key
cleanup before stopping its owned emulator. A failed final Git/source check is
recorded before saving/raising and clears overall `full_completion`, while
retaining completed guest-stage flags and artifacts.
For the first-image checkpoint, add `--frame-only`: no keys are injected, only
the owned emulator is stopped after the closed frame, and input/clean-exit/full
completion remain false pending parent inspection. The frozen effective private
`runtime/effective-config.yml`, its before/after hashes and exact launch command
are retained in feedback/evidence.

The first draw reads full 960×544 `GL_BACK`, after `glFinish` and before swap,
using safe CPU `glReadPixels(..., GL_RGBA, GL_UNSIGNED_BYTE, vector.data())`, then
checks GL errors. The writable vector is 2,088,960 bytes; pinned vitaGL
`framebuffers.c` 657–678 and 749–767 select the back buffer and copy bottom-up
RGBA with pitch 3840, bypassing GPU transfer/conversion.

Only the fresh private emulator config forces `backend-renderer: OpenGL`,
`resolution-multiplier: 1`, and `disable-surface-sync: false`. In the inspected
local Vita3K source, `renderer/src/scene.cpp` 124–174 skips GPU-to-guest copying
when surface sync is disabled; `modules/SceGxm/SceGxm.cpp` 2620–2634 queues that
copy at EndScene. This explains the earlier CPU export's zero data with the
inherited disabled-sync config; `glFinish` cannot restore a skipped copy.
The GPU-transfer experiments are not used: RGB conversion was unsupported and
the mapped RGBA attempt crashed the host. The exact mapped-transfer crash cause
is unestablished. All failed artifacts/logs remain preserved.
`glReadBuffer` is implemented at 957–974; `gxm.c` 962–969 finishes GPU
work and 928–929 advances the buffer indices only during swap. The display
surface is A8B8G8R8; width 960 is 64-pixel aligned. The tested encoder reverses
RGBA rows and strips alpha into top-down P6 RGB, including
the black letterbox rows. SDK `SCE_O_EXCL` preserves existing guest outputs.

Guest files are `ux0:data/celeste_native_room-<revision>.ppm` and a closed `.ppm.txt`
completion receipt with `frame_saved`, dimensions, revision, render stage and
actual initial Player state. This receipt remains available independently of a
buffered running guest log. Failures emit a closed revision-specific error receipt
and fail fast. `convert_native_frame.py` performs only lossless format conversion
of that guest PPM to PNG using Python's standard library; both originals and
hashes are preserved under the feedback output. Parent visual review remains
pending until the parent opens the returned artifact. This image does not prove
input, death, reset or clean exit.

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
for this host's AZERTY layout: Up 111, Right 114, Cross 53, Square 52,
Triangle 55, Start 36. The fresh isolated config is checked against these
physical mappings before any input; shared keyboard settings are not edited.
Before injecting a press it checks server key state and refuses preheld keys
without injecting or claiming ownership. It releases only accepted own injections,
including cleanup after acknowledgement timeouts, never drives/closes unrelated windows, and
only terminates its own spawned process. Missing isolation/focus/rendering is a
runtime failure, not permission to bypass protections.

X11/inotify/select events and bounded deadlines coordinate nonvisual input, not
sleep/process polling or polling a buffered guest log. Small explicitly labeled
guest `.ready` signals acknowledge sampled input/death/reset for coordination
only. Final evidence is the **completed** guest log after Start, not readiness
signals. The stdio `fopen`-before-redirect ordering avoids the documented SDK
pitfall. Logs include revision, counts, input edges, bounded-frequency state,
actual Dash entry/freeze crossing/upward launch/Normal exit, actual death,
manual reset counter, clean exit and measured elapsed time.
`x11-input.json` records pending Xlib events, drained event types/keycodes, errors
and keymaps before injection and at acknowledgement/timeout. Buffered events are
drained and server state rechecked before blocking on the X11 file descriptor.
OS/Linux screenshot commands/APIs remain forbidden and are not used. The latest
bounded authorization permits only our app's one native-renderer export and
lossless format conversion. Parent visual inspection of that artifact is deferred
to the parent, never inferred from window titles/logs or historical images.
Preserve guest/host logs and state; distinguish guest clean exit from an emulator
shutdown fault. Historical exploratory captures created before that constraint
are retained privately, not a substitute for a new built-in visual check.

Host tests cover pure parsers/corruption, input edges/opposing axes, fresh reset,
exit precedence and fixed clock/viewport. `native_diagnostic_replay` with the
staged mask/hazards first jumps at spawn, then Dashes upward and walks right, reaching actual spike
death without teleporting or calling `die`. Full host/source/static Vita checks
and exact-commit runtime evidence are recorded privately in
`.audit/native-room-vita/finalchecks.json`. Runtime/hardware success must never
be inferred from package construction alone; physical Vita remains untested.
## Unattended guest-controls diagnostic

`--guest-replay --after-climb` explicitly builds and runs one bounded diagnostic
scenario without synthetic host keyboard input or desktop permission requests:

```sh
python3 -B scripts/feedback_native_room.py \
  --output .audit/native-room-vita/unattended-<unique-run> \
  --guest-replay --after-climb --textured --spike-art \
  --visual-dir <verified-private-eight-texture-assets> \
  --player-dir <verified-private-player-assets>
```

This still opens the real Vita3K GUI and uses the native Vita renderer. It is not
headless or verified with a locked compositor. It needs the existing SDK,
firmware, shader compiler, private archive, and accepted prepared assets; it
downloads nothing and changes neither shared emulator configuration nor desktop
security settings. No click or permission acceptance is part of this path.

`CELESTE_ROOM_GUEST_REPLAY` defaults **OFF**. Staging, build, package verification,
and runtime must agree on explicit replay intent. Normal builds retain the
existing SceCtrl mapping and sampling path. A replay package must not be run with
the manual smoke mode, or vice versa.

`src/vita/guest_replay.hpp` contains the versioned `first_room_climb_dash_v1`
typed-controls fixture: 21 input changes, 118 initial neutral ticks, 250 samples,
and a final Start at tick 249. Inputs were transcribed from the successful
first-room trace preserved at private
`.audit/native-first-room-spike-art/f4d8def61701b27b22b8e5ec38c2d32dd4974fe3/executed/run/runtime/guest.log`
(the log identifies its original executable revision as `7627c91`). The fixture
contains only caller input, not expected physics or original game code/art.
Its exact source SHA256 is pinned in staging, the executable, and feedback.

Each tick, including freeze, supplies Controls to the same `Controller::sample`
and `Session::step`. There is no state/position/speed/RNG/camera override. Tick
order and exhaustion fail immediately. The normal moving, airborne, drained
Climb condition triggers the actual GL_BACK/glFinish CPU readback; its closed PPM
and receipt are preserved and losslessly converted to a 960x544 PNG. No desktop
capture or replacement canvas is used.

The host runner never constructs X11 or loads ctypes libraries in replay mode:
no XTEST, focus/activation, keyboard injection, libei, portal, or screen capture.
It checks duplicate ownership via private-state process arguments, installs
byte-exact VPK entries, stops only its installer, and launches its title via
Vita3K `-r`. It observes guest files and its own pidfd with bounded waits. Private
OpenGL 1x configuration keeps surface synchronization enabled. The closed
completion receipt is emitted only after graphics teardown and guest-log close;
the host additionally requires Vita3K's game-closed notification before cleanup.
Failures retain partial feedback and any already exported real frame.

Completion requires observed Jump, Climb entry/ascent/drain/hold/release/landing,
Dash freeze/thaw/launch/return, actual spike death, Triangle reset, and Start exit,
plus the closed native frame and unchanged source/config state. Feedback uses
`requested_scope=guest_replay_smoke`, `input_source=scripted_guest_controls`,
`physical_controller_verified=false`, `host_input_injected=false`, and
`portal_requests=0`. `stages.input=true` means **guest fixture** input only. It
does not validate a physical controller, full game, source Level death/respawn,
hardware fidelity, or performance. Emulator elapsed time is not a Vita benchmark.
