# Native movement kernel

`src/native/movement.hpp` is the first native C++17 code, independent of Mono,
CLR, FNA and the game runtime. This is a host-tested static-collision subset,
not a playable port. The earlier [feasibility audit](FEASIBILITY.md) remains
historical evidence, not a native execution claim.

## Build and test

No external test framework or packages are required. Python 3.12+ (standard
library only) runs the validation-tool regressions through CTest:

```sh
/usr/bin/cmake -S . -B .audit/native-kernel-host \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=/usr/bin/c++
/usr/bin/cmake --build .audit/native-kernel-host -j2
/usr/bin/ctest --test-dir .audit/native-kernel-host --output-on-failure
```

The unit executable checks behavior without game files or .NET. The fixture
runner smoke test also exercises the shared synthetic fixture protocol.
GNU/Clang strict floating-point flags disable fast-math and FMA contraction.
Other compiler configurations are explicitly rejected until validated.
Use the default round-to-nearest floating-point environment for simulation.

Cross-compile the static library only with the existing SDK (no installation):

```sh
/usr/bin/cmake -S . -B .audit/native-kernel-vita \
  -DCMAKE_TOOLCHAIN_FILE=/home/fred/cloudpunk-vita/tools/vitasdk/share/vita.toolchain.cmake \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF
/usr/bin/cmake --build .audit/native-kernel-vita -j2
```

This establishes compilation, **not execution, linking into a Vita game, or
performance on Vita**. No VPK is produced by this ticket.

## Supported contract

- `Body` is just position, optional hitbox and target `collidable` flag.
  `StaticWorld` contains explicit ordered Solid and JumpThru pointer lists;
  the caller supplies category membership and preserves object lifetimes.
  World and referenced bodies must outlive the actor and calls, including
  callback reentry. Lists may contain the querying body: self is excluded.
- Float32 position/remainder accumulation, followed by double-promoted .NET
  ties-to-even rounding and checked int32 conversion. Exact moves walk pixels;
  they do not consume existing fractional remainders unless blocked.
- Strict hitbox overlap, offsets and negative coordinates. Edge touching is
  not overlap. Right/bottom grouping is `(offset + size) + position`, not
  `(offset + position) + size`. Zero-size hitboxes retain the source predicate.
- Queries exclude self, missing colliders and noncollidable **targets**;
  a noncollidable querying actor still checks collisions. Query-at operations
  are side-effect-free, equivalent to source save/set/check/restore for this
  hitbox-only subset (there are no custom collider hooks).
- Horizontal movement checks Solid only. Vertical movement checks Solid first,
  then ordered JumpThrus only when descending, not ignored, and outside the
  particular target at the current position.
- `true` means blocked, including partial travel. Synchronous callbacks receive
  hit/pusher pointer identity, original intended target, signed moved distance
  and direction, including signed-zero vector components. The blocked axis's
  remainder is zero **before** the callback. Callback position/remainder/world
  mutation and nested movement are not overwritten on return. Exceptions
  propagate; callback state is not rolled back. To exercise a combined step,
  call `move_h` **before** `move_v`; there is no integration/scheduler API.
- Nonfinite input/computed edges, negative dimensions, null world entries and
  rounded movement outside int32 throw `std::invalid_argument`, rather than
  relying on undefined conversion behavior. Inputs are validated when used;
  this is not a transactional scene validator. Pixel walking is linear in the
  requested distance, even for large valid int32 moves.

The only collider type representable by this API is `Hitbox`; unsupported
shapes/features have no conversion or fallback API. Grid, Circle,
ColliderList, moving platforms/carry/push/lift/squish, Player/state machine,
coroutines, input, map loading, rendering and audio are **not implemented**.
The pusher is identity-only; passing one does not implement pushing.

## Private differential reference

The reference executes **unchanged extracted methods**, not newly rewritten
movement algorithms and not reflected game CIL. Private inputs must already
exist under `.audit/ilspy`, from the accepted PC 1.4.0.0 analysis. The extractor
checks `inputs/Celeste.exe` SHA256:

`fd73f8a2311fa5737ded550cbad4b75c85b7686b36432f59185e940fcb65fcfe`

Exact inclusive ranges used from `.audit/ilspy/cs/`:

| File | Lines |
|---|---|
| `Celeste.Actor.cs` | 186–281 (four movement methods) |
| `Celeste.CollisionData.cs` | 5–18 |
| `Monocle.Collide.cs` | 8–28, 51–70 |
| `Monocle.Entity.cs` | 682–690, 728–738 |
| `Monocle.Collider.cs` | 8–22, 205–251, 255–258 |
| `Monocle.Hitbox.cs` | 7–98, 180–183 |

The extractor also checks pinned hashes from the accepted decompilation; the
generated `source-manifest.json` records each source file SHA256 and block
hash/range. Tracked `tests/native/oracle/Shims.cs` visibly substitutes only a
two-float vector, entity position/collider ownership, explicit ordered tracker
lists, platform identity shells and Hitbox-only dispatch (other shapes throw).
The tracked runner supplies synthetic callbacks. There is no original scene
initialization, Tracker registration, FNA implementation or game execution.
This proves **extracted-method compatibility for these fixtures**, not full
original gameplay or equivalence of decompilation to original CIL.

Python 3.12+ is needed for the optional private bootstrap/check scripts:

```sh
python3 scripts/bootstrap_native_oracle.py
python3 scripts/check_native_oracle.py --native .audit/native-kernel-host/native_trace_runner
```

Bootstrap downloads official SDK **8.0.425 linux-arm64** (212188361 bytes), paired
with runtime **8.0.31**, using Microsoft's published release metadata URL and
SHA512. All downloads/extraction stay in `.audit/native-oracle/tools`; there
is no PATH/profile/global install or change to the shared Cloudpunk runtime.
The check invokes that exact SDK, disables telemetry, uses private CLI/cache
directories, clears NuGet sources, and restores/builds package-free net8.0
offline. Once bootstrapped, checks need no network. All original C#, binaries,
reference build artifacts and traces remain ignored under `.audit`.

Metadata reads are capped at 2 MiB. Both streamed downloads and existing SDK
archives must be exactly 212188361 bytes and match the pinned published SHA512;
a changed metadata hash fails explicitly. Oversized/short downloads fail before
extraction or SDK execution. Only a uniquely owned unverified partial is cleaned
on failure; existing caches and unrelated files are not deleted. Regression
tests mock network/extraction/execution, use tiny archives for filesystem
checks, and simulate the oversized 230686720-byte response without allocating
or writing it. The SDK is not downloaded by tests.

`tests/native/movement.fixtures` defines the same operations for both runners.
Each TSV row carries case/step/event/return value, position/remainder bits,
hit/pusher identity and every collision vector's float bits. The comparator
fails at the **first divergent operation/field**, without epsilon tolerances.
Before comparing, each trace independently must satisfy the field grammar and
the ordered case/step/terminal-event coverage derived from the fixture commands.
Missing, duplicate and foreign operations are rejected even if both traces
contain the same error. Callback/reentry sequences follow the fixture runner's
callback mode, including nested callbacks; this validation does not calculate
movement or collision outcomes. The two-path comparator CLI defaults to the
maintained fixtures; use `--fixtures PATH` for another synthetic fixture set.
The unit suite additionally checks invalid-input failures and callback throws,
outside the reference's supported valid-input domain.
