# Bounded static Climb

`src/native/player_climb.cpp` supports coherent Climb (1), ClimbJump, Slip,
ClimbHop, blocked ledges and delayed hop motion alongside Normal (0), Dash (2)
and the jump family. Worlds remain ordered, immutable Hitbox/Grid solids and
JumpThrus with static Up/Left spikes. This is not full Player/Engine, original
CIL/FNA execution, ECS, movers, nonzero lift, carrying, wind/water, presentation
parity or hardware/performance proof.

## Input and behavior

`PlayerInput.grab` is **held**, not entity holding. It has zero buffer and shares
the sampled `jump.disabled` MInput gate. Only default Hold mode is supported;
Toggle/Invert and hardware mapping are excluded from the kernel. The unresolved
legacy `dash` bool still rejects before mutation. Direct state requests remain
Normal-only; Climb/Dash entry must be input-driven.

Normal Grab precedes Dash. Climb checks Jump, Dash, release and lost wall before
motion/drain/exhaustion. Entry scales Y by .2, waits .1 and snaps up to two pixels
toward its wall. Climb suppresses facing changes. Grounded Climb refills before
costs, so grounded idle can finish below 110. Up costs 45.454544/s, idle 10/s,
down zero. Air ClimbJump costs 27.5 without clamping; grounded ClimbJump is free.
The `<20` tired predicate includes a pending 27.5 refund, unlike the `>0` jump
selector. Wall boost decrements its timer and checks **previous** moveX, including
the crossing tick, before ground recovery and current input resolution. Jump
helpers and NormalEnd clear boost; NormalEnd also clears hop wait.

Slip uses real half-open **point** queries, never zero-sized rectangles. Its
second point applies addY twice: Top+4/Top for zero, Top+3/Top-2 for -1. Right
uses TopRight X; left uses TopLeft X-1. Grid bounds are checked before truncating
nonnegative cell coordinates; negative world positions remain valid. The source
Hitbox point upper edge is AbsoluteLeft+Width, which can differ in float operation
order from its ordinary rectangle Right edge.

Hop selects the first **shifted full Player Hitbox** Solid, retaining its actual
stable Body pointer and position. It is not a point lookup or fake-null identity.
The static profile excludes movement of that solid; a changed retained position
throws. Ordered lists include the actual merged SolidTiles Grid. `[Tracked(false)]`
means no inherited propagation of that exact tracker category, not untracked:
SolidTiles is included in the inherited Solid category. No full original scene
population/Tracker lifecycle or dynamic-scene ordering claim is made.

Upward stopping retains ceiling OR (blocked hop AND Slip(-1)); rising lost-wall
hop still executes. Real spike LedgeBlocker and JumpThru guards and H→V→hurtbox
hazard order remain. Holdables, WallBoosters, seeds/followers and ClimbBlockers
are validated absent in the private oracle. Unsupported gameplay services throw;
conveyor branches are not cosmetic no-ops. Cosmetic sound/sweat/rumble are inert.
Source noWind/fastJump bookkeeping has no supported service effect in this profile.

## Source and checks

PC 1.4 executable SHA256:
`fd73f8a2311fa5737ded550cbad4b75c85b7686b36432f59185e940fcb65fcfe`.
Additional unchanged Player blocks: 2644–2675, 3552–3555, 3882–4177; preamble
extends through 1695. Existing tired/refund/Normal/Dash/jump/ledge bodies are reused.
Point closure extracts Scene 356–367, Entity 893–896, Collide 103–110/333–340,
Hitbox 161–164 and Grid 409–416. Scene SHA256:
`741b780cc262406f1c0b6cc862af5656de6698bd594068c77ddfbefa08bdf71a`.
All private source, body/file hashes and offline extraction receipts remain in
`.audit`; helper preparation preserves historical receipts. SDK/runtime remain
8.0.425/8.0.31; no downloads or tool installation.

```sh
python3 -B scripts/prepare_dash_oracle.py --climb
python3 -B scripts/check_native_oracle.py --domain dash --climb-family \
  --native FRESH_BUILD/native_climb_trace_runner --output .audit/native-climb/FRESH
```

The opt-in schema retains all 77 historical Dash fields and appends 26 input,
climb/boost/hop/tired fields. Independent fixture grammar, input samples, ordered
phases/callbacks and nine behavior groups are required before exact float32-bit
equality; equal empty traces cannot pass. Point probes separately distinguish
fractional/negative origins, included left/top, excluded right/bottom, cell
boundaries and noncollidable targets. Hop probes distinguish point vs rectangle,
insertion order and collidable filtering. Original seven schemas and jump-family
checks remain. Only obsolete no-wall Grab rejections become supported; explicit
legacy Dash rejection keeps that coverage.

## Actual first room

`native_diagnostic_replay MASK HAZARDS --climb` calibrates Left+Cross, release
Cross, held L on descent, Up, hold, release and landing before UI work. Vita L is
`SCE_CTRL_LTRIGGER` (SDK `psp2common/ctrl.h:40`); Cross/Square/Triangle/Start and
the old `--after-wall-jump` mode remain.

```sh
python3 -B scripts/feedback_native_room.py --after-climb \
  --output .audit/native-room-vita/FRESH
```

`--after-climb` is mutually exclusive with post-WallJump/default-spawn capture;
frame-only cannot request deferred capture. Readiness does not wait for an image.
Exactly one native export requires actual airborne state 1, held Grab, drained
stamina and ascent, then logs hold/release/landing and retains Dash/death/reset/exit
smoke. The receipt records actual frame/state/stamina/grab/kind and revision.
Readback stays GL_BACK→glFinish→CPU RGBA→closed original PPM→swap, with lossless
PNG conversion and hashes. No OS/window capture or synthetic canvas is used.
Fresh private OpenGL 1x config keeps surface sync enabled; shared configuration,
toolchains, original assets and foreign processes remain untouched. Input is
PID/focus/preheld/owned-key checked and released before owned-host termination.
Guest completion does not resolve historical emulator post-exit crashes or prove
a healthy host. Parent visual review and independent integration review remain
separate acceptance gates.

The application-only `src/vita/layout.ld` leaves a minimum 4 KiB gap before
`.init_array` for `vita-elf-create`'s appended SCE metadata. The first clean Climb
build exposed a 1,848-byte gap versus 3,132 required bytes; a private relink proved
the gap correction before changing app configuration. No shared linker/toolchain
or runtime algorithms are patched. ELF/SELF/VPK validation and guest execution
remain required after this layout change.
