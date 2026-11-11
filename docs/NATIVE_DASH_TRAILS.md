# Bounded native Dash trails

Normal Madeline's Dash now requests the original three blue (`#44B7FF`) body-and-hair trails: launch, the `.08` timer crossing, and coroutine completion. Cancellation does not synthesize completion. Movement, freeze, input, hair tint and RNG are unchanged. Audio, optional particles, slash, displacement and shake are not added.

`PlayerTrails` is level-owned. Its 64 first-free slots retain the creation anchor and body scale, but reference the current presentation until BeforeRender. The first lazy manager capture waits for the manager's next Scene commit; later requests may capture while their Snapshot is still pending. Captured tiles never refresh. Snapshot updates precede Player updates, do not run during positive-freeze SceneSkip, test `Percent >= 1` before incrementing, and release slots at the following commit. Equal-depth rendering follows creation order, not slot order. Death retains the pool; Reload clears it before rebuilding Player/Hair. The scene graphics teardown disposes the target.

The target is one 512×512 RGBA FBO, with 64×64 tiles. Only a new tile is cleared. Hair then PlayerSprite are captured with premultiplied source-over. PlayerSprite floors the translated render position; hair floors its translated root and subtracts the atlas offset afterward. A white `DST_ALPHA/ZERO` quad makes the completed tile `(A,A,A,A)`. This is original `TrailManager.MaxBlendState`, **not** GL_MAX. Applying the truncated original `Color * (.75 * (1 - CubeOut(p)))` once to the completed tile avoids double-fading hair/body intersections. Ghost depth 1 precedes Player 0 and foreground art.

## Source recording contract

`prepare_dash_trail_oracle.py` extends an explicitly supplied, immutable accepted room-core extraction in a separate generated assembly. Original TrailManager, CreateTrail, Dash methods/callsites and supporting math are byte-pinned. Existing profiles/generators/support files are not changed. New draw/device leaves are declared recording boundaries; optional effects are excluded or source-only. Native import guards remain fail-closed.

`compare_dash_trails.py` observes 360 frames each for first/repeat/cancel/reload/capacity/fractional-anchor API scenarios. Capacity/fractional cells are declared TrailManager.Add API fixtures, not invented Player poses or timing callbacks. Native output never supplies source inputs. It compares slots, commit/capture phase, percent, ordering and fade bytes, and records original capture vertices/blends/target/clear calls. Non-repeat capture geometry is compared exactly.

Repeat captures retain a diagnosed **existing presentation gap**: original selects idle on landing while native briefly retains jumpFast, changing subsequent hair nodes. Only 90 hair00 position/vertex differences at capture ticks 134/139/145 are admitted, and their complete raw source/native value pairs must match the immutable pre-correction fingerprint `9a5173ced88ab08fef14749402539f75f97281c7df3c46a2ab72349324f68ffc`. This fingerprint comes from the preserved `parity-frozen-release/repeat.source.jsonl` / `repeat.native.jsonl` recordings, not a new native run. Body geometry and every texture/scale/rotation/color/alpha/origin field are always enforced. A changed, missing or additional inherited pair fails closed. All 90 differences and raw value pairs remain reported without normalizing source results. This cut does not claim complete body/hair presentation parity or original GPU pixels.

## External GPU probe protocol

**Current correction 04 is an instrumented diagnostic-only build.** `CELESTE_ROOM_DASH_PROBE=ON` now always enters the sweep below and exits nonzero at its capture point, even if every observed swatch/marker matches. There is no new staging or compile flag and no acceptance bypass. The retained normal-frame/360-sample/completion contract below is not a success path in this build. Existing strict helper rejection must remain enabled; historical VPKs are not current-source verified after these source changes.

After independent review and explicit staging/build approval, use `stage_native_room.py --guest-dash-probe` with the existing player/visual/decal inputs and a fresh exact-WIP-bound staging directory. Build with normal animated/textured/spike/decal options and `-DCELESTE_ROOM_DASH_PROBE=ON`. Keep `CELESTE_ROOM_GUEST_AUTOMATIC`, `CELESTE_ROOM_GUEST_REPLAY` and capture overrides OFF. Strict-clean default, explicit `--expected-source-state` / `CELESTE_EXPECTED_SOURCE_STATE` opt-in, resident ELF/SELF and staging bindings remain required. No actual staging/build packaging is authorized by this protocol document.

Probe provenance adds `guest_dash_probe="first_room_dash_trails_v1"` and `guest_dash_probe_fixture={id,samples:360,exit_frame:359,source:"src/vita/guest_dash_probe.hpp",sha256}`. The unchanged 1,092-byte fixture header SHA256 is `3d34e2a2335db02f8ee6493eb44068a7bcd4ad7bbf33f414a8ecdc85df50c324`. Generated asset pins carry that ID/hash/sample bound/terminal frame and `CELESTE_STAGED_DASH_PROBE`. Compile-time and build/package checks reject missing, mixed or wrong staging intent; the resident capture policy is separately bound as `dash_trails`. Probe-OFF provenance adds no new keys and old-mode asset-pin text remains byte-identical for equivalent inputs.

The input-only `first_room_dash_trails_v1` fixture waits through Respawn14, holds Up at samples 40..59, presses Dash only at sample 40, and supplies terminal Start at sample 359. Existing automatic365 and legacy250 inputs/IDs are unchanged. There is no host/controller injection. Capture waits for all three committed trails, draws actual faded ghosts over the nonblack first room, and exports before swap through the existing native `GL_BACK` path:

* `ux0:data/celeste_native_room-<revision>-dash-probe.ppm`: 960×544 P6, 1,566,735 bytes.
* Same path + `.txt`: closed capture receipt, including probe measurements.
* Same path + `.trail.rgba`: actual FBO attachment, 512×512 RGBA, 1,048,576 bytes; raw GL bottom-up rows.

Unused tile 63 contains opaque, alpha128, overlapping alpha128 (union alpha192), and asymmetric alpha64 swatches. Native readback checks all four channels (±1), orientation, preservation of captured tiles, and GL state restoration. Failure is fatal; an existing export is preserved and cannot count as fresh proof.

### Native observation and completion records

The boot line starts `guest dash probe fixture=... fixture_sha256=... input_source=scripted_guest_controls samples=360 exit_frame=359 physical_controller_verified=false host_input_injected=false capture_policy=dash_trails`.

Exactly 360 `guest_dash_probe` lines observe actual post-`Session.step` samples 0..359 on the same Session. Keys are `fixture`, `frame`, raw `left/right/up/down/cross/triangle/start/square/l`, sampled `jump/jump_pressed/jump_released/dash/dash_pressed/dash_released/grab/reset/exit/x/y/aim_x/aim_y`, and actual `state/dead/clock/dash_events/trails/committed_trails/captured_trails/fresh_export/native_probe_checks`. Terminal Start is observation 359, not an extra update: its clock remains 359. Raw fixture input is checked against the pinned header and declared terminal Start; Triangle/reset is never permitted. Per-sample lines are at most 767 bytes plus newline.

The closed frame receipt additionally binds `probe_fixture`, `probe_fixture_sha256` and `native_probe_checks=1`. The observer accepts it only once, for the current rendered frame, matching revision/path/hash/capture policy, after three committed and captured trails, and requires `trail_probe=diagnostic_rgba_fbo other_captured_tiles_preserved=1`. Native swatch/readback failures throw before a successful return; synthetic host observer tests are not GPU evidence.

Only after all 360 valid observations, actual Dash entry/completion, one Dash event, observed maxima of three occupied/committed/captured slots, a fresh successful probe export, and successful graphics teardown does the log emit `guest_dash_probe_complete`. Its keys are `revision/fixture/fixture_sha256/samples/exit_frame/clock/dash_events/max_trails/max_committed/max_captured/fresh_export/native_probe_checks/full_completion/graphics_teardown`. Summary records are bounded to 767 bytes plus newline. The completion gate advances only after that summary is successfully written and flushed.

Only after that run returns successfully **and the log closes successfully** does native main exclusively create `ux0:data/celeste_native_room-complete-<revision>-dash-probe.txt` (at most 1,024 bytes). It starts `complete`, carries those source-bound completion fields, and adds `input_source=scripted_guest_controls capture=dash_trails graphics_teardown=1 log_closed=1 status=0`. Failures use `celeste_native_room-failure-<revision>-dash-probe.txt`, bounded to 2,047 bytes, with `FATAL revision/fixture/fixture_sha256/capture/cause`. Existing files are preserved. Old automatic365/legacy250 receipt paths and bytes are unchanged, so same-revision mode receipts cannot collide. The shared general log still requires archive-before-next-launch; there is no generic run namespacing.

`native_probe_checks=1` reports native GPU swatch/readback and native before/after state checks. It is **not** an independent host observation of GL state preservation. The external helper must inspect the exported GPU pixels; a closed completion receipt alone does not establish independent GPU fidelity. A 1 MiB collector bound comfortably covers the bounded 360 sample lines plus ordinary diagnostics.

### Pre-validation diagnostic evidence (correction 03)

The first source-bound GPU attempt failed at the `(454,454)` swatch before normal export. Its cause remains unconfirmed. This evidence-only addition changes no orientation, blend, render pass, expected byte or tolerance.

Only `CELESTE_ROOM_DASH_PROBE` calls the diagnostic writer. Immediately after the existing post-swatch `after=read_rgba()` returns, before either captured-tile preservation or swatch validation, its callback exclusively writes **all 1,048,576 untouched bytes** to `ux0:data/celeste_native_room-<revision>-dash-probe-diagnostic.trail.rgba`. This is not the accepted `.ppm.trail.rgba` attachment. No flip, crop, normalization or additional GPU read/render pass is performed. Existing diagnostic files are preserved; open/write/close failures propagate with the diagnostic path and original IO error. The existing graphics cleanup and fatal/failure-receipt path remain responsible for failed probes.

After the diagnostic file closes, four flushed `guest_dash_probe_diagnostic` log records report `path/revision/frame/width/height/bytes/layout/swatch/x/top/row/offset/expected_rgba/actual_rgba/mirrored_row/mirrored_offset/mirrored_rgba`. `frame` is the current draw/export frame, not the input observation index (observation 56 precedes draw frame 57). Offsets are zero-based byte offsets into the saved buffer. Each RGBA field contains all four channels; `row=511-top`, `mirrored_row=top`, `offset=(row*512+x)*4`. `layout=GL_bottom_up_RGBA8` identifies the existing readback interpretation, not independent proof of its correctness. Records are at most 767 bytes plus newline.

| swatch | x,top | expected RGBA | row / offset | mirrored row / offset |
| --- | --- | --- | --- | --- |
| single | 454,454 | 128,128,128,128 | 57 / 118552 | 454 / 931608 |
| inner_union | 462,454 | 192,192,192,192 | 57 / 118584 | 454 / 931640 |
| opaque | 486,454 | 255,255,255,255 | 57 / 118680 | 454 / 931736 |
| orientation | 486,470 | 64,64,64,64 | 41 / 85912 | 470 / 964504 |

Every diagnostic line explicitly states `diagnostic_only=1 accepted_frame=0 fresh_export=0 native_probe_checks=0 full_completion=0`. These are pre-validation observations, even if a later check succeeds. A diagnostic-only file/log bundle is **never an accepted normal frame bundle** and never grants export, native-check or completion credit. The original fatal messages, all-channel ±1 threshold, tile-preservation checks and post-teardown/closed-log completion gates are unchanged. If validation still fails after successful diagnostic IO, the run still fails, but the raw bytes and all four point/mirrored-row records survive for inspection. Host scripted-buffer/IO tests establish evidence ordering and preservation only, not GPU mathematics or rendering fidelity.

### Instrumented discriminating sweep (correction 04)

Attempt 02's entire original 1,048,576-byte raw attachment was zero (`30e14955ebf1352266dc2ff8067e68104607e750abb9d3b36582b8af909fcb58`). Its failed-run data and reviewed correction 03 remain immutable. All-zero bytes do not establish a Y flip, rounding problem or any specific root cause. No orientation, expected value, ±1 tolerance, gameplay capture/mask or physics/input/RNG/presentation fix is made here.

The same `--guest-dash-probe` staging intent and `-DCELESTE_ROOM_DASH_PROBE=ON` mode select this sweep automatically; old automatic365/legacy250 modes remain separate. All new records, including the retained four original diagnostic point records, state `instrumented=1 uninstrumented_proof=0`. Extra reads and `glFinish` calls can change visibility/timing; an instrumented matching original swatch is **not** evidence that the uninstrumented renderer was fixed.

Ordered operations on the existing attachment:

1. Retain the original pre-swatch read. Draw the original diagnostic swatches, then add one full 512×512 RGBA read **before the original alpha mask**, initialized to `0xC3`. Log all four expected/mirrored samples, counts and histogram; do not export this array. Expected pre-mask RGBA values are `(64,32,16,128)`, `(96,48,24,192)`, `(51,120,0,255)`, `(16,16,16,64)` in the original point order.
2. Apply the unchanged original mask, retain the exact existing post-mask read and exclusive correction-03 raw path, and log its four original expected/mirrored samples. It still uses the legacy zero-initialized buffer; the paired experiment, not this initialization, distinguishes no-write from observed zeros. Run the unchanged tile and swatch checks. Record `original_result=matched|failed`, preserving the original cause **before marker mutation**. If this result cannot be logged, stop without mutating markers and fail.
3. Read the same unchanged attachment twice into contrasting `0xA5` / `0x5A` RGBA scratch buffers. No intervening drawing or read-vs-both-binding experiment occurs. Log per-read changed/retained/zero counts, 16-bin byte histogram (`byte >> 4`) and all four point/mirror samples. Log `sentinel_pair classification=no_write|partial_no_write|consistent_overwrite|differing_reads`, `bytes`, `retained_pairs`, `differing_bytes`; a byte retains its pair only if the first is `0xA5` and the second `0x5A`. A single retained sentinel value can also be real data; it is not independently conclusive. Failed reads are reported as errors/unavailable, never invented values.
4. Only now touch unused tile 63: a scissored nonzero-alpha `glClear`, followed by distinct opaque, blend-disabled scissored/unscissored quads. All geometry stays within top-oriented `[448,512]×[448,512]`. Marker definitions and sample coordinates are shared by drawing and logs:

| marker | top-oriented rectangle x,y,w,h | expected draw RGBA | scissor | sample x,top |
| --- | --- | --- | --- | --- |
| clear | 448,448,64,64 | 17,33,65,96 | GL box 448,0,64,64 | 450,450 |
| scissored_quad | 452,452,12,12 | 68,119,170,255 | GL box 452,48,12,12 | 454,454 |
| unscissored_quad | 484,484,12,12 | 205,82,41,255 | disabled; geometry tile-bounded | 486,486 |

5. Read marker **RGBA first** (`0xA5` initialization), then full 512×512 **GL_RGB/GL_UNSIGNED_BYTE** (`0x5A` initialization). Save both exact arrays, log counts/histograms and the three expected/mirrored marker samples. RGB logs report three observed channels only; declared expected draw alpha is not measured RGB alpha. There is no post-RGB read and no GL_BACK/background pass. The complete sweep performs seven reads instead of two: five additional read/finish operations, not an uninstrumented proof.
6. Compare captured gameplay bytes against the paired pre-marker reference only where the pair agrees and the marker RGBA byte does not retain its initialization sentinel. Log `checked_bytes/changed_bytes/unobservable_bytes`; changed observable bytes add a fatal cause. This is limited CPU-observable evidence, not independent GPU tile preservation proof. Restore/verify read/write bindings, viewport/scissor, matrices/mode, texture/color, blend settings/enables, depth/cull, **clear color**, and observed pack alignment. Pack state is not modified: pinned vitaGL reports alignment 1 and its setter supports only `UNPACK_ROW_LENGTH`, so unsupported setters are not guessed. Query/read/restoration GL errors are explicit failures.
7. Always throw after available evidence is persisted and state restored. Preserve an original failure first, plus diagnostic IO/GL/log/cleanup contexts. If original checks matched, the fatal is `instrumented diagnostic completed; uninstrumented GPU acceptance disabled`. Evidence IO errors are reported immediately and composed into the final failure while other available evidence is attempted; no diagnostic can resume gameplay or create a closed completion receipt.

Only three revision-bound raw artifacts are authorized (all `SCE_O_EXCL`; no flip/crop/normalization):

| path after `ux0:data/celeste_native_room-<revision>` | bytes |
| --- | ---: |
| `-dash-probe-diagnostic.trail.rgba` (original post-mask) | 1,048,576 |
| `-dash-probe-diagnostic-markers.trail.rgba` | 1,048,576 |
| `-dash-probe-diagnostic-markers.trail.rgb` | 786,432 |
| **total, when all three writes succeed** | **2,883,584** |

Additional records use `guest_dash_probe_sweep revision/frame/instrumented/uninstrumented_proof/diagnostic_only/accepted_frame/fresh_export/native_probe_checks/full_completion`, followed by `sweep_begin`, `read phase/format/width/height/channels/bytes/sentinel/changed_bytes/sentinel_retained_bytes/zero_bytes/legacy_zero_initialized/histogram16`, `sample phase/point/channels/x/top/row/offset/expected_rgba/actual/mirrored_row/mirrored_offset/mirrored`, `original_result`, `sentinel_pair`, `marker_definition`, `pack_alignment`, `captured_tiles` or `diagnostic_error phase/cause`. Each line remains bounded to 767 bytes plus newline. No premask/pair arrays or normal PPM/accepted RGBA/sidecar are exported. All credit flags remain zero and the host helper must reject the run even if markers look correct.

| observation (only after accounting for retained sentinels/read errors) | hypothesis discriminated; not an automatic diagnosis |
| --- | --- |
| Contrasting paired sentinels retained | API did not overwrite those destination bytes |
| RGB markers present, RGBA absent | CPU-copy visibility/read-path distinction |
| Unscissored quad present, scissored quad absent | Scissor behavior |
| Clear present, both quads absent | FFP/projection/draw path |
| Premask opaque present, postmask zero | Alpha-mask path |
| Both paired reads zero, sentinels overwritten | FBO scene/shared-memory visibility remains unresolved |

Pinned vitaGL source, not host stubs, supports the API/path distinctions. Host tests cover ordering, bytes, classification, error propagation, marker bounds and state bookkeeping only; they do not validate GPU mathematics, rendering fidelity or the cause of prior failures. A later separately authorized runtime attempt and original-reviewer follow-up remain required.

### Nestable matrix state guard (correction 05)

Sweep 03 exposed a diagnostic guard defect, not proof of the original GPU/readback cause. Pinned vitaGL has a two-entry projection stack starting at counter 1. The old outer guard pushed it to 2; the nested premask read pushed again, received `GL_STACK_OVERFLOW` (`1283`), then popped despite the failed push. This explains the observed premask/restoration errors and missing original post-mask raw. Sweep 03's partial scissor/RGBA/RGB observations require a clean-state run before interpretation.

The state guard now reloads the already-saved projection/modelview values with `glLoadMatrixf`, then restores the saved matrix mode. Pinned `glGetFloatv` and `glLoadMatrixf` use inverse value-copy layouts and preserve all 16 values; neither requires a stack entry. No push/pop, SDK limit change, scissor/math/readback-backend change or additional read is introduced. Caller stack counters and active entries remain untouched even when the projection stack is already at its last entry.

State queries are checked before any mutation. A private checked state boundary restores and verifies values on success and on callback/readback/IO exceptions; it reports pending GL errors and combines cleanup failures with the original exception context. There is no fallible GL restoration hidden in a destructor. An actual restoration API failure or value mismatch remains a loud failure, never a claim that state was preserved.

The host model now enforces projection/modelview limits 2/32 with counters initially 1, returns real overflow/underflow errors without changing a failed push's depth, and stores actual non-symmetric 4×4 matrix values. Tests exercise both nested premask/marker paths, baseline and caller-occupied tops, both matrix modes, constructor errors, callback/IO/readback failures and restoration faults. This validates bounded state/error bookkeeping, not GPU rendering. Correction 04's seven reads, three raw filenames/sizes (2,883,584 bytes total), marker geometry, flags and always-instrumented nonzero termination are unchanged. No normal export or completion is enabled.

The exported frame includes one diagnostic ghost at logical `(200,16)` and an overlapping pair at `(240,16)`/`(248,16)`, all tinted `(51,137,191,191)`. In the single ghost, sample `(206,22)` is alpha128 and `(214,22)` is inner-union alpha192. Pair sample `(254,22)` overlaps the first inner-union with the second alpha128 region. Validate these against premultiplied source-over over the adjacent nonblack room background, allowing GPU byte quantization. Confirm actual gameplay ghost/body/foreground order and orientation too. These known semialpha samples distinguish inner hair/body union from between-ghost blending; an old 0/255 crop or host recording test cannot establish this proof.

No emulator, GUI, upload or physical run is performed by the implementation worker. Actual pinned-vitaGL GPU results remain required before acceptance.
