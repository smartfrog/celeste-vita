# Death/respawn source-closure checkpoint

**Historical partial diagnostic. Not permission to implement native
death/respawn.** This checkpoint executes the original private corpse and wipe
bodies, but does not itself execute a coherent death → room reconstruction →
Respawn14 → Normal0 lifecycle. The later bounded controlled round trip is
documented in `native-player-room-core-frontier-checkpoint.md`; it does not
close any of the eight required lifecycle families. Native gameplay, rendering,
assets and API are unchanged.

## Reproduction

From the repository root, using the existing private inputs and offline tools:

```sh
python3 -B scripts/read_player_death_sources.py --output .audit/native-player-death-respawn/example/source
python3 -B scripts/prepare_player_death_oracle.py --source .audit/native-player-death-respawn/example/source --output .audit/native-player-death-respawn/example/checkpoint --checkpoint-only
python3 -B scripts/prepare_player_death_oracle.py --source .audit/native-player-death-respawn/example/source --output .audit/native-player-death-respawn/example/load-level-probe --probe-load-level
```

Outputs must be fresh. The first command reuses the tracked presentation
extractor, validates the original archive, executable/FNA/mscorlib hashes, SDK
8.0.425/runtime 8.0.31 and ILSpy identity, and decompiles only named types with
`--disable-updatecheck`. No restore source or network download is enabled.
The second command is an explicitly partial diagnostic. The third intentionally
fails compilation: it selects the complete unchanged `Level.LoadLevel` body
instead of the throwing boundary. Omitting `--checkpoint-only` also fails the
coverage gate; a successful diagnostic process is not lifecycle acceptance.

All handwritten recipes, shims, independent fixture inputs and tests are
tracked. Binaries, original source bodies, generated source, metadata and traces
remain private. The extraction manifest binds source blocks, handwritten
support, recipe dependencies and fixture hashes. `verify_extraction` checks
every selected block for byte identity and unchanged inclusion.

## What actually executes

Six independent fixture cases supply a position and death direction to a
declared Player shell: Up direction, Left direction, early MenuConfirm,
ActionDelay, checkpoint retention and non-first-level retention. They do not
supply expected pose, hair nodes, RNG values, draw vertices or native output.
`Player.Die` and `Drop` are unchanged original methods. Original complete
PlayerDeadBody, DeathEffect, Coroutine, Tween, Component, ComponentList,
EntityList, RendererList, ScreenWipe and AngledWipe execute, as do the selected
Entity/Scene/Tracker ownership methods and complete Reload/UnloadLevel methods.
The original Freeze method and Engine positive-freeze branch execute too.

Original SpriteBank/Sprite/PlayerSprite/PlayerHair and selected FNA
Vector2/Color/MathHelper/SpriteBatch geometry bodies are reused from the accepted
presentation closure. Source-local math is **not** original x86 FNA or original
CIL runtime execution. Original private mscorlib Random is available under the
existing tracing subclass at diagnostic seed 0, not a .NET 8 RNG substitution
or a claim of original startup RNG parity. Missing Level RNG behavior means
these checkpoint traces do not establish lifecycle RNG parity.

The fixture shell is not the original Player constructor/Added/update path.
Collision services throw, so caller-supplied directions do not prove Up/Left
hazard collision. MenuConfirm is a sampled diagnostic boolean, not the real
virtual-button/input pipeline. It is never reported as held/buffered-input
coverage. Respawn methods compile unchanged but are not reported as executed.

## Mandatory blocker and smallest next source-only split

1. `Level.LoadLevel:357–1387` remains a throwing boundary. Original Reload
   reaches it through the real ScreenWipe completion delegate after original
   UnloadLevel has actually removed the corpse and committed its removal.
   Required responsibilities include resets at 359–449, scoped RNG at
   386/1386, static room materialization at 468–1296 and Player reconstruction,
   camera and wipe-in at 1297–1349. Do not replace this with state0 teleport.
2. `Level.Shake:2616–2623` is **not mechanically inert**: it sets shake state,
   consumed by `Level.Update:1927–1956`, including global RNG draws. The
   diagnostic records this unsupported service explicitly instead of claiming
   its output is faithful. `Level.Update:1823–1827` also consumes global RNG
   even during corpse/wipe ticks. The current plain Scene driver omits these
   mandatory Level phases and `UpdateTime:1726–1746`.
3. Link the existing unchanged Normal/Climb/Dash/input/geometry closure to
   original constructor/Added/removed phases, state14 callbacks, level clocks,
   shake/RNG, static guarded room reconstruction and camera. Use source-proved
   absent-world guards, not silent no-ops, for mutable entities, triggers,
   collectibles, other states, assists and transitions. Only after that closes
   should the eight lifecycle fixtures and native contract be accepted.

Audio, rumble, save statistics, particle clears and displacement are explicit
recording boundaries in this diagnostic. They are not evidence for those
systems. Collider, FNA Vector3/Matrix and GPU services are diagnostic shells;
they are not accepted geometry/render parity. The static area-wipe selection
is caller glue here, not execution of AreaData's original selection callback.

## Source-grounded phase constraints for the next gate

These are inspection constraints, **not a verified native contract**:

| Phase | Original source boundary |
| --- | --- |
| Lethal hazard | Player 1898–1920 visits tracked PlayerColliders in order using the hurtbox, restores collider and returns before UpdateHair after death. Spikes 220–249 supplies Up/Left direction. |
| Die | Player 2855–2908 sets Dead, zero speed, lock/noncollidable, constructs corpse, queues corpse addition and old-player removal. Further Die calls return null. |
| Ownership commit | EntityList 61–123 adds before removing, then depth-sorts and Awakes; ComponentList 199–210 defers additions/removals until unlock. Corpse retains actual sprite/hair/light objects. |
| Bounce | PlayerDeadBody 75–114 requests .05 freeze, yields one resume, creates .5 CubeOut tween, waits .375 through Coroutine's separate timer-crossing tick, then stops tween. |
| Burst and wipe | DeathEffect duration .834; corpse waits .65 of that, optional ActionDelay, calls End once. ScreenWipe uses RawDeltaTime/.5, then separate Completed and removal/callback ticks. Rendering still runs while Engine update is frozen. |
| Reload | Level 1400–1435 resets Session.Time/Deaths only for first-level/no-collectibles/no-checkpoint; room deaths are not reset there. Unload and LoadLevel(Respawn) are real lifecycle operations. |
| Reconstruction | Player constructor 1116–1253 resets grab and constructs physics/components; Added 1277–1328 sets state14, JustRespawned, StartHair and PreviousPosition. Level 1315–1335 reconstructs camera and wipe-in. |
| Respawn | Player 6121–6154 creates .6 tween; completion enters Normal0 and sets scale (1.5,.5). State14 Render 1368–1370 uses DeathEffect, not ordinary body. This is not WakeUp15. |
| Live resumption | Original virtual buttons/controller history, scene clocks, session/checkpoint and global RNG must survive appropriately; Player-owned physics/presentation/hair are reconstructed. ResetGrab and Level hair AfterUpdate ordering remain mandatory. |

Exact corpse/wipe tick indices in these traces are conditional diagnostic
observations, not final gameplay timing. Engine inputs precede the positive
freeze check, and the zero-crossing freeze tick still skips Scene update
(Engine 224–276). Coroutine 35–81 likewise does not resume on its timer's
crossing tick. Frozen/live/dead/wipe/reload/respawn input behavior and first
resumed action must be proved together, rather than inferred from these pieces.
