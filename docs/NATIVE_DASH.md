# Bounded native Player Dash

This extends [Normal/Jump](NATIVE_PLAYER.md) with default-inventory 8-way Dash
between Normal (0) and Dash (2), on ordered static Hitboxes/Grids and static
Up/Left spikes. It is not the original CIL, full Player/Engine, full game,
presentation parity, or a physical-Vita performance result.

## Input and clock

```cpp
celeste::PlayerInput input;
input.aim_x = 1;
input.aim_y = -1;
input.dash_button = {true, true};
player.frame(1.0f / 60.0f, input);
```

`aim_x/aim_y` are independently resolved digital axes in [-1,1], not analog or
hardware threshold parity. Neutral aim uses current facing, preserving its
signed-zero Y. `dash_button` has the same .08-second VirtualButton buffer as
Jump. The existing `jump.disabled` is the shared MInput-disabled sample for
both buttons; hardware/debug/crouch-dash mapping is excluded. The old unresolved
`PlayerInput.dash` flag still rejects before mutation, preserving its old API
contract; new gameplay uses the explicit sampled `dash_button` instead.
Direct non-Normal `request_state` calls still reject: Dash is entered by input.

`FrameClock` takes a caller-provided **raw float**, validates it, and computes
`(raw * 1) * 1`: canonical TimeRate/TimeRateB are fixed at 1. Both buttons update
before the freeze gate. A positive freeze timer subtracts raw dt, clamps to zero,
and skips the entire scene tick **including its zero-crossing tick**. The next
call resumes. A zero-dt call remains valid and does not advance positive freeze.
DashBegin's .05-second freeze does not abort its entry frame.

The source originally converts `ElapsedGameTime.TotalSeconds` from TimeSpan to
float. This boundary deliberately excludes GameTime/TimeSpan tick conversion,
other Engine systems, and assist freezes; it is not a full Engine-clock claim.

## Gameplay boundary

Entry consumes/spends, ends Normal, zeros velocity, and primes the unchanged
scheduler-equivalent coroutine with a null yield. On the first resumed scene
tick DashUpdate precedes launch. Launch uses the latest aim at 240, retaining
faster same-sign X. The .15 coroutine wait consumes its crossing tick. Exit sets
AutoJump/zero AutoJumpTimer, uses 160 for non-downward directions, multiplies
upward Y by .75, and returns through DashEnd/NormalBegin. Ground clears AutoJump;
ordinary Jump clears attack/glider timers. Cooldown/refill/attack timers are
.2/.1/.3; refill crossing waits the following tick. Trails/glider bookkeeping
is retained, but trails, particles, audio, shake, slash and displacement are not
rendered or otherwise claimed faithful.

Movement remains H then V then hurtbox hazards. The added collision paths retain
ground duck correction, downward-before-upward H corner search 1..4, downward
edge correction, upward reach 4→5 while attacking, snap-3 and JumpThru snap-6,
with hurtbox spike blockers. Default inventory **enables DreamDash**. The private
oracle executes its unchanged real guard/body with an explicitly validated-empty
DreamBlock collection. Native `StaticWorld` cannot represent DreamBlocks, water,
SwapBlocks, movers, holding, booster/listener hooks or other gameplay services;
these absent branches are reduced by representation, not by disabling inventory.
The [jump-family extension](NATIVE_WALL_JUMPS.md) supports selected eligible
SuperJump/WallJump/SuperWallJump calls. An ordinary buffered Jump without that
eligibility is retained, including across freeze/exit. Climb remains excluded.

## Source oracle and verification

Only private extracted source is compiled, never the original game runtime.
The pinned PC 1.4.0.0 executable SHA256 is
`fd73f8a2311fa5737ded550cbad4b75c85b7686b36432f59185e940fcb65fcfe`.
Existing Player/Actor/Grid/hazard/Scheduler/VirtualButton extraction is reused.
Additional unchanged ranges:

| File | Inclusive lines |
|---|---|
| Player | 1090; 1457–1460; 1791–1794; 4191–4567; 4569–4576 |
| Actor | 134–154 |
| Input | 103–135; 331–373 |
| Engine | 227–229; 264–276 |
| MInput | 1380–1424; 1437–1443 |
| Celeste | 152–162 |

Synthetic glue supplies raw float dt, ordered scene calls and stable sampled
bindings. Scalar vector/math and explicit world/presentation shims are not FNA.
The manifest hashes full source files and every extracted block; the checker
independently verifies that each selected block is byte-identical and present
unchanged in generated source. All decompiled material remains beneath `.audit`.

```sh
python3 -B scripts/prepare_dash_oracle.py
/usr/bin/cmake -S . -B .audit/native-dash/new-host -DCMAKE_BUILD_TYPE=Release
/usr/bin/cmake --build .audit/native-dash/new-host -j2
/usr/bin/ctest --test-dir .audit/native-dash/new-host --output-on-failure
python3 -B scripts/check_native_oracle.py --domain dash \
  --native .audit/native-dash/new-host/native_dash_trace_runner \
  --output .audit/native-dash/new-source-run
```

The offline private SDK/runtime remain 8.0.425/8.0.31; preparation reuses the
existing ILSpy with `--disable-updatecheck`, with no downloads. Fresh `--output`
paths preserve prior oracle evidence. Compile-only proves closure, not behavior.
Differential traces expose phases, raw/scaled/freeze clocks, both buffers,
state/coroutine scheduling, timers, motion, inventory, collisions and hazards;
comparison is exact float32 bits, not epsilon. Fixture-declared phase/callback
coverage is checked independently before equality. Other-domain and actual
room/mask tests remain separate; only the eligible Normal WallJump rejection
changes to a supported outcome.
The extended Dash trace adds force/low-friction timers, launched state, glider
direction and stamina (77 fields); the original selected-jump rejections now
assert supported outcomes, while Grab still rejects before mutation.

See [diagnostic feedback](NATIVE_VITA_DIAGNOSTIC.md) for Square Dash, safe isolated
input, the single direct native-frame export, provenance and guest logs. Parent
visual review and independent integration review are separate acceptance gates.
