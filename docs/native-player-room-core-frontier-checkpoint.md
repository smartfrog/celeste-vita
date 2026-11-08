# RoomCore source-only frontier checkpoint

This is a partial delivery for review, not lifecycle closure or authorization for
a native death/respawn implementation. It extends the accepted partial source
checkpoint `5ffd25a49f1e12c6549aa34648308f41f42361e8` without synchronizing development.

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
reaches state `0` on tick 35 and executes exactly one further controlled live
tick on tick 36. Both state0 ticks use original Level update and Player
`NormalUpdate`; no state0 teleport, unsupported closure, native attempt, or
native mapping occurs.

Reached source members now include the original `SFX.EventnameByHandle`,
`Audio.SetAltMusic`/`SetMusic`/`SetAmbience`/`SetParameter`/`Stop`/
`EndSnapshot`/`GetEventDescription`/`CreateInstance`/`Play` bodies, the original
`Spikes` constructor and `Added`, `PlayerCollider.Check`, `Input.Initialize` and
input binding primitives, `SaveData.AddTime`, and `UserIO.Saving`. These are
ordinary source executions, not a whole-class import.

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
buffered input is claimed.

There is still no death/corpse/wipe/reload roundtrip and no coherent eight-family
coverage. Completion remains **0/8 lifecycle families**. The remaining gap is
the real corpse lifecycle and Wipe completion through `Reload` into a second
`LoadLevel(Respawn)`, then the Up/Left hazard, ordering, corpse/Hair/RNG/draw,
callback/list, freeze/buffered-input, reload-resume, and repeated-cycle families.

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
`native-guard-test-f71a5f2b157f459eb8c1bdd62bdaa368/respawn-live-tick.jsonl`
with its compiled source manifest and source identity beside it.
The additional declaration source `room-core-declarations-extra-01` was generated
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
and `respawn-live-tick.jsonl`.
The current cut has 183 unchanged extraction blocks across 123 entries, with
generated-source SHA256
`83a018b515c73d3f95df88f1d0b7ad20469b9fcf698a207ba41de0233b2876bd`.
It records 3027 executable members, 13421 declaration contracts including 1094
native-ABI declarations, and zero managed platform fixture changes beyond the
separate `SDL_GetPlatform` wrapper.
This identity does not by itself establish full runtime coverage.

Regression checks are the full native Python suite and the task-branch Release
CMake/CTest build. They are not development synchronization, hardware, UI,
FullGame, CIL-equivalence, performance, or complete lifecycle evidence. Parent
review and any later integration remain separate.
