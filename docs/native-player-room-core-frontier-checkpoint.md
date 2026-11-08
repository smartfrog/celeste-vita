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

## Current managed platform fixture and first LoadLevel entry

The declared `pc-linux` profile supplies the string `Linux` through only the
public managed no-argument `SDL_GetPlatform` wrapper. The original wrapper is
excluded from unchanged executable identity. Its original method, signature and
body hashes, replacement body/hash, profile, reason, and tracked provider hash
are recorded separately in the generated manifest. `IsGGP` and the Settings
constructor remain unchanged and compute their own values from that input.

This is a reference-platform input, not a claim about physical Vita, original SDL
runtime behavior, original startup/save parity, native interop, or CIL equivalence.
Tests observe one fixture read, unchanged RNG and clocks, no native attempts,
and no SDL2/FMOD mappings. Unsupported profiles are rejected. Both the original
native platform import and another SDL import still hit the unchanged throwing
resolver, as does the pinned FMOD import.

The current execution prefix also runs original `MInput.Initialize`, prepares
single-room header inputs, and enters the unchanged `LoadLevel(Respawn)` body.
The body writes `LastIntroType = Respawn` and then stops at the still-guarded
`SFX.EventnameByHandle` member. The process fails immediately; the next routine
promotion is that original member and its proven initialization dependencies.
No new platform authorization is needed for ordinary member promotions.

Caller limitations are explicit: map data is preloaded field storage for the
pinned stripped room, not execution of the guarded MapData constructor or its
initializers. Original MapData `Get`/`TileBounds` execute. Only the first two
original area object initializers are selected, including the original wipe
callbacks; whole AreaData loading is not claimed. World tile/caller assembly,
input sampling/history ticks, and complete LevelLoader fidelity remain unproven.
None of these limitations is counted as lifecycle coverage.

There is still no state 14-to-0 transition, controlled live tick, or coherent
corpse/wipe/reload roundtrip. Completion remains **0/8 lifecycle families**.

## Evidence and reproduction

Original bodies, generated C#, compiler receipts and execution traces remain
private under `.audit/native-player-death-respawn/`. The initial native guard
checkpoint remains in `native-guard-test-c70009f80b234376a372b37974271fa1/`.
The first actual SDL2 bootstrap boundary is retained in
`native-guard-test-88ba2801318a45b291e3542f282a95dc/execution-prefix.jsonl`.
All earlier failed probes, including probe92, remain unchanged.
The first LoadLevel-entry trace is retained in
`native-guard-test-7858d793f5854f21905ee2d25adeaf0f/load-level-prefix.jsonl`.

With the pinned private inputs and discoveries present, this command creates a
fresh compilation and separate processes for identity, negative import,
duplicate-registration, managed-platform fixture, and source execution checks:

```sh
python3 -B -m unittest discover -s tests/native -p test_room_core_native_guard.py -v
```

Each fresh `native-guard-test-*` directory retains the compilation receipt,
source/declaration/fixture inventories, stdout/stderr, `execution-prefix.jsonl`,
and `load-level-prefix.jsonl`.
The current cut has 183 unchanged extraction blocks across 123 entries, with
generated-source SHA256
`5f1fdbc7177c5e1d368b2c7ddf5049d9791ebfcb7b6f067e5e413cc83e355838`.
This identity does not by itself establish runtime coverage.

Regression checks are the full native Python suite and the task-branch Release
CMake/CTest build. They are not development synchronization, hardware, UI,
FullGame, CIL-equivalence, performance, or complete lifecycle evidence. Parent
review and any later integration remain separate.
