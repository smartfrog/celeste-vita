# First Up transition: source contract candidate

This is **source-only**, pending coordinator acceptance, simplification and fresh
independent review. It does not implement or authorize a native transition.
The frozen Dash05 worktree and all existing source-oracle recipes are unchanged.

## Fixed experiment

`tests/native/room-transition.inputs.json` contains only a seed and 16 legal
keyboard-input runs: 514 frames at float32 `1/60`, seed 1. C is Jump, Z is Climb,
and the arrow keys are Dpad. No Dash is needed. The route was derived through
bounded fresh source replays, then frozen; replay has no feedback or state tape.
There are no position, speed, state, camera or room writes in the input driver.
Only original gameplay bodies move the player and camera during execution.

Original-source observations, with zero-based frame numbers:

| Frame | Observation |
| --- | --- |
| 0 | Room 1 natural spawn `(19,144)`, original Respawn14 lifecycle |
| 373, before EOF | Player `(276,5)`, CenterY < room.Top; original NextLevel delegate pending, room 1, no coroutine yet |
| 373, after EOF | Same room and player; original TransitionTo creates the coroutine |
| 374 | Coroutine calls original LoadLevel(Transition); room 2 commits at world bounds `(240,-184,320,180)` |
| 374–412 | Original transition movement and camera easing; destination Strawberry does not update |
| 413 | Original outgoing removal/commit and OnTransition effects; coroutine clears, camera `(240,-184)`, respawn metadata `(264,-24)` |
| 448 | Actual descending JumpThru landing: position `(276,-24)`, Speed.Y zero |
| 468 | First new legal grounded Jump after landing |
| 513 | Normal controlled landing `(263,-24)`, not a forced destination spawn |

The Level, Player, PlayerSprite and PlayerHair identities persist across the
transition. Seven outgoing entities are removed, including the five room-1
spikes. Room 2 retains its JumpthruPlatform, three spikes, Spring and Strawberry.
Their reached constructor/Added/Awake/update closure executes original bodies;
the Spring uses inherited Entity.Update. Spring contact, berry collection and
unreached callbacks remain throwing guards, not neutral stubs.

`OnGround()` can be true during an upward JumpThru crossing (frame 419). That is
not called a landing: the validator also requires zero vertical speed, producing
frame 448. This distinction has its own observed-source red/green test.

## Provenance and execution boundaries

`scripts/prepare_room_transition_oracle.py` uses the accepted source8 extraction
and manifest without modifying or rebuilding that checkpoint. It promotes only
specific byte-pinned original spans and necessary support. Original gameplay
bodies, source state callbacks, coroutine bodies and ordering are not replaced
with mirrored results. Every added source span must be present byte-identically
in generated private files; missing or ambiguous guarded replacements fail.

The original map member is `Content/Maps/1-ForsakenCity.bin`, SHA-256
`ace1892261c03aa766f45aaa38cb2cd60a8823c34eda673f5b2ed8ab31c890ab`.
The supplied field-only MapData contains authored rooms `lvl_1` and `lvl_2` in
their original order. Original LevelData constructs and normalizes them.
Only decals and object-tile presentation are stripped; entities, triggers and
solid layers are retained. Bounds have a declared 64px tile-bake margin.
This is not a complete chapter map or execution of MapData.Load/LevelLoader.

Original LevelLoader lines 95–274 build global SolidTiles from the supplied
rooms, using the source PushRandom/PopRandom scope. This is distinct from
room-scoped entities: original Level.TransitionRoutine retains persistent/global
entities, loads incoming entities, and removes outgoing entities only after the
transition. No reload swap or flattening of room entity lifetimes is used.

Relevant original roots are Level.NextLevel (2945–2954), TransitionTo and
TransitionRoutine (1486–1640), Player.BeforeUpTransition (2332–2351),
Player.TransitionTo/OnTransition (2282–2308), Level.Update's TransitionUpdate
branch (1887–1895), and the original Scene.AfterUpdate EOF dispatch. Their full
source hashes and exact selected spans are in the private profile receipt.

One additional dependency, PufferCollider, is decompiled in memory by the
existing pinned offline ILSpy with update checks disabled. Only its pinned
class/fields/constructor plus a throwing Check declaration are emitted into a
transformed extraction. No raw original source file, asset, DLL or tool runtime
is copied. The original constructor's assignment is preserved, not corrected.

The observation driver transplants the accepted original Engine freeze/Scene
fragment (264–276), splitting it only between unchanged source statements for
read-only observations. Gameplay bodies are unchanged. Identity IDs use a
reference-equality dictionary outside game objects. Reflection only reads
private fields and coroutine locals, including a captured display-class field.
The observer never calls transition, loading, movement or state callbacks.

The profile executes original SaveData.StartSession once during initialization,
before LoadLevel, so Strawberry.CheckStrawberry reads the actual current session.
This is not a full startup claim. As in the accepted profile, raw keyboard state
and selected original virtual-input updates are supplied explicitly; full
Engine.Update/MInput device polling, hardware input and startup RNG parity are
not claimed. Rendering is not executed. Existing declared inert audio caches,
managed Linux platform identity and recording/graphics exclusions remain.

## Recorded contract and negative coverage

Each frame records input samples/buffers, five phase snapshots, persistent
identities/owners, state and actor remainder, camera and coroutine locals,
pending EOF delegates, entity/component identities/tags/births/removals, source
clocks/counters, respawn metadata, and RNG state hashes. RNG leaf observations
include temporary original room-seed scopes. The persistent RNG is restored;
there is no false "never reseed" requirement. The inherited Calls field counts
its NextDouble/Next(max) overrides, not every conceivable Random overload; the
hash also covers the complete private SeedArray and indices.

The comparator requires the natural lifecycle, deferred request, next-tick
incoming load, original easing, outgoing removal, target entities, landing and
new Jump. It compares all selected observations using exact integer/scalar and
float32-bit equality. Mutations cover immediate switching, recreated identities,
clock/counter changes, missing room origin, incorrect transition filtering,
movement, outgoing leaks and native-attempt bypass. These are mutations of an
executed source recording, not native-generated expectations.

The source recording's parsed JSON types are authoritative. Integer observations
are compared exactly, without float32 conversion; booleans are not numbers.
Mixed integer/float wire forms are rejected even when numerically equal. Only
two floating observations use float32-bit comparison, allowing decimal spellings
that represent the same float32 value, but no epsilon or differing float32 bits.

Room/session/save death counters are zero in this death-free fixture. A changed
observable count is rejected, but omitting a zero-to-zero reset is not
distinguishable dynamically here. The original reset assignment is byte-pinned;
this is not claimed as a nonzero death-history reset test. FreezeTimer stays
zero and Dash is unused; existing accepted freeze/Dash evidence is not silently
relabelled as this fixture's coverage. No eight-family audit is reopened.

The generated assembly compiles the exact accepted module-initializer native
guard. Its source binding, compiler input list and compiled artifacts are pinned.
Separate fresh diagnostics check native ABI identity, throwing native resolution,
duplicate resolver rejection and a still-unsupported Spring collision. The last
uses an uninitialized object only as a negative guard sink, never as route input.

## Reproduction

Use an existing canonical x64 SDK; do not copy tools into this worktree.
All output directories below must be fresh.

```bash
python3 scripts/prepare_room_transition_oracle.py \
  --accepted /home/fred/projects/celeste-vita/.audit/native-player-death-respawn/source-contract-reviewed-bd7ac7f8/shared/generated \
  --manifest /home/fred/projects/celeste-vita/.audit/native-player-death-respawn/source-contract-reviewed-bd7ac7f8/producer/build-manifest.json \
  --legacy-root /tmp/opencode/celeste-vita-death-source-up \
  --archive /home/fred/projects/celeste-vita/game/celeste-linux.zip \
  --output .audit/native-room-transition/source-contract-01/NEW-profile \
  --sdk /home/fred/projects/celeste-vita/.audit/native-oracle/tools/dotnet-8.0.425-linux-x64/dotnet

python3 scripts/run_room_transition_probe.py \
  --profile .audit/native-room-transition/source-contract-01/NEW-profile \
  --sdk /home/fred/projects/celeste-vita/.audit/native-oracle/tools/dotnet-8.0.425-linux-x64/dotnet \
  --content /tmp/opencode/celeste-vita-death-source-up/.audit/native-player-death-respawn/tile-content-pins-01 \
  --controls tests/native/room-transition.inputs.json \
  --output .audit/native-room-transition/source-contract-01/NEW-run

python3 scripts/compare_room_transition_contract.py SOURCE/trace.jsonl REPLAY/trace.jsonl
python3 -m unittest discover -s tests/native -p test_room_transition_profile.py
```

Private evidence is under `.audit/native-room-transition/source-contract-01`.
The final receipt identifies the current frozen profile/replays and immutable
starting manifest. The tests explicitly skip private execution checks if that
recording is absent. A successful experiment process alone is intentionally not
reported as transition acceptance. No native build/game, GL, VitaSDK packaging,
VPK staging, installation or FTP is part of this work.
