# Bounded first-room automatic lifecycle

`FirstRoomSession` composes the existing Player, virtual buttons, frame clock,
coroutines, one-shot tweens and presentation for the declared ordinary Madeline
first-room profile. It is not a general Scene/ECS or a full-game implementation.
The profile requires bounds 0..320, one retained static Grid/Solid, safe ground,
no JumpThrus, four Up spikes and one Left spike (17 Up/2 Left images), and the source-backed player
bank. Spawn is `(19,144)`, room height 180, inventory one dash, no collectibles,
and the original default half-strength screenshake setting. A checkpoint **flag**
fixture changes the source Reload reset predicate, not spawn/checkpoint acquisition.

The Session owns input/clock/RNG lifetimes and is deliberately nonmovable.
Reconstructed Players borrow that context; standalone `Player::frame` and its
Normal/Climb/Dash/jump fixtures retain their existing behavior. One frame samples
clock and both buttons before testing positive freeze. The float zero-crossing
tick still skips Scene; no removed Player receives another update.

Death queues a corpse while the old Player remains the committed render owner.
The following Scene boundary commits transferred presentation, runs source death
animation selection and the corpse coroutine. Its bounce tween, deferred effect
component and six-row AngledWipe retain separate source timers. The wipe's
completion flag and later exactly-once callback reconstruct room spikes, Player,
sprite and hair; this is not a coordinate reset. Collision data, buttons, frame
counter, both Level clocks and the global RNG survive. Room-local seed 49 is
separate from global diagnostic seed 0; the single-texture spike choices still
consume original `Next(1)` calls within that temporary scope. Global tile baking
is not repeated. Particle clear, death counters, first-level session-time reset,
camera reset and wipe replacement are bounded responsibilities, not full save,
particle rendering, wind or arbitrary entity loading claims.

Respawn is real state 14: a 0.6-second one-shot tween invokes the Normal transition
before applying squash. State 14 renders original DeathEffect math, not an invented
animation. Live/corpse hair, original body/effect draw arguments, sprite vertices
and wipe vertices are CPU-tested. Hair AfterUpdate precedes interval-shake RNG.
The dust creation RNG branch is retained; dust rendering is excluded.

## Assets and application

`prepare_player_presentation.py --death` preserves all 24 legacy animations and
derives the three required death animations from hash-pinned Sprites.xml and
original PlayerDeadBody/PlayerSprite behavior. It adds the transparent sweat-idle
texture required by the integrated source draw capture. The resulting closure is
202 frames in six 128x64 pages (196,608 submitted RGBA bytes); every crop remains
alpha 0 or 255. Atlas, original-bank and member provenance remain explicit.
`--source-root` selects an existing immutable original-source root explicitly;
it is never an automatic fallback.

The animated non-guest-replay Vita application selects this lifecycle and draws
its sprite/effect commands and wipe triangles. Camera/shake translation is applied
only to world rendering. Corpse/Respawn depth places them after foreground tiles;
the Normal completion frame retains its committed foreground slot until the next
source BeforeUpdate sort boundary. Triangle is a separately logged manual diagnostic restart,
not an automatic Reload. The old 250-sample guest replay and standalone Session
constructor remain **legacy/manual Normal-start** diagnostics; their Triangle
assertions are unchanged and cannot establish autorespawn.

## Verification and exact-WIP provenance

Host build/CTest commands remain in [NATIVE_KERNEL.md](NATIVE_KERNEL.md). The new
`native_lifecycle_unit` exercises two automatic cycles for both flag profiles.
`native_lifecycle_trace_runner` accepts only ordered caller input, not expected
poses, timers, RNG, counters or geometry. `compare_lifecycle_traces.py` checks the
accepted immutable 365-frame source captures, including 11,174 sprite draws and
160 wipe draws per profile. Float values compare by float32 bits, including signed
zero. Original and packed UVs are independently checked against their respective
pinned atlas/layout; world vertex positions are compared directly.

Both new verification CLIs default to requiring committed-clean source. An explicit
`--expected-source-state PATH` opts into the complete `source_identity()` manifest:
base HEAD, status, sorted tracked/untracked relevant paths, per-path bytes/hash/mode,
and aggregate fingerprint. Before/after identities must match exactly. Inputs,
generated assets, native binaries, original source and immutable source artifacts
are separately pinned before/after. There is no dirty fallback or clean-SHA claim.
The existing committed-clean presentation verifier remains unchanged.

`check_native_regressions.py --proof PATH --source-root PATH --native-build PATH
--expected-source-state PATH --output PATH` reuses explicitly selected accepted
legacy extracted-source assemblies with the existing nine physics/input/scheduling
comparators and presentation/geometry comparators. It does not rebuild or rewrite
the source oracle. Output directories must be fresh and private beneath `.audit`.

No full Engine/MInput, original startup/save/RNG parity, GPU/pixel fidelity, audio,
dynamic movers, menus, full game, deployment, emulator or hardware acceptance is
implied. No tracked benchmark exists; performance is unmeasured. Vita/VPK compilation
still requires a supported local SDK and no-splash vitaGL archive, separately from
host verification and runtime acceptance.
