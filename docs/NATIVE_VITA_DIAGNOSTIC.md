# Native Vita room diagnostic

This is our own C++ executable/VPK, not the original game. It composes the
accepted [Normal Player](NATIVE_PLAYER.md), [bounded Dash](NATIVE_DASH.md), [full merged solidmask](NATIVE_TILEMAP.md)
and [five static Up/Left spikes](NATIVE_HAZARDS.md) for explicitly selected room
`1`. Debug rectangles are **not faithful graphics**. Audio, original respawn,
corpse/reload lifecycle, other Player states, room transitions and full
gameplay remain excluded. It is not a completed playable port or a hardware
performance result.

## Controls and clock

- Physical manual build: the left stick (standard analog mode, **not** wide range)
  and DPad feed the source-style MoveX 0.3 / MoveY 0.7 axes used for movement,
  climb and glider-independent vertical input. Left stick and DPad also feed the
  independent Aim binding (threshold 0 plus radial 0.25), snapped to eight
  directions with the source 22.5/17.5 degree asymmetry. Same-direction stick
  precedes DPad. Opposite movement uses source `TakeNewer`; opposite Aim compares
  magnitudes then `TakeNewer`. This intentionally differs from the legacy
  both-DPad-pressed neutral rule only in the new analog profile and is not a
  hybrid priority policy.
- The raw stick mapping is a fixture assumption for later calibration, not
  original-source or hardware proof: `SCE_CTRL_MODE_ANALOG`, bytes 0..255 assumed
  centered at 128 and right/down positive, piecewise `(v-128)/128` and
  `(v-128)/127`. An unavailable sample still fails loudly and is never treated as
  raw 0,0 full up-left. Raw `lx`/`ly` plus resolved move/aim telemetry is logged
  on changes and periodically for a later physical calibration pass.
- The scripted guest-replay build does not sample hardware analog input and keeps
  the existing nine-bool `Controller::sample(Controls)` path, DPad opposing
  neutral behavior, edges and 250-frame fixture byte-for-byte unchanged.
- Cross: sampled held/rising-edge input to the existing Player VirtualButton.
  Releasing clears held; a subsequent press produces a new edge.
- Square: sampled Dash VirtualButton; aim is the independent analog profile above.
  Cross/Jump, Triangle/manual reset and Start/exit remain separate.
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
the black letterbox rows. Before an export, the guest checks both destinations with
`sceIoGetstat`: if either the `.ppm` or its `.ppm.txt` receipt exists, it
preserves both, logs `capture_skipped_existing ... prior_capture_preserved=ppm_and_receipt
current_run_capture=false`, emits no `frame_saved` receipt and continues drawing,
sampling controls and accepting Start. The resolved capture flag prevents a
retry on every frame for both spawn and deferred policies. New outputs still use
`SCE_O_EXCL`; unexpected stat/write errors fail fast instead of being treated as
missing. An existing failure receipt is likewise preserved without masking the
primary error, and stale artifacts never satisfy a current-run capture claim.

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

`--appdir <extracted-AppDir>` selects the official sharun layout (`AppRun`,
`bin/Vita3K`) while the default keeps the historical
`<existing>/squashfs-root` linuxdeploy layout and its Qt hook. The vendor
`AppRun` is executed directly; its loader/environment is not recreated.
`/tmp` is a private bind of the state temp directory, mounted before the real
state path is restored. AppDir, replay VPK and firmware paths that live under
`/tmp` are remapped read-only at their real paths; only the actual state remains
writable. Only the host `/tmp/.X11-unix` socket directory is exposed read-only
for later GUI access. The sandbox has a private network namespace, fresh private
`HOME`/`XDG_RUNTIME_DIR`, and no session-bus/SSH-agent environment. The effective
original `XAUTHORITY` is resolved before `HOME` changes: an explicit value is
preserved, and the implicit original file path is exposed read-only if the
private `/tmp` hides it; cookies are never read, copied or reported. Vendor
auto-updates are disabled (`DISABLE_AUTO_UPDATES=1`). Missing launcher files fail
explicitly before launch.

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

All GUI launch paths require an explicit, nonblank `DISPLAY`. This fail-fast
guard does not test connectivity: the operator must separately verify the
existing real display and authorization. No display discovery or fallback is used.

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
the host additionally requires an observed Vita3K exit status 0 before cleanup.
Failures retain partial feedback and any already exported real frame.

`--source-checkout <clean-checkout>` permits a reviewed host harness to replay a
genuine prebuilt VPK from an earlier revision. Before creating emulator state or
launching, replay verifies that the selected checkout is clean, is at the exact
VPK source revision, and contains the same fixture identity. Feedback records
the selected source revision separately from the actual host-harness revision,
changes and fingerprint. The default is the current source root, and dirty,
wrong-revision or fixture-mismatched selected sources are rejected.

Guest replay launches the installed app through Vita3K's SDL frontend, which the
pinned CLI documents as running the `-r` app in a plain window and quitting with
it; manual/legacy smoke keeps its existing Qt/X11 path. Guest completion requires
the exact closed guest receipt, observed fixture/input checkpoints, the native
frame and a final observed host exit 0; it does not depend on Qt's
`on_game_closed` log message. Guest launches also use a private PID namespace so
AppRun's detached descendants are reaped with the owned launcher wrapper. The
private config seeds the verified `user-id` and controller bind defaults that the
emulator otherwise normalizes, and the unchanged raw config hash check still
fails the run if any other field changes.

Completion requires observed Jump, Climb entry/ascent/drain/hold/release/landing,
Dash freeze/thaw/launch/return, actual spike death, Triangle reset, and Start exit,
plus the closed native frame and unchanged source/config state. Feedback uses
`requested_scope=guest_replay_smoke`, `input_source=scripted_guest_controls`,
`physical_controller_verified=false`, `host_input_injected=false`, and
`portal_requests=0`. `stages.input=true` means **guest fixture** input only. It
does not validate a physical controller, full game, source Level death/respawn,
hardware fidelity, or performance. Emulator elapsed time is not a Vita benchmark.

A nonzero emulator exit after the observed clean guest shutdown remains an
overall partial result: already verified guest input/exit and native-frame
stages survive, but `full_completion` stays false and the host error is retained.
Do not turn an emulator post-game crash into a successful host exit.
Replay completion requires an observed host exit status 0 within the 30-second
post-guest wait. A timeout is partial even if subsequent owned-process cleanup
returns 0; cleanup status 133 or termination likewise cannot promote completion.

### Production automatic lifecycle (separate opt-in)

`--guest-automatic` selects `first_room_auto_death_v2`, not the legacy 250-sample
Triangle replay. It is incompatible with `--guest-replay`, `--after-climb`,
`--after-wall-jump` and `--frame-only`. The native build must use
`CELESTE_ROOM_GUEST_AUTOMATIC=ON` and the production animated death profile.

For an already verified artifact, `smoke_native_room.py` requires `--source-root`
(the native source checkout), `--build` (its build's `src/vita` directory), and
`--staging`, in addition to the existing VPK/state/output arguments. Verification
delegates to that source root's `scripts/verify_native_room_vpk.py`, before and
after runtime. Dirty sources require explicit `--expected-source-state PATH`;
without it the native committed-clean default remains strict. The resident
binary/build/assets binding and complete source identity must match throughout.
The feedback wrapper forwards these native source/manifest pins to staging,
CMake, package verification and smoke; it requires the animated `--player-dir`.
Invoking the wrapper builds and runs: do not invoke it before review/runtime GO.

The input-only sequence is derived from accepted source trace SHA256
`b2123d17ef324e44535f20f75963ea9a177ea38217c8255162a2c97c45c04260`:
364 production steps, then a non-stepping exit sample at frame 364. The host
requires exactly 365 ordered `guest_automatic` records with the exact controls,
two actual death rising edges, two dead-to-Respawn14 reloads, three Respawn14-to-
Normal transitions (including startup), three actual Jumps, monotonic counters,
no manual reset, and a live final state. `guest_automatic_complete` alone cannot
prove completion. The closed guest receipt, current-run native image, unchanged
private config and observed host exit 0 remain independently mandatory.

The production animated automatic profile defaults to `capture=initial_respawn`:
frame 0 renders and publishes readiness, but does not export its initial wipe.
One fresh export follows the first live Normal render with no active wipe,
`loads=1`, `automatic_reloads=0`, `respawn_callbacks=1`, `wipe_callbacks=0`, no
pending/committed corpse, and zero deaths/resets. Its positive app-frame number
must equal the first observed Normal sample plus one; that increment is not an
extra simulation step. Missing deferred files remain pending, not successful.
The native resident build binding must declare the same capture policy; old
frame-0 automatic artifacts are rejected before launch. Receipt body draw count,
source RGB/texture/bank/hair/spike/decal checks remain mandatory, including visible
live player hair. Black or relabeled intro frames cannot prove completion.
Explicit WallJump/Climb overrides keep their existing policies; legacy `spawn`
still requires frame 0.

This path retains guest-only input, private isolation and owned-process cleanup;
it never opens host input/desktop APIs. The image is the guest's own native
`glReadPixels` export, not a desktop screenshot or a replacement renderer.
Unit/mocked protocol checks are not a new emulator lifecycle pass. No physical
controller, hardware, full-game, GPU fidelity or performance claim follows.
The verified guest/frame stages and explicit timeout error survive cleanup.
This host-exit requirement is replay-specific; the default manual smoke policy
is unchanged and is not a new host-health validation.
