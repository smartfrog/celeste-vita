# Native Dash runtime harness: host-tested, GPU run not authorized

This helper extends the accepted 16-file runtime overlay
`ca69c0fb6c19a062e6546ee48f5c3ba6b285919c96d16e2f8774b98b11b93fa2`
over development `572a9b88629e56a19a19944016058c281ebdb434`. It does not copy
native feature files into the helper checkout. Source/build verification is
delegated to the selected native checkout's actual `verify_native_room_vpk.py`.

## Frozen producer contract

Authority is the native feature worktree's
`.audit/native-dash-visual-feedback/producer-contract-correction-02/protocol.json`,
plus the actual producer implementation. The source input header SHA-256 is
`3d34e2a2335db02f8ee6493eb44068a7bcd4ad7bbf33f414a8ecdc85df50c324`.
`first_room_dash_trails_v1` has 360 observations, Up at 40–59, Dash only at 40,
and Start at 359. The terminal sample does not update the clock: final clock 359.

The exact boot fixture/hash and all `guest_dash_probe` fields are checked:
nine raw buttons, resolved movement/aim, jump/Dash edges, state/dead, clock,
Dash event count, occupied/committed/captured trails, fresh export and native
probe checks. Observations must be ordered and complete. The host recomputes
the Respawn14/Normal/Dash/Normal sequence, one launch, three-trail maxima,
fresh-export transition, and its relationship to the actual closed frame.
It does not infer unexported freeze timers or independent GL state snapshots.

The terminal `guest_dash_probe_complete` summary is checked against those
observations. The exclusive closed completion must match the actual producer's
wire text, including revision/header hash, `graphics_teardown=1`, `log_closed=1`,
`input_source=scripted_guest_controls`, `capture=dash_trails`, and `status=0`.
Completion and failure paths are mode-specific:

* `ux0:data/celeste_native_room-complete-<revision>-dash-probe.txt`
* `ux0:data/celeste_native_room-failure-<revision>-dash-probe.txt`

Automatic365/legacy250 fixtures, inputs and completion receipts are unchanged.
Their completion files cannot satisfy Dash; their failure files cannot collide
with Dash. Any current Dash failure or FATAL log fails closed.

## Successful runtime wiring and source binding

`smoke_native_room.py --guest-dash-probe` reuses the existing exact installer,
SDL guest-only runtime, pidfd/owned-process cleanup and private isolation path.
It creates no X11/input/portal API. It requires `--source-root`, `--build`,
`--staging`, `--vpk`, `--state`, and private `--output`; `--appdir` selects the
existing reviewed emulator distribution. Guest modes and capture overrides
are exclusive. A naturally available operator-verified DISPLAY remains required;
this implementation does not create one or bypass the guard.

The strict-clean default is retained. `--expected-source-state` is the explicit
exact-WIP opt-in, forwarded to the authoritative native verifier. Staged Dash
intent/header hash, resident ELF/SELF chain, staging/assets, binding mode and
`dash_trails` capture policy must agree. The package hash is pinned before
state preparation. The complete verification is repeated after runtime, including
the host harness fingerprint; source/input/artifact drift prevents completion.
Private emulator config bytes are frozen and hashed again after runtime.

Dash requires fresh log, readiness, export/sidecar and mode-specific receipt
paths before installation; existing artifacts are preserved and rejected.
The actual frame_saved log marker, closed sidecar and sample-derived export
frame must agree. File counts or existing files are never current-run proof.
Only observed zero owned-host exit plus final source/config verification can
set `stages.full_completion`. That field means the bounded runtime contract
completed, **not** visual compositing acceptance or physical-device proof.

## Actual raw export validation

`collect_native_frame(..., capture="dash_trails")` consumes:

* `ux0:data/celeste_native_room-<revision>-dash-probe.ppm`: 960×544 top-down P6,
  exactly 1,566,735 bytes.
* That entire name plus `.txt`: one closed frame_saved receipt, at most 8192
  bytes, including `probe_fixture`, `probe_fixture_sha256`, `native_probe_checks=1`.
* That entire name plus `.trail.rgba`: exactly 1,048,576 bytes, 512×512 RGBA,
  **raw GL bottom-up**. Logical `(x,y)` addresses `((511-y)*512+x)*4`.

Raw bytes and source measurements are never flipped, cropped or normalized.
The collector checks source-bank/room/spike/decal content, three ordered snapshot
masks/fades, and all four channels in all 4096 pixels of diagnostic tile 63:
opaque, alpha128, internal union192, asymmetric alpha64 and cleared regions,
with ±1-byte GPU tolerance. Receipt swatch values must equal exported alpha.
Snapshot tint allows one byte for the producer's six-decimal percent rounding.
The original PPM/receipt/raw are preserved by exclusive creation; the PNG uses
the existing stdlib lossless converter. No new dependencies are used.

Dash does not inherit initial-Respawn callback counts or a black-lower-row
acceptance requirement. Observed letterbox rows are recorded as received.
The raw collector alone does not establish current-run freshness. Captured-tile
preservation and GL state restoration remain explicitly **native checks**, not
independent host before/after proof; those snapshots are not exported.

## Future pipeline, only after separate authorization and both reviews

Use a fresh exact-WIP-bound native staging/build with the animated/textured/
spike/decal profile. Native staging accepts `--guest-dash-probe` and explicit
`--expected-source-state <state.json>`. CMake requires
`-DCELESTE_ROOM_DASH_PROBE=ON`, `-DCELESTE_ROOM_ANIMATED_PLAYER=ON`,
`-DCELESTE_ROOM_TEXTURED=ON`, `-DCELESTE_ROOM_SPIKE_ART=ON`,
`-DCELESTE_ROOM_DECALS=ON`, and `-DCELESTE_EXPECTED_SOURCE_STATE=<state.json>`.
Automatic, legacy replay and both capture overrides must be OFF. Select only
the approved canonical SDK/vitaGL paths after approval; no tools are installed
or copied by this helper. The older build/feedback wrapper is unchanged; call
the authoritative native staging/build steps separately, then this runtime CLI.

Actual GPU review must verify faded gameplay ghosts over nonblack room pixels,
orientation, and ghost-depth-1/player-depth-0/foreground order. Inspect the
single diagnostic ghost `(200,16)` and pair `(240,16)/(248,16)`: `(206,22)` uses
alpha128, `(214,22)` internal union192, and `(254,22)` between-ghost source-over.
Compare against the actual underlying nonblack background, not an assumed equal
neighboring textured pixel. Host-generated good bundles, binary-alpha crops,
receipt assertions and host stubs are not GPU execution proof. Compositing/depth
review remains pending even after the runtime contract passes.

Pinned emulator GPU results are not physical Vita proof. Preserve physical lower
rows even if they differ. Physical, FTP/upload/launch, staging/build/package and
Vita3K execution all need separate authorization. No desktop controls, system
screenshots, display/driver workarounds or config/security changes are included.
