# RoomCore source-only frontier checkpoint

This is a partial delivery for review, not lifecycle closure or authorization for
a native death/respawn implementation. It extends the accepted partial source
checkpoint `5ffd25a49f1e12c6549aa34648308f41f42361e8` and is synchronized with
the accepted directional-input development tip.

## Established behavior

- The generated C# RoomCore cut compiles offline with the pinned SDK/runtime.
  Executable source spans and declaration contracts have separate inventories.
- Excluded managed members throw on invocation, except for the explicitly declared
  managed platform-identity fixture below. Native ABI declarations retain
  their original extern/import attributes, signatures and marshalling metadata as
  a distinct `native-abi` declaration kind, not a managed implementation.
- A module initializer installs a throwing resolver for the generated assembly
  only. Its attempt history cannot be cleared through the harness API. Duplicate
  registration fails. It neither loads a library nor returns a fallback handle.
- The actual pinned `Celeste.Audio.FMOD_SDL_Register` import retains its original
  metadata and null managed body. Fresh-process negative invocation reaches the
  resolver. This is not FMOD behavior or a universal native-cache blocking proof.
- A fail-fast execution prefix now runs original `Tags.Initialize`, full
  `Tracker.Initialize` reflection, and the original `Level` constructor.
- One controlled caller stimulus runs the original `Player.Die`/
  `PlayerDeadBody`/`Coroutine`/`DeathEffect`/`Wipe`/`Level.Reload`/
  second `LoadLevel(Respawn)`/`Normal0` sequence. This is not a hazard,
  directional, corpse-parity, input, or repeated-cycle family proof.

## Preserved historical boundary at 4e1d0a0

Only actually invoked members were promoted after the first execution:
the implicit `Binding` constructor, `Settings` constructor, and managed
`SDL_GetPlatform` wrapper. Their original initializers and bodies remain intact.

The resulting source call chain is:

```text
Settings constructor
  Celeste.Celeste type initializer
    IsGGP platform-identity initializer
      SDL_GetPlatform managed wrapper
        SDL2.SDL.INTERNAL_SDL_GetPlatform
          generated-assembly resolver throws UnsupportedClosure for SDL2
```

The trace records one real native-ABI boundary attempt, no SDL2/FMOD mappings
before execution or at the boundary, and unsuccessful process exit. The original
exception chain is retained. There is no catch-and-continue, substituted platform
identity, native fallback, or reuse of the failed initialized type.

`LoadLevel` has **not** been entered. No real Level ticks, state 14-to-0 transition,
controlled live tick, or corpse/wipe/reload roundtrip is established. Completion
remains **0/8 lifecycle families**. The remaining caller fixture is deliberately
not treated as assembled.

That checkpoint and its failure remain immutable. The parent subsequently
approved only the managed wrapper fixture described below; it did not authorize
native SDL2 loading, changing `IsGGP`, or removing its initializer.

## Current managed platform fixture and first live tick

The declared `pc-linux` profile supplies the string `Linux` through only the
public managed no-argument `SDL_GetPlatform` wrapper. The original wrapper is
excluded from unchanged executable identity. Its original method, signature and
body hashes, replacement body/hash, profile, reason, and tracked provider hash
are recorded separately in the generated manifest. `IsGGP` and the Settings
constructor remain unchanged and compute their own values from that input.

This is a reference-platform input, not a claim about physical Vita, original SDL
runtime behavior, original startup/save parity, native interop, or CIL equivalence.
Tests observe no native attempts and no SDL2/FMOD mappings. Unsupported profiles
are rejected. Both the original native platform import and another SDL import
still hit the unchanged throwing resolver, as does the pinned FMOD import.
Original `UserIO` static path initialization also reads the managed platform
fixture twice; those reads are recorded rather than counted as native activity.

The unchanged `LoadLevel(Respawn)` body now returns after creating the state14
`Player` and room entities. The execution trace records `state = 14` at return.
A real `Level.BeforeUpdate`, `Level.Update`, `Level.AfterUpdate` tick loop then
executes original Level and Player update. Tick 35 still runs `StateMachine`
update in state14; later tween completion transitions to state0 through
`IntroRespawnEnd`/`NormalBegin`. Only tick 36 executes one original
`NormalUpdate`. No state0 teleport, unsupported closure, native attempt, or
native mapping occurs.

Reached source members now include the original `SFX.EventnameByHandle`,
`Audio.SetAltMusic`/`SetMusic`/`SetAmbience`/`SetParameter`/`Stop`/
`EndSnapshot`/`GetEventDescription`/`CreateInstance`/`Play` bodies (including
the position overload and `SetMusicParam` in the death path), the original
`Spikes` constructor and `Added`, `PlayerCollider.Check`, `Input.Initialize`
and `Input.Rumble`, `SaveData.AddTime`/`AddDeath`, `Scene.OnRawInterval`, and
`UserIO.Saving`. These are ordinary source executions, not a whole-class import.
The Engine pooler/scene accessors and a declared no-device rumble profile are
driver inputs for the death probe, not startup parity.

The audio profile is explicit: the pinned SFX path constants are preloaded into
`Audio.cachedEventDescriptions` with null descriptions before execution.
Original audio bodies execute but receive no event instances. This is not FMOD,
native audio, recording-service output, or startup-audio parity. A declared
1920x1080 camera viewport, empty session audio events, and source
Lighting/Bloom/Hud renderers are caller inputs for this bounded probe.

Caller limitations remain explicit: map data is preloaded field storage for the
pinned stripped room, not execution of the guarded MapData constructor or its
initializers. Original MapData `Get`/`TileBounds` execute. Only the first two
original area object initializers plus the declared Spike atlas id are selected;
whole AreaData loading is not claimed. World tile/caller assembly, original
startup/save data, full input history, and complete LevelLoader fidelity remain
unproven. Input initialization is executed once, but no button history or
buffered input is claimed; the death driver records `inputSampled = false`.
The death path additionally declares only the LevelLoader-owned field subset
(`Particles`, `ParticlesBG`, `ParticlesFG`, `strawberriesDisplay`) plus
`Engine.Pooler`/`Engine.Scene` and GUI atlas metadata as driver environment; the
original LevelLoader constructor/loading thread and SolidTiles geometry still do
not execute.

A separate fresh-process probe now executes one controlled death round trip.
After the first `Normal0`, the caller invokes the original `Player.Die` with an
explicit `(0, -1)` stimulus. That stimulus is a probe input, not a hazard,
directional-collision, ordering, or family proof. The source sequence is:

```text
Player.Die
  PlayerDeadBody constructor / deferred Awake
  DeathRoutine coroutine
    Celeste.Freeze(0.05)
    freeze gate ticks 37-39 (zero-crossing tick 39 skips Scene update)
    bounce Tween commit tick 40, DeathEffect tick 64
  PlayerDeadBody.End
    Level.DoScreenWipe -> AngledWipe with OnComplete = Level.Reload
  Wipe completion tick 129, Reload tick 130
    UnloadLevel removes the corpse/old Player
    second original LoadLevel(Respawn) creates a new state14 Player at (19,144)
  second IntroRespawn tween -> Normal0 tick 166
  one resumed original NormalUpdate tick 167 (speed Y = 15.000001)
```

The trace records corpse/player/wipe body identities, the wipe's
`OnComplete.Target == level` and method `Reload`, the removed corpse, the new
state14 Player, the second LoadLevel wipe-in, and the single resumed state0
tick. Session death counters are source-derived: at Die `Session.Deaths = 1`
and `SaveData.TotalDeaths = 1`; `Level.Reload` then takes the first-level branch
and clears `Session.Deaths`/`Session.Time` while `DeathsInCurrentLevel` remains
1. No state0 teleport, fake reload callback, native attempt, or native mapping
is used.

The bounded driver mirrors only the original Engine freeze gate, records that
input sampling is not modeled, and never swaps Scene/Player. Required
LevelLoader-owned fields (`Particles`, `ParticlesBG`, `ParticlesFG`,
`strawberriesDisplay`, `Engine.Pooler`, `Engine.Scene`) are declared caller
driver setup using original constructors/properties; original LevelLoader and
its loading thread are still not executed. GUI atlas metadata comes from the
pinned `Gui.meta`; rumble is a declared no-device profile. Original
`SaveData.AddDeath` executes with recording `Stats`/`StatsForStadia` fixtures.
Original `Level.Reload` also writes `Distort` presentation floats; those GPU
effect-parameter writes use a typed `Celeste.Distort` recording boundary while
preserving its state fields. None of these fixtures replace the corpse, wipe,
Reload, LoadLevel, Player, or RNG/clock path.

There is still no hazard-triggered death, directional collision proof, Up/Left
family, ordering/double-death, corpse presentation parity, buffered input,
or repeated-cycle proof. Completion remains **0/8 lifecycle families**. The
controlled round trip closes only the first source-level corpse/wipe/reload
sequence; the eight family contracts remain open.

## Synchronized delivery

The delivery merge brings current `development` `921a098c2ed02fee5e8c48669fde3bac45ac043d`
(the accepted directional-input `.3`/`.7` aim and legacy-250 change) into the
existing task branch without rebase/reset/force/cherry-pick. It retains
development's native harness, decal, spike-art, guest-replay and directional-input
changes plus the controlled death/reload proof without rewriting input code. The
only recipe adaptation was regenerating the
private death-source snapshot as `source-synced-6b-01` so development's added
`Celeste.Spikes.cs` presentation pin is validated by the same source inventory;
the frozen `5ffd` snapshot and all older proof directories remain immutable.
The unreviewed input `921` branch and other POCs were not merged.

## Compiled native ABI identity correction

The first synchronized review found three compiled P/Invoke signatures in
`FMOD.System` bound to `FMOD.Studio.ADVANCEDSETTINGS`,
`FMOD.Studio.SYSTEM_CALLBACK` and `FMOD.Studio.SYSTEM_CALLBACK_TYPE` because
the generator injected a global `using FMOD.Studio;` while the original root
`FMOD` contracts were absent. The fix pins four original root declaration
contracts beside `FMOD.System`: `FMOD.ADVANCEDSETTINGS`,
`FMOD.SYSTEM_CALLBACK`, `FMOD.SYSTEM_CALLBACK_TYPE` and the dependent
`FMOD.DSP_RESAMPLER`. Their kind, layout, fields, delegate signature, enum
values, attributes and original source hashes are recorded in
`declaration-pins.json` and the generated manifest.

`tests/native/oracle/death/NativeAbiMetadataAudit.cs` now compares the fresh
compiled assembly against the pinned `Celeste.exe`/`FNA.dll` original metadata
for **all 1094** P/Invoke signatures, including their qualified parameter/return
types, refs, import attributes, library/entrypoint and null-body contract. It
also checks the three expected root types, the three affected native calls, and
the four root type contracts. The regression runs the same audit against the
pinned pre-fix `54581b5` assembly: RED is exactly 3 signature mismatches; GREEN
on the fresh build is 0 mismatches and 0 root-contract mismatches. The
transformation compares identities only; the assembly name is ignored and there
is no `FMOD.Studio`/root collapse. Negative FMOD/SDL resolver tests remain in the
same focused suite.

## Evidence and reproduction

Original bodies, generated C#, compiler receipts and execution traces remain
private under `.audit/native-player-death-respawn/`. The initial native guard
checkpoint remains in `native-guard-test-c70009f80b234376a372b37974271fa1/`.
The first actual SDL2 bootstrap boundary is retained in
`native-guard-test-88ba2801318a45b291e3542f282a95dc/execution-prefix.jsonl`.
All earlier failed probes, including probe92, remain unchanged.
The first LoadLevel-entry trace is retained in
`native-guard-test-7858d793f5854f21905ee2d25adeaf0f/load-level-prefix.jsonl`.
The first successful live-tick run is retained in
`native-guard-test-1e4a6b94beed43cbac3b46a4c0cfff84/respawn-live-tick.jsonl`
with its compiled source manifest and source identity beside it. The accepted
`52723db` checkpoint remains in `room-core-checkpoint-52723db/verification.json`.
The pre-sync controlled death/wipe/second-Respawn trace remains in
`death-probe-13/death-respawn-roundtrip.jsonl`; the synchronized rerun is
retained under `.audit/native-player-death-respawn/<delivery-commit>/` with the
generated manifest, source identity, GUI atlas, and stdout/stderr files. The
additional declaration source `room-core-declarations-extra-01` was generated
with `scripts/read_frontier_declarations.py --require-type LedgeBlocker` and
recorded in the tracked declaration pins.

With the pinned private inputs and discoveries present, this command creates a
fresh compilation and separate processes for identity, negative import,
duplicate-registration, managed-platform fixture, and source execution checks:

```sh
python3 -B -m unittest discover -s tests/native -p test_room_core_native_guard.py -v
```

Each fresh `native-guard-test-*` directory retains the compilation receipt,
source/declaration/fixture inventories, stdout/stderr, `execution-prefix.jsonl`,
and `respawn-live-tick.jsonl`. The death round-trip process writes
`death-respawn-roundtrip.jsonl` in the same private directory.
The current cut has 183 unchanged extraction blocks across 123 entries, with
generated-source SHA256
`20ab627ccce726df08153dd18a53cca817514b184b735211e45796bf36708a07`.
The generated-source SHA has moved across sync/correction because private
discovery-path labels and pinned declaration contracts changed; the selected
183 blocks / 123 entries and every selected executable-source body hash remain
unchanged. It records 3035 executable members, 13437 declaration contracts including 1094
native-ABI declarations, and zero managed platform fixture changes beyond the
separate `SDL_GetPlatform` wrapper. The declaration count difference includes
the declared recording `Distort` boundary; the executable count includes the
ordinary promoted `Input.Rumble`, `Audio.Play(position)`,
`Audio.SetMusicParam`, `SaveData.AddDeath`, `Scene.OnRawInterval`, and Engine
scene/pooler accessors.
This identity does not by itself establish full runtime coverage or any of the
eight hazard/lifecycle families.

Regression checks are the full native Python suite and the task-branch Release
and AddressSanitizer CMake/CTest builds. The synchronized merged counts are 348
Python tests and 27 CTest entries. They are not hardware, UI, FullGame,
CIL-equivalence, performance, or complete lifecycle evidence. Parent review and
any later integration remain separate.
