# Bounded static room hazards

The accepted static Player profile now composes immutable **Up/Left spikes**
with the existing ordered Hitbox/Grid collision world. This is headless hazard
compatibility and immediate death, **not a playable room or full Player.Update**.
No original game or Vita execution is performed.

## Native API and lifetime

```cpp
celeste::StaticSpike spike({-8, 0}, 16, celeste::SpikeDirection::up);
celeste::PlayerWorld world;
world.spikes = {&spike};
celeste::Player player(world, {0, 2});
player.frame(0);
bool dead = player.death().dead;
```

`PlayerWorld.spikes` is appended, so existing aggregate callers remain valid.
The list is explicit tracked order, separate from Solid/JumpThru bodies: spikes
are entity Hitboxes, not solid Grid cells. World, bodies, grids and spikes must
outlive Player and remain static. Null/duplicate spike pointers, nonfinite
positions, nonpositive sizes and unsupported directions fail explicitly. A
constructor-only collidable flag permits static enabled/disabled fixtures; there
is no mover, activation, entity loader or generic component framework.

The existing `default_static` profile remains the only profile. Bounds remain
off; Grab, Dash, other states, assists, holding and movers remain unsupported.
Observers are read-only instrumentation, not gameplay callbacks. `die(direction)`
is an explicit command outside a frame, not a snapshot setter; invoking it from
an observer throws. Death state, last hazard-frame probes and StateMachine/Actor
state are exposed read-only.

## Collision and frame ordering

- Up: `(width,3)` offset `(0,-3)`. After strict overlap, kill only when
  `Speed.Y >= 0` and **current hurtbox Bottom <= spike Bottom**.
- Left: `(3,height)` offset `(-3,0)`. After strict overlap, kill only when
  `Speed.X >= 0`. Zero qualifies; edge touch alone does not overlap. Target
  collidability is respected.
- Movement/hurt boxes are 8x11/8x9 at `(-4,-11)` and duck 8x6/8x4 at
  `(-4,-6)`. Both hurtbox bottoms are **Position.Y - 2**, not Position.Y.
- Grounded dash refilling checks the **current movement collider**, before
  NormalUpdate can change ducking. Any spike overlap denies the refill call,
  independently of lethal velocity or Bottom gates. Dashes 1/stamina 110 remain
  invariants; instrumentation records the call, not an invented depleted setup.
- Every static Up/Left spike has default `LedgeBlocker.Blocking=true`.
  JumpThru boost probes the movement box two pixels up and can be blocked even
  by a nonlethal ascending overlap. Climb-hop, DashCorrect and dash-specific
  WallJump reach branches remain excluded by the unchanged profile guards.
  Ordinary WallJump eligibility still rejects selection of unsupported WallJump.
- After H and V movement, save the movement collider, install the hurtbox, then
  check spike PlayerColliders in tracked order. Nonlethal overlaps continue.
  Lethal overlap restores the saved collider and **returns before frame-end
  `wasOnGround`**. The `removed` observation is instrumentation only. Normal
  completion restores the movement collider before `hazards` and `complete`.
  Static callbacks cannot replace a collider, so the source's conditional
  nonlethal restoration has only that reachable path. Exceptions propagate;
  there is no invented gameplay rollback/RAII restoration promise.

## Immediate Die and lifecycle boundary

The admitted profile has no invincibility or state 18. A first death sets Dead,
Depth -1000000, zero Speed, locks the state machine and disables Actor collision.
The retained observable event order is `corpse_created`, `corpse_added`,
`player_removed`; the supplied direction is retained at the corpse boundary.
Repeated `die` returns false without changing direction or adding events.
Further `frame` calls reject **before input mutation or observation**.

Native code does not create a real corpse. `corpse_created` marks an inert
**CORPSE CREATION BOUNDARY** only; neither PlayerDeadBody construction nor its
routine is claimed faithful. Stats/persistence, follower/booster/lookout services,
actual scene scheduling, corpse coroutine, freeze, wipe, reload, respawn and full
room lifecycle are excluded. The no-holding source Drop path is genuinely empty.
There is no fabricated death-to-respawn delay or subsequent dead-Player update.

## Private unchanged-source oracle

`read_hazard_sources.py` reuses the existing offline ILSpy 9.1.0.7988 and SDK
8.0.425/runtime 8.0.31. It pins the executable SHA256
`fd73f8a2311fa5737ded550cbad4b75c85b7686b36432f59185e940fcb65fcfe`.
`extract_native_oracle.py --domain hazards` extends the existing Player closure;
full source hashes and every unchanged block hash/range are recorded privately.

| Source | Additional inclusive ranges |
|---|---|
| Spikes | 11–17, 21, 48–51, 55–58, 64, 220–249 |
| PlayerCollider | 8–50 (complete Check and constructor, excluding DebugRender) |
| LedgeBlocker | 8–58 (complete methods) |
| Player | 2855–2908 (entire Die), 2997–3005 (entire Drop), 2826–2831 (RefillDash body) |
| Entity | 189–210 (Bottom) |

The existing Player frame blocks, notably 1594–1612, 1787–1790, 1898–1914 and
1944–1945, remain unchanged. The hazard pass and frame end share one wrapper, so
the actual lethal `return` cannot accidentally run SourceComplete. Static spike
constructor shells preserve the actual Up/Left collider and blocker cases;
PlayerCollider/LedgeBlocker methods are not rewritten C# algorithms. RefillDash's
unchanged body has a structural instrumentation wrapper counting calls. Tracked
iteration and callback wrappers record checks/overlaps without changing results.

Die remains whole, including its guards and branches. Isolated counters stand
in for stats; empty followers, Holding, LastBooster and Lookout are validated
absence, not globally cosmetic services. Unsupported paths throw. Shake/rumble/
sound are inert presentation shells. The inert corpse shell asserts the source's
immediate flags already hold and records direction/ordered scene events. These
synthetic scalar/input bindings are **not original CIL or full-runtime proof**.

## Actual selected room and checks

`prepare_room_hazards.py` reuses BinaryPacker and the fixed executable/map hashes
from [static tilemap preparation](NATIVE_TILEMAP.md), explicitly selecting room
`1`. It privately decodes four Up and one Left spike in map order. Ordinary
non-cheat/non-debug save data with unlocked modes < 3 keeps the golden gate
closed; raw berry data never creates a native entity. No automatic startup
selection or general entity conversion is claimed.

Actual probes include **all five hazards and the merged global mask**, not an
isolated-room shortcut. Preparation verifies the mask against the accepted
global construction and hashes the hazard data, fixture and mask in provenance.
Raw map/spike data and original C# stay under `.audit`, never in tracked fixtures.

```sh
python3 -B scripts/read_hazard_sources.py
python3 -B scripts/check_native_oracle.py --domain hazards --compile-only
/usr/bin/cmake -S . -B .audit/native-room-hazards/host -DCMAKE_BUILD_TYPE=Release
/usr/bin/cmake --build .audit/native-room-hazards/host -j2
/usr/bin/ctest --test-dir .audit/native-room-hazards/host --output-on-failure
python3 -B scripts/check_native_oracle.py --domain hazards --native .audit/native-room-hazards/host/native_hazard_trace_runner
python3 -B scripts/prepare_room_hazards.py
python3 -B scripts/check_native_oracle.py --domain hazards --native .audit/native-room-hazards/host/native_hazard_trace_runner --fixtures .audit/native-room-hazards/prepared/hazards.fixtures
```

Synthetic coverage: 21 scenarios/25 operation rows, plus 11 actual-room probe
cases/11 rows. Each row has 39 exact fields, including float32 bits, input,
collider identity, death flags, ordered scene events, checked/overlapping spike
identities and ordered frame phases. Both traces independently satisfy strict
fixture-derived grammar/coverage before equality. Negative tests reject even
identically malformed, missing, duplicate, reordered, foreign or postdeath-phase
rows. The old Player 51-field validator and all prior domains remain unchanged.

Final exact-commit commands, immutable snapshots/log hashes and results live in
`.audit/native-room-hazards/finalchecks.json`. Release/sanitizer CTest, all prior
source differentials, all-cell mask/actual Player regressions and the existing
VitaSDK `BUILD_TESTING=OFF` static-library build are required checks. They prove
bounded host compatibility/static compilation only, not Vita execution,
performance, rendering/audio, respawn or a playable first room.
