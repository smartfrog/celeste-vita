# Native scheduling compatibility

`src/native/scheduling.hpp` adds headless C++17 `Coroutine` and `StateMachine`
beside the [movement kernel](NATIVE_KERNEL.md). It needs no Mono, CLR, .NET,
game files or third-party library at runtime. It is not a game loop or Player.

## Contract

- An `Iterator` owns a native step callback. `IteratorStep` is either completion
  (`std::nullopt`) or a typed `Yield`: null (`std::monostate`), int32 wait,
  float32 wait, or shared child iterator. Each update steps the stack top once.
  Child push and pop do not step the child/parent again in the same update.
- A positive wait subtracts the selected scaled/raw float32 delta and returns,
  even when it reaches or crosses zero. Other waits and null yields still
  consume a step. Wait arithmetic uses the kernel's strict FP build flags and
  the default round-to-nearest environment; comparisons use exact float bits.
- `cancel` clears the stack/timer, marks finished/inactive and sets `ended`.
  `replace` clears stack/timer, marks unfinished/active and sets `ended`.
  Update clears `ended` first. The executing iterator remains owned through
  the call; a cancellation/replacement during its step suppresses its stale
  yield or completion. Exceptions propagate, without rolling back mutations.
- `active` is a caller scheduling flag: direct `Coroutine::update` does not
  check it, matching the source. StateMachine does check its current coroutine's
  flag. Completion increments `removal_events` when `remove_on_complete` is set;
  this is a synthetic removal request, **not** Entity/component removal.
- State and previous state start at `-1`. `added(entity_has_scene)` and
  `entity_added()` initialize state 0 only while still uninitialized, through
  the ordinary locked setter. These are explicit lifecycle notifications, not
  an Entity/Scene runtime.
- `set_state` observes locked/same-state guards. `force_state` reruns a SAME
  state transition even while locked; a DIFFERENT state uses the guarded setter.
  Transition sets changed/previous/current fields before old end, current begin,
  then current factory (replace) or no factory (cancel). Each post-callback
  lookup uses current fields. A factory's returned iterator replaces the current
  one even if that factory reentered a transition before returning.
- StateMachine update clears `changed_states`, calls the state update and
  applies its returned state, then updates the current active coroutine. A new
  state's iterator can run that same tick. Coroutine-triggered transitions
  replace/cancel the executing stack without running the replacement that tick.
  Executing callback copies remain alive if callbacks are replaced during reentry.

Objects must outlive their calls; callbacks may reenter transitions but must not
destroy the machine/coroutine itself. Shared iterator captures must not introduce
ownership cycles. Iterators model stable typed yields, not arbitrary `Current`
getter side effects or language-level async. Recursive coroutine **update** is
explicitly rejected (`std::logic_error`); transition reentry remains supported.
Null iterator pointers, empty step callbacks, nonfinite deltas/waits and timer
overflow fail explicitly (`std::invalid_argument`). Nonpositive state counts
fail, and used out-of-range state indices throw `std::out_of_range`; invalid
transition targets are rejected before state mutation (outside the valid-source
comparison domain). No reflection, diagnostics/logging API or unsupported yield
fallback exists. There is no disposal/finalizer, thread scheduler or real ECS.

## Verification

Standalone tests run without private files or .NET:

```sh
/usr/bin/cmake -S . -B .audit/native-scheduling/host \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=/usr/bin/c++
/usr/bin/cmake --build .audit/native-scheduling/host -j2
/usr/bin/ctest --test-dir .audit/native-scheduling/host --output-on-failure
```

The optional private differential command reuses the existing pinned SDK
8.0.425/runtime 8.0.31 under `.audit/native-oracle/tools`, offline:

```sh
python3 -B scripts/check_native_oracle.py --domain scheduling \
  --native .audit/native-scheduling/host/native_scheduling_trace_runner
```

`extract_native_oracle.py --domain scheduling` verifies PC 1.4.0.0 input SHA256
`fd73f8a2311fa5737ded550cbad4b75c85b7686b36432f59185e940fcb65fcfe`
and these decompiled file hashes/ranges, copying the class bodies **unchanged**:

| Private file | Inclusive lines | SHA256 |
|---|---|---|
| `Monocle.Coroutine.cs` | 6–102 | `d4cd81b29b8535146931606aeafac396ce739df00a24763a1b51c337325fae33` |
| `Monocle.StateMachine.cs` | 6–202 | `92091f4cdf54a87cab34832d33698d0d5dd33be4c11d8e61c42d1be07e5bdf4e` |

The generated source manifest additionally hashes the extracted blocks.
`tests/native/oracle/scheduling/Shims.cs` supplies only active/visible fields,
explicit attachment, a removal counter, Entity.Scene and float32 Engine deltas.
Original reflection/logging methods remain in the extracted class; their Calc
shim throws and these methods are not exercised. The synthetic runner supplies
IEnumerator scripts/callbacks and inspects private fields for trace instrumentation
outside the extracted methods; it does not reflect or load the original game.

`tests/native/scheduling.fixtures` drives both runners. Its `=>` annotations
declare exact callback/move/removal event coverage; `!` expects a synthetic
exception terminal. They do not supply expected state/timer results. The separate
scheduling validator checks command/event grammar, declared identities, state
bounds, selected tick deltas and complete ordered operation/event coverage before
comparing 17 TSV fields, including float32 bits, stack depth and callback order.
Legitimate repeated reentrant callbacks are preserved. Missing/duplicate events
and identical malformed traces fail; comparison reports the first differing
field without epsilon. Actor validation retains its own domain grammar.

This is **unchanged extracted-method compatibility for synthetic valid inputs**,
not original CIL/decompiler equivalence or full-game execution. The existing
VitaSDK can compile the static library with `BUILD_TESTING=OFF` as documented for
the kernel; compilation is not Vita execution or performance evidence. Buffered
input, Player, maps, hazards, rendering and audio remain outside this slice.
