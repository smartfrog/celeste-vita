# Bounded native jump family

`src/native/player_jumps.cpp` adds SuperJump, WallJump and SuperWallJump to the
existing Normal (0)/Dash (2) static Hitbox/Grid/Up/Left-spike profile. It does not
add Climb, movers, nonzero lift, full Player/Engine, presentation parity or
original CIL execution. Existing input/world APIs are unchanged. Grab still
rejects; stamina remains 110 and wall boost/lift remain zero.

Normal selects grace Jump, then right wall, then left wall. Its SuperWallJump
requires attack plus the real upward-angle guard. Dash retains JumpThru
correction before horizontal SuperJump, then angle-selected wall jumps. Returning
Normal runs DashEnd/NormalBegin and cancels the coroutine, including a buffered
SuperJump before launch. SuperJump retains standing/duck speeds and facing;
the glider direction intentionally does not mirror with facing.

Low-friction stop decrements before ground detection. Positive force time
subtracts and overrides effective moveX on its crossing tick, before facing,
aim and retention. Neutral effective moveX WallJump creates no force; nonzero
creates .16 seconds. SuperWallJump does **not** assign the advertised .2 force
constant or clear inherited force/low-friction state. Reach remains three, or
five for upward attack unless the source spike guard shortens it. Existing
variable-jump ceiling threshold, H→V movement and hurtbox hazard order remain.

Jump kind/count are read-only native diagnostic instrumentation; they are not
new input, mutable gameplay snapshots or source persistence counters.

## Source and numeric proof

Pinned PC 1.4.0.0 executable SHA256:
`fd73f8a2311fa5737ded550cbad4b75c85b7686b36432f59185e940fcb65fcfe`.
Unchanged Player ranges 2480–2519, 2548–2605, 2607–2642 and 1461–1464 join the
existing preamble 1632–1666, selectors, guards and collision closure. Pinned
`Monocle.Calc.cs` SHA256 is
`53ba72dc68ea5f6fed05e5394dc2fa0e867ea9317cb1f3271bd0c9c6fec38669`;
its unchanged AngleToVector is lines 854–857. New C# shims only permit zero
Actor/Platform LiftSpeed assignment, inert wall sound lookup and isolated
TotalWallJumps. No Player algorithm is rewritten in shims.

The first private compile/numeric checkpoint is preserved under
`.audit/native-wall-jumps/first-compile/`. SDK/runtime 8.0.425/8.0.31 compile only
the extracted source. Actual angle bits `bf16cbe4` and `bf490fdb` match native
float operations and double cos/sin narrowed before float length multiplication:
respectively `(3f54db31,bf0e39da)` and `(3f3504f3,bf3504f3)`. No epsilon or
replacement vector constants are used in native code. This is bounded host
numeric evidence, not execution of the original FNA/runtime or hardware proof.

```sh
python3 -B scripts/prepare_dash_oracle.py
python3 -B scripts/check_native_oracle.py --domain dash --jump-family \
  --native PATH/native_dash_trace_runner --output .audit/native-wall-jumps/FRESH
```

`tests/native/jumps.fixtures` covers nine families in 25 scenarios. Its comparator
requires concrete action/timer/selection checkpoints independently of equality,
plus fixture-derived phase/callback completeness. Traces compare 77 exact fields.
Existing seven domains, full mask/loader and actual-room Player/hazard tests
remain separate regressions. Release/sanitizer and exact-revision evidence are
private; independent parent review/integration are separate gates.

## Actual room feedback

`native_diagnostic_replay MASK HAZARDS --wall-jump` calibrates Left+Cross from
`(19,144)`, release at frame 4 near x=13 and re-press at frame 5. On the unchanged
merged mask it launches `(130,-105)`, clears the Jump buffer, sets .2 variable
time and .16 forced-right time. The same 14-frame full-mask/spike input sequence
is compared against unchanged extracted C# separately.

```sh
python3 -B scripts/feedback_native_room.py --after-wall-jump \
  --output .audit/native-room-vita/FRESH
```

This opt-in bool replaces the default spawn export with exactly one export after
an actual input-driven WallJump. Startup/input readiness never waits for that
image. Geometry-based airborne-near-wall readiness coordinates Cross release/
re-press; subsequent forced-right motion is separately logged. The helper then
manually resets and retains the genuine Jump/Dash/death/reset/Start smoke.
The direct GL_BACK→glFinish→CPU RGBA→closed PPM→swap pipeline and lossless PNG
conversion are unchanged; no OS/window capture is used. Receipt records actual
frame, position, velocity, state, kind, stage and revision; host feedback joins
the verified VPK hash. Parent must open the PNG. No hardware/performance or
healthy-host claim follows from a successful guest log.
