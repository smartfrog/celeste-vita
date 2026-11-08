# RoomCore source-only frontier checkpoint

This is a partial delivery for review, not lifecycle closure or authorization for
a native death/respawn implementation. It extends the accepted partial source
checkpoint `5ffd25a49f1e12c6549aa34648308f41f42361e8` without synchronizing development.

## Established behavior

- The generated C# RoomCore cut compiles offline with the pinned SDK/runtime.
  Executable source spans and declaration contracts have separate inventories.
- Excluded managed members throw on invocation. Native ABI declarations retain
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

## Concrete execution boundary

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

The next decision is the permitted treatment of this platform-identity service:
the current constraints do not permit loading SDL2, replacing `IsGGP`, dropping
its initializer, or ignoring the failure merely to reach `LoadLevel`.

## Evidence and reproduction

Original bodies, generated C#, compiler receipts and execution traces remain
private under `.audit/native-player-death-respawn/`. The initial native guard
checkpoint remains in `native-guard-test-c70009f80b234376a372b37974271fa1/`.
The first actual SDL2 bootstrap boundary is retained in
`native-guard-test-88ba2801318a45b291e3542f282a95dc/execution-prefix.jsonl`.
All earlier failed probes, including probe92, remain unchanged.

With the pinned private inputs and discoveries present, this command creates a
fresh compilation and separate processes for identity, negative import,
duplicate-registration and source-bootstrap checks:

```sh
python3 -B -m unittest discover -s tests/native -p test_room_core_native_guard.py -v
```

Each fresh `native-guard-test-*` directory retains the compilation receipt,
source/declaration inventories, stdout/stderr, and `execution-prefix.jsonl`.
The current cut has 182 unchanged extraction blocks across 122 entries, with
generated-source SHA256
`45f2d0568bd383f35a0cf6e923ac4425f057265bfea0131c1f046485a5f75058`.
This identity does not by itself establish runtime coverage.

Regression checks are the full native Python suite and the task-branch Release
CMake/CTest build. They are not development synchronization, hardware, UI,
FullGame, CIL-equivalence, performance, or complete lifecycle evidence. Parent
review and any later integration remain separate.
