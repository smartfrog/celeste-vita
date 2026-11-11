# Native sampled-button compatibility

`src/core/input.hpp` adds a headless C++17 `VirtualButton` to the existing
native library. No game files, .NET or third-party dependencies are required by
the native library or standalone tests.

## Sample boundary

```cpp
celeste::VirtualButton jump(0.08f);
jump.sample = {held, raw_pressed, raw_released, disabled, debug_key_held};
jump.update(scaled_delta_time);
if (jump.pressed()) jump.consume_press();
```

The caller supplies already-resolved booleans and a float32 scaled delta.
`sample` stays unchanged until the caller replaces it. Querying never synthesizes
edges, polls devices or mutates a Binding. `debug_override_pressed` represents
the source's configured debug key being **held**, not a fresh key edge; false
also represents no configured override. It bypasses disabled/consumed only for
`pressed()`. `check()` and `released()` gate the sampled held/released values
with disabled; consumption does not affect them.

Sample and update input even when scene simulation is omitted during freeze.
This class neither invokes scene updates nor implements engine registration,
freeze/lifecycle scheduling or a full frame clock. Hardware keys, gamepads and
the device sampling/calibration layer remain outside this slice; the separate
directional-input slice below covers source-style analog direction resolution.
Side-effectful or changing Binding getters are unsupported.

## Preserved semantics

- Update clears consumed first, subtracts delta from the buffer, then replaces
  it with `buffer_time` on a raw press. Pressed **or** held enables the repeat
  path. When neither is true, update clears both counters and repeating immediately.
- Held input retains the buffer until its positive interval expires. The
  counter is not clamped at zero; queries require strictly greater than zero.
  The Jump/Dash configuration is `0.08f`. Raw press can still report pressed
  with zero or negative buffer configuration.
- `pressed()` checks debug override before disabled and consumed, then checks
  positive buffer, repeating and raw press. Queries are stable for unchanged
  state/sample, including before update and after consumption.
- `consume_buffer()` clears only the buffer: raw press or repeat can still
  report pressed. `consume_press()` also gates pressed until the next update.
- `set_repeat(first, multi)` enables repeat exactly when first is positive.
  Disabling clears only repeating, not counters or consumption. Re-enabling
  retains the old countdown. The single-delay overload supplies both delays.
- An exactly zero repeat counter primes first and returns without decrement.
  Otherwise it subtracts delta once; crossing/reaching zero emits one repeat
  and installs multi, discarding overshoot. There is no catch-up loop. Zero
  multi therefore reprimes first on the following held update; negative multi
  is retained. Enabled reconfiguration does not clear an existing repeat flag.

Finite negative/zero deltas and configuration values, including signed zero,
retain source behavior. Nonfinite constructor/configuration/update values and
timer arithmetic overflow throw `std::invalid_argument`, outside the comparison
domain. `buffer_time` is validated on update. Exceptions do not roll back earlier
mutations. Float32 arithmetic uses the library's strict FP flags and the default
round-to-nearest environment, not fast math or an epsilon comparison.

## Vita analog direction profile

`src/core/directional_input.hpp` adds a bounded, host-testable resolver without
changing `Controller::sample(Controls)` or the 250-frame guest fixture. The
source order is `Celeste.Input.cs` 145-151/331-373, `Monocle.Binding.cs` 204-222,
`Monocle.VirtualIntegerAxis.cs` 51-98 and `Monocle.VirtualJoystick.cs` 71-233,
with default controller order `LeftThumbstick` then `DPad` from
`Celeste.Settings.cs` 298 onward.

- MoveX uses threshold 0.3, MoveY 0.7 and Aim uses binding threshold 0 followed
  by a radial 0.25. Analog thresholds compare normalized float magnitudes, not
  raw byte cutoffs.
- For each direction the stick is checked before DPad. A zero or below-threshold
  stick falls through to DPad; a nonzero Aim stick shadows the same-direction
  DPad before radial deadzoning.
- Opposite movement directions use the source integer-axis `TakeNewer` state:
  first overlap inverts the prior value, further overlap holds, release restores,
  and overlap from zero stays zero.
- Opposite Aim directions compare magnitudes, then use the source joystick
  `TakeNewer` state; equal nonzero input from a zero value stays zero.
- Aim uses the source eight-way snap: strict `<` with a 22.5 degree threshold for
  nonnegative angles and 17.5 degrees for negative angles, in the source check
  order and with `AngleDiff` wrapping. Zero Aim stays zero so the existing Player
  facing fallback remains source-compatible. Diagonal integers are normalized by
  Player, not duplicated here.

The raw Vita mapping is a **fixture assumption**, not original-source or
hardware calibration: standard `SCE_CTRL_MODE_ANALOG` bytes are assumed centered
at 128, right/down positive, with `(v-128)/128` on the negative side and
`(v-128)/127` on the positive side. `SCE_CTRL_MODE_ANALOG_WIDE` is not used.
An invalid reading normalizes to neutral; it must never turn zero-initialized
`lx`/`ly` into full up-left. The Vita app still throws when the SDK sampling call
does not return exactly one sample. Raw and resolved values are logged for later
physical calibration without claiming a hardware pass.

## Verification

```sh
/usr/bin/cmake -S . -B .audit/native-buffered-input/host \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=/usr/bin/c++
/usr/bin/cmake --build .audit/native-buffered-input/host -j2
/usr/bin/ctest --test-dir .audit/native-buffered-input/host --output-on-failure
python3 -B scripts/check_native_oracle.py --domain input \
  --native .audit/native-buffered-input/host/native_input_trace_runner
```

The optional differential uses the **existing** private SDK 8.0.425/runtime
8.0.31 under `.audit/native-oracle/tools`, offline. No new SDK acquisition is
needed. `extract_native_oracle.py --domain input` verifies PC 1.4.0.0 input SHA256
`fd73f8a2311fa5737ded550cbad4b75c85b7686b36432f59185e940fcb65fcfe` and private
`Monocle.VirtualButton.cs` SHA256
`ae7c19ab7a08ddf2c2f5e8e31e2305ba9334f149573f9b01d78cac16291e8cbb`.
It copies the entire class unchanged (inclusive lines 5–163); the generated
private manifest pins the extracted block too. Maintained shims supply only
Binding booleans, disabled/debug-key values, abstract VirtualInput and Engine's
sampled delta. The runner inspects private counters outside that class.

Both runners execute `tests/native/input.fixtures`. Every operation produces
before/after rows, including queries, sample/configuration changes, updates and
consumption. The validator checks all 21 field grammars and fixture-derived
ordered operation/phase, sample, configuration and delta coverage **before**
comparing raw float32 counter bits, flags and queries. It rejects identical
malformed, missing, duplicated, reordered and foreign rows while allowing
legitimate repeated operations and arbitrary valid fixtures. Divergence reports
the first differing field, with no tolerance. Actor and scheduling retain their
separate strict grammars; only scalar fixture parsing is shared.

This establishes unchanged extracted-class compatibility on synthetic inputs,
not original CIL execution, complete game fidelity, Vita hardware input or
performance. VitaSDK static compilation with `BUILD_TESTING=OFF` is not execution.
Private evidence is under `.audit/native-buffered-input` and
`.audit/native-oracle/input`; source/tools/game assets stay uncommitted.
The [bounded Player slice](NATIVE_PLAYER.md) composes this button without adding
hardware Binding or a general engine loop.
