# Native Vita room diagnostic

The animated non-guest-replay application now selects the bounded
[automatic first-room lifecycle](NATIVE_LIFECYCLE.md). The manual Normal-start
diagnostic and historical guest replay described below remain separate legacy
profiles; their existing evidence is not automatic-respawn evidence.

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
`vglSwapBuffers(GL_FALSE)`. That argument is `has_commondialog`, not a vsync
disable switch. The normal profile reports instrumented durations, not FPS.

### Repeatable normal interactive runs

Only the interactive animated-player default `initial_respawn` profile uses
per-run files. Guest automatic, guest replay, Dash probe, spawn, explicit
WallJump and Climb retain their existing contracts. Before any truncating/opening
operation, the normal path checks log, readiness, PPM, sidecar and failure
destinations together, then exclusively writes a closed log claim. A short opaque
process-clock token plus a candidate suffix creates the prefix
`ux0:data/celeste_native_room-run-<16hex>-<2hex>`. The suffix is bounded to 32
candidates. Files end in `.log`, `.ready`, `.ppm`, `.ppm.txt`, `-failure.txt`;
there is no new normal completion file. No normal run writes
`celeste_native_room.log` or `celeste_native_room.ready`. Full source revision,
run ID, capture outcome and `instrumented=1` are recorded together. Repeated clock
tokens and orphan/partial outputs occupy a candidate; they are never reused or
removed. Stat errors, racing claims, failed writes/closes and namespace exhaustion
are fatal, retaining partial files and all earlier runs. A destination occupied
after claim is fatal rather than waiving the strict fresh-export requirement.

### Clock calibration and passive metrics

The installed VitaSDK newlib mapping uses `sceKernelGetProcessTimeWide` for
`CLOCK_MONOTONIC`, converting microseconds to seconds/nanoseconds. This is not a
CPU-clock inference from its name. The normal run checks 64 consecutive reads
for regression and reports the maximum adjacent read gap, **not** guaranteed
read-call overhead. After the namespace/log claim and before graphics, session,
player, controls or gameplay RNG construction, calibration requests
`sceKernelDelayThread` waits of 100000, 100000, 100000 and 1000000 microseconds.
Startup therefore adds roughly 1.3 s; scheduler overshoot is allowed without an
upper target-duration bound. There are no waits in gameplay.

Each endpoint brackets checked UTC `sceRtcGetCurrentClock` / `sceRtcGetTime_t`
conversion between process-clock reads. Nonnegative seconds, microseconds below
1000000, overflow, nondecreasing clocks and brackets at most 1000 us are required.
RTC elapsed must lie inside `[P1_lo-P0_hi, P1_hi-P0_lo]`, allowing an explicitly
chosen `floor(RTC_elapsed/100)+2 us` tolerance. Process lower-bound and RTC elapsed
must also reach `requested-floor(requested/100)-2 us`. This 1%+2 us policy is a
diagnostic criterion, not a hardware accuracy specification. A single bounded
record binds criteria, all endpoints/deltas, run ID, revision and result.
Calibration/API/IO failure aborts through the normal fatal path before gameplay.
`blocked_elapsed_check=passed suspend_validated=0 hardware_perf_proof=0` means
only that check passed; the RTC is a separate API, not independent hardware proof,
and its microsecond representation does not prove physical microsecond resolution.

Metrics reanchor after startup. Fixed-storage unsigned-64 counters retain counts,
sums, maximum duration and its earliest zero-based **sample-frame index**. The
microsecond buckets are `<=16667`, `16668..20000`, `20001..33334`,
`33335..50000`, `50001..100000`, `>100000`; strict threshold counts are `>20000`,
`>33334`, `>50000`, `>100000`. Loop intervals cover the **prior sample frame**,
including its capture/summary tags. Step is the session step call; render includes
the existing swap and any synchronous capture/export; log is the sum of successful
in-loop formatted-write/newline/flush calls in that frame. Nothing feeds timing
back into the fixed `1/60` step, input, RNG or renderer ordering. The hot metrics
path performs no allocations or IO. Every 300 samples and on Start, bounded
summaries show measured `all_` and separately tagged `steady_` series. Steady
excludes capture/summary/intercepted samples, not merely long durations.
The periodic snapshot precedes its own log duration (retained in the next
summary); startup/teardown and the final summary's own log are outside the sample
window. Arithmetic overflow, clock regression, excluded samples and invalid
status are explicit rather than wrapped or silently converted to valid zeroes.
The existing controller sample's `SCE_CTRL_INTERCEPTED` flag (the SDK's
`SCE_CTRL_PSBUTTON` alias) excludes the affected frame and reanchors before its
interval is accepted. Input still follows the unchanged controller path; no
interception mode is set. No suspension is inferred from gap length. Signals
that occur entirely between samples may be missed; detection completeness and
physical suspend behavior remain separately unverified. No full-session FPS,
GPU execution-time or uninstrumented/hardware
performance result follows from these records.

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
export VITASDK=/home/fred/projects/celeste-vita/.audit/native-oracle/tools/vitasdk-2026.08.1-linux-x64
export VITAGL=/home/fred/projects/celeste-vita/.audit/native-oracle/tools/vitagl-cd3791e
export PATH="$VITASDK/bin:$PATH"
# Reuse verified existing preparation; generate it separately only if absent.
python3 -B scripts/stage_native_room.py
/usr/bin/cmake -G "Unix Makefiles" -S . -B .audit/native-room-vita/vita \
  -DCMAKE_TOOLCHAIN_FILE="$VITASDK/share/vita.toolchain.cmake" \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DCELESTE_VITA=ON \
  -DCMAKE_CXX_FLAGS="-I$VITAGL/source" \
  -DCELESTE_VITAGL_LIBRARY="$VITAGL/libvitaGL.a" \
  -DCELESTE_ROOM_STAGING="$PWD/.audit/native-room-vita/staging"
/usr/bin/cmake --build .audit/native-room-vita/vita -j2
python3 -B scripts/verify_native_room_vpk.py \
  --vpk .audit/native-room-vita/vita/src/vita/celeste_native_room.vpk \
  --build .audit/native-room-vita/vita/src/vita \
  --staging .audit/native-room-vita/staging
```

Use fresh staging and build directories, not a preserved candidate. The vitaGL
include override is required because this SDK has no installed `vitaGL.h`.
Staging, build and package verification require committed-clean source by default;
current source/config changes are rejected even when HEAD matches an older package.
Only the four exact untracked `.opencode` coordination paths are exempt.
Root `CELESTE_VITA` defaults OFF; host tests need no SDK.
`vita-elf-create`, `vita-make-fself`, `vita-mksfoex` and `vita-pack-vpk` are invoked
by the installed VitaSDK CMake macros. Unique title ID: `CELR00001`, version 00.01.
The <2 MiB package size is a goal, not a performance claim.

### Explicit exact-WIP verification

A dirty checkpoint requires the same explicit complete expected-state JSON at
every stage: `--expected-source-state <manifest>` for staging and verification,
and `-DCELESTE_EXPECTED_SOURCE_STATE=<absolute-manifest>` for CMake. Obtain it
from `native_room_revision.source_identity()` after freezing code and reviewing
the state, and store it under `.audit`; never edit an older receipt to fit new
code. The manifest binds base HEAD, all expected paths, modes, status and bytes.
There is no implicit dirty fallback or claim that a WIP binary is a clean SHA.

For the bounded lifecycle package, pass
`.audit/native-player-death-respawn/native-geometry` as `--mask-dir` and
`.audit/native-player-death-respawn/native-hazards` as `--hazard-dir`. Reuse
`.audit/native-lifecycle-vita/prepared/{spike-visuals-01,decals-01}` and original
`.audit/native-player-death-respawn/native-assets-02`. Pass these three as `--visual-dir`,
`--decal-dir`, `--player-dir`; enable CMake's `CELESTE_ROOM_TEXTURED`,
`CELESTE_ROOM_SPIKE_ART`, `CELESTE_ROOM_DECALS` and
`CELESTE_ROOM_ANIMATED_PLAYER`. Leave guest replay and deferred capture OFF.
This stages the actual death-extension producer output directly, not a derived
payload-only directory. Player provenance retains all `files` hashes and new
producers declare `payload_files` and `evidence_files` separately. Legacy
payload-only provenance remains supported. `bank.json` is verified source-linked
evidence, never a VPK entry; the death payload is `player.txt` (13992 B) and six
32768-byte pages (210600 B total). Unknown files, missing pins and bank/metadata
mismatches fail staging. Evidence is not deleted or omitted from its provenance.

The build generates a readonly resident ELF token over the complete source
identity, staged provenance/pins/payload, prepared evidence, SDK tools, vitaGL,
linked SDK archives, generated compile/link flags and explicit include headers.
The verifier recomputes it rather than trusting the generated receipt. It also
reruns the pinned `vita-elf-create` and `vita-make-fself -c -s` conversions in a
private temporary build directory and requires byte-identical VELF/SELF, then
matches the actual packaged SELF and assets. Changed inputs or preexisting
unbound artifacts require a fresh build directory. Before/after checks reject
source, input and artifact drift; a different WIP at the same HEAD cannot reuse
the old binary by editing receipts. This is a local provenance check, not signed
authentication against a malicious builder. Real SDK-chain reproducibility must
be checked on the authorized fresh target build; mock conversion tests alone do
not establish it. It proves neither runtime/hardware behavior nor performance.

### Input-only automatic guest diagnostic

`CELESTE_ROOM_GUEST_AUTOMATIC=ON` selects `first_room_auto_death_v2` through
`src/vita/guest_automatic_replay.hpp`. It defaults OFF, requires the animated
Player, and is mutually exclusive with the unchanged legacy
`CELESTE_ROOM_GUEST_REPLAY`/250-frame fixture. Both normal animated production
and the new diagnostic call the same automatic `Session` constructor; only
input sampling and observation differ. No poses, timers, RNG or expected
outcomes are supplied to gameplay.

Use `stage_native_room.py --guest-automatic`, not `--guest-auto`; keep deferred
capture flags OFF and use distinct fresh production/automatic staging and build
directories. Both variants require the same exact-state opt-in described above.
Provenance and generated pins carry `guest_automatic` as the fixture ID or null;
`guest_automatic_fixture` pins the source header SHA256, sample count and exit
frame. Legacy `guest_replay` is unchanged. The resident build token also binds
the actual compile definition and CMake mode, so production and automatic
artifacts at the same source fingerprint cannot be relabeled interchangeably.

The fixture contains only accepted immutable default-profile source raw
Right/Left/C input changes for frames 0–363, then Start at frame364. All 365
samples use `Controller::sample`; the exit sample observes the current Session
without an extra Scene update. Per-sample `guest_automatic` records contain
`fixture frame x y jump reset exit state dead reloads room_deaths save_deaths
jumps`. Here `x`/`y` are sampled input axes and `jump` is held C/Cross, not a
position or an asserted Jump outcome. State and counters are observed after
the actual step; `reset` remains 0.

`guest_automatic_complete` contains `fixture samples exit_frame reloads
room_deaths save_deaths jumps full_completion`. Completion requires observed
initial Respawn14→Normal, two deaths and automatic reloads through Respawn14→Normal,
three actual Jumps, no manual reset, an alive final Normal Player, terminal Start,
and successful graphics teardown. A fresh native frame export is required; the
existing completion receipt is closed only after the guest log closes cleanly.
External verification must still independently check inputs, events, image and
receipt rather than trusting `full_completion`. Host-only fixture checks do not
establish Vita execution, hardware fidelity, full Engine/ECS behavior or performance.

Without an explicit WallJump/Climb capture override, both animated production
and the automatic guest use `capture=initial_respawn`. Frame0 still renders and
publishes readiness, but does not export its initial Respawn14/wipe image. Export
waits for the first actual live Normal Player with no active wipe, no death or
reset, loads1/reloads0, respawn_callbacks1/wipe_callbacks0, and no pending or
committed corpse. The predicate only reads Session state; it adds no Scene step,
draw, input, countdown or RNG call. Capture frame numbering is the app's
post-step render frame, one greater than that input sample's zero-based index.
The receipt includes `wipe_active=0` and the actual lifecycle witnesses. Missing,
skipped or duplicate exports fail completion; a black image is never accepted
by relaxing body/content probes. The resident build context explicitly binds
the capture policy and checks its compile definitions against CMake options.
Legacy manual spawn, WallJump and Climb capture policies remain unchanged.

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
The legacy/scripted `initial_respawn` path preserves an existing pair too, but
fails because it cannot satisfy the required fresh export. The normal interactive
profile instead claims the fresh per-run namespace described above; it never
uses an older pair as a successful capture.

Normal interactive logging owns a separate non-standard `FILE*`, opened in append
mode only after the exclusive run claim. Bootstrap/calibration, asset-ready,
input, capture, metrics and fatal lines all use that same stream, with checked
format/newline/flush and a checked single close. It never redirects or closes
global `stderr`. On the inspected VitaSDK newlib build, the first ordinary asset
`fopen` can reinitialize global `stderr` after a `freopen` redirect; checked writes
can then succeed on the wrong destination. The owned-stream repair is covered by
a host global-reset test double and real asset-stdio churn, not yet by a new
physical/Vita3K run. Fatal log/close errors still reach the independent SCE
failure receipt, including operation/path context. Legacy profiles keep their
existing checked `stderr` and completion contracts.
If that independent receipt also fails, the caller reports the complete composed
error through checked, non-recursive default-stderr emergency output before
returning status 2. If the emergency output fails too, the full-context exception
propagates and execution stops instead of claiming the report succeeded.

Readiness is event-driven, not a heartbeat: the initial `.ready` can remain
`pending` at frame 0 if no later input/death/reset/dash-done signal occurs, even
after a fresh capture at frame 36 and many periodic log summaries. That is not a
logging or simulation failure. The owned-stream repair does not change readiness
format, frequency, input or gameplay.

Legacy/scripted guest files are `ux0:data/celeste_native_room-<revision>.ppm` and a closed `.ppm.txt`
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
The verified guest/frame stages and explicit timeout error survive cleanup.
This scripted guest host-exit requirement leaves the default manual smoke policy
unchanged and is not a new manual host-health validation.

### Automatic lifecycle host verification (separate opt-in)

`--guest-automatic` consumes the [input-only automatic guest diagnostic](#input-only-automatic-guest-diagnostic),
not the legacy 250-sample Triangle replay. It is incompatible with `--guest-replay`,
`--after-climb`, `--after-wall-jump` and `--frame-only`.

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

The host independently checks the `initial_respawn` policy and lifecycle witnesses
described above. Its positive app-frame number must equal the first observed
Normal sample plus one; that increment is not an extra simulation step.
Missing deferred files remain pending, not successful.
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
