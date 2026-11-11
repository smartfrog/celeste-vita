# Bounded native Player locomotion

`src/core/player.hpp` composes the accepted Actor, StateMachine and
VirtualButton. This is Normal locomotion plus ground/coyote Jump on synthetic
ordered static Hitboxes, now also immutable target Grids (see
[native static tilemap](NATIVE_TILEMAP.md)). It is **not full Player.Update,
game runtime or a playable port**. It has no external native dependencies.

The subsequent [bounded Dash extension](NATIVE_DASH.md) adds sampled Dash,
independent digital aim, freeze/input clock and Normal↔Dash transitions. The
Normal-only oracle/profile invariants described below remain its historical
regression boundary; they do not describe the extended native default API.
The [jump-family extension](NATIVE_WALL_JUMPS.md) also enables eligible WallJump
in the Normal regression oracle; its force/low-friction timers are no longer
zero invariants. The later [static Climb extension](NATIVE_CLIMB.md) supports
Climb, held Grab, stamina use and wall boost in the current native API.

## Supported profile and API

```cpp
celeste::Body floor{{-100.0f, 0.0f}, celeste::Hitbox{200.0f, 8.0f, {}}, true};
celeste::PlayerWorld world{{{&floor}, {}}, {&floor}};
celeste::Player player(world);
celeste::PlayerInput input;
input.x = 1;
input.jump = {true, true};
player.frame(1.0f / 60.0f, input);
```

- Default inventory, ordinary core/gravity, no assists, space, wind, water,
  holding, movers/lift, triggers or platform gameplay hooks. The bounded
  [static Up/Left hazard extension](NATIVE_HAZARDS.md) adds spikes, hurtbox death,
  refill denial and their boost blockers separately. Its only accepted
  profile is `default_static`; other profile values and non-Normal state
  requests throw. Grab, Dash and debug-override requests throw before input
  mutation. Ordinary disabled sampled input remains supported.
- `PlayerWorld.collision` is the accepted ordered static world. Its `safe_ground`
  list explicitly identifies safe platforms; others are unsafe. Safe identities
  must belong to that world. Bodies/world must outlive Player and remain static
  during simulation. This is not platform activation, carry, push or lift logic.
- Bounds enforcement is always **off**. Int32 fixture bounds remain available
  for the source's asymmetric/strict `ClimbBoundsCheck`.
- Spawn truncates to int32 then float32, facing starts right, and lifecycle
  initialization enters Normal through StateMachine, invoking NormalBegin
  (`maxFall = 160`). Optional finite initial speed is a synthetic kinematic seed,
  not an arbitrary gameplay snapshot or proof that another state can reach it.
  No timer, collider, inventory, state-machine or Actor mutation API is exposed.
- Default dashes remain 1 and stamina 110: no supported operation spends either.
  Ground refilling follows the static Solid/outside-JumpThru condition and is
  denied by movement-collider overlap with static spikes. There is no general
  refill/hazard/platform callback stub. Depleted-dash snapshots and
  depleted stamina from excluded gameplay are not accepted setup inputs.
- LiftSpeed is zero. Jump preserves the zero-vector addition and therefore
  `LaunchedBoostCheck`'s actual result/reset is false. AutoJump, dash/wall-boost,
  force-move/hop, dream-jump and other-state timers/flags are zero/false
  invariants, not accepted snapshots. Wall slide and wall-speed retention are
  supported Normal behavior, not excluded with Climb.
- Nonfinite spawn/speed/delta/world values, invalid bounds/axes, negative delta
  and overflowing delta scaling fail explicitly. Validation precedes input
  update. Computed movement also retains Actor's checked conversion rules.
  Observer exceptions propagate; mutations are not transactional. Recursive
  `frame` calls throw. Observers are read-only instrumentation, not gameplay hooks.

Standing movement/hurt boxes are respectively 8x11 at (-4,-11) and 8x9 at
(-4,-11); duck boxes are 8x6 at (-4,-6) and 8x4 at (-4,-6). Jump consumes the
**buffer**, not the raw press, and does not itself unduck. An airborne press
without ground grace still buffers. Real WallJumpCheck eligibility is preserved;
eligible WallJump is now supported by the jump-family extension. Grab is rejected up front,
so ClimbJump cannot be selected through an accepted input.

## Frame and source boundary

The observation order is input update, previous-position/ground snapshot,
timers/input/facing/retention, scheduler NormalUpdate, overlap-JumpThru upward
boost (unless a static spike LedgeBlocker denies it), falling unduck, H movement,
V movement, hurtbox hazard pass, then `wasOnGround` only on nonlethal completion.
Collision before/after observations occur synchronously
inside their movement phase. Ground is **pre-movement**: landing does not refresh
coyote grace until the following frame. Stand assistance searches 4 to 1,
right before left, using MoveH subpixels. Ceiling correction searches left
before right, directly changes Position and returns before clearing speed;
head-bump variable-jump cancellation uses strict `< 0.15`.

The private oracle extracts unchanged selected source rather than rewriting a
C# motion algorithm or loading the original game. It combines the accepted
Actor/Hitbox, complete StateMachine/Coroutine and complete VirtualButton with
minimal linked shims. No whole Player.Update dependency closure is attempted.
PC input SHA256 is
`fd73f8a2311fa5737ded550cbad4b75c85b7686b36432f59185e940fcb65fcfe`.
Player source SHA256 is
`47413e0a774802c6dac9baff96aca6f6fda01edd8f28b1dd9bb86e0075cd4d9a`;
PlayerInventory source SHA256 is
`fca9bed434019cba9bbe937e18e5d170c420cbbe51740926a4e9d70aeac7ec5f`.
The manifest additionally hashes every inclusive extracted range:

| Player source lines | Purpose |
|---|---|
| 605–613; 934–954; 956–1044; 1048–1088; 1092–1102 | Boxes, control/inventory/lift/duck/dash properties |
| 2353–2362; 2436–2478; 2521–2546 | LaunchedBoostCheck, complete Jump and WallJumpCheck |
| 2824–2832; 2910–2929 | RefillDash, unduck/duck checks |
| 3135–3473 | Complete H/V collisions and actual DreamDashCheck guard/body |
| 3531–3550; 3557–3843; 4179–4189 | Normal begin/end, climb guards, complete NormalUpdate, boost blocker check |
| 1431; 1437; 1499–1541; 1542–1550; 1555–1682 | Previous position, ground and movement preamble |
| 1787–1790; 1795–1798; 1799–1802; 1803–1806 | Boost, unduck, H then V |
| 1898–1914; 1944–1945 | Empty hurtbox/hazard slot and frame-end flags |

Additional Entity query ranges are 531–540, 551–581, 648–658, 762–776;
Collide ranges are 8–101. Remaining Actor/Collider/Hitbox and scheduling/input
ranges/hashes are the accepted ones documented in the linked native guides.
PlayerInventory 6–37 is extracted unchanged. Initialization is explicitly
synthetic glue based on Player 1116–1175 and 1277–1328 with IntroType.None,
not an extracted full constructor/scene lifecycle.

FNA substitutes only scalar two-float vector operations/length-squared/angle,
Lerp and Approach. Presentation audio/rumble/dust/sprite-scale shells are inert.
The synthetic Aim is independently neutral, so its facing fallback supplies
lastAim; hardware Aim resolution and later-state use of lastAim are excluded.
Unsupported actions throw; only validated-absent entity/component categories
are empty. The complete real DreamDashCheck short-circuits because DashAttacking
is false, **not** because Default inventory disables DreamDash (it enables it).
The original Player oracle retains its validated-empty hazard/blocker collections;
the separate hazard domain extends them with unchanged source methods.

Stats, replay/chaser history, strawberry collection, idle services, camera,
carry, triggers, water transitions and bounds services are **excluded services**,
not globally cosmetic no-ops. Earlier assist/other-state timers are excluded by
the profile invariants. The source Jump's TotalJumps increment uses an isolated
oracle counter; no native persistence/stat claim is made. Presentation-only
fields touched by retained source blocks are not native gameplay state.

## Verification

```sh
/usr/bin/cmake -S . -B .audit/native-player-normal/host \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=/usr/bin/c++
/usr/bin/cmake --build .audit/native-player-normal/host -j2
/usr/bin/ctest --test-dir .audit/native-player-normal/host --output-on-failure
python3 -B scripts/check_native_oracle.py --domain player --compile-only
python3 -B scripts/check_native_oracle.py --domain player \
  --native .audit/native-player-normal/host/native_player_trace_runner
```

The oracle uses the existing private SDK8.0.425/runtime8.0.31 offline. The
compile-only gate establishes dependency closure, **not behavior**. Exact
differentials compare 51 fields, including float32 bits, important state,
collider identity and ordered phases/callback payloads. Each trace independently
must satisfy strict grammar and fixture-derived scenario/frame/input/phase/hit
coverage before equality. Callback annotations declare coverage, not results;
repeated hits are allowed. There is no fixed trace hash/count or epsilon test.
Fixtures include synthetic overlapping/zero-width boxes to distinguish search
priorities; these are not claimed reachable room geometry or gameplay states.

Private compile/red-green/final exact-commit evidence lives under
`.audit/native-player-normal`; shared oracle outputs under
`.audit/native-oracle/player` can be refreshed by later checks. Source, SDK,
game files and build artifacts stay uncommitted. The existing VitaSDK static
build with `BUILD_TESTING=OFF` establishes compilation only, **not Vita execution,
performance, original CIL equivalence or full-game fidelity**. The subsequent
bounded Grid/global-mask and actual-room headless checks are documented separately.
