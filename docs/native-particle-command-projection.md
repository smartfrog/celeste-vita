# Bounded native default-Dust projection

`native_room_transition_trace_runner --particle-commands <private-CDUS1-catalog>`
composes with all existing positional forms and command observers. Validation
precedes trace output. Commands run at the existing after-frame boundary; this
observer never calls Player Draw, updates a Scene, or consumes random samples.

The level-owned `DustParticles` pool receives copies of the **existing** native
Jump/landing birth samples. The physical birth vector, nine-sample sequence
(including zero-range spin), RNG observer, and global glitch-before-Player order
are unchanged. There is no visual reseed, stream compensation, Source-position
replay, or per-frame production table. `Level.Particles` binds the persistent
mid-particle owner in the real native draw projection, not a fake room entity or
a process-local Source token. BG/FG command streams remain empty in this scope.

The supported type is explicitly default `ParticleTypes.Dust`: four chooser
textures; static white StartColor/Color; ColorMode Static; FadeMode None; raw
delta time; acceleration `(0,4)`; friction zero; speed multiplier one; random
initial rotation; zero spin; cubic scale-out. StartLife and StartSize persist.
Update uses the life ratio **before** decrement, expires before motion, moves
before acceleration, and scales from StartSize. Births update on their first
scene frame, including frames on which the Player dies. Engine freeze skips
updates; corpse scene frames do not. Transition frames skip aging but continue
rendering, including the frame ending the transition. At transition completion,
ClearRect uses the incoming bounds inflated by 16 and strict interior tests.
Clear does not reset the 400-slot cursor. Slot reuse advances generation;
render order is slot order, not age order. Coordinates truncate toward zero,
and origin is original frame Center, without atlas trim offset.

This is not a general particle framework: SparkyDust/material-40, other PTypes,
tracked particles, alternate fade/color/spin modes and new emitter/wind branches
are not proved. The type boundary rejects unsupported types. No new physical
or surface-index semantics are introduced by this projection.

## Private materials and proof

`scripts/prepare_particle_material_catalog.py` reads the pinned cached
`TransitionExtracted.cs` and atlas in place. Both SHA-256 pins are verified before
creating an exclusive private output directory under canonical
`.audit/native-particle-command-projection-01/`. `CDUS1` contains two pins, the
`Dust 4` type/count declaration and four atlas-frame records; the runner pins its
FNV integrity. It reuses the common atlas parser and command geometry serializer.
Generated keys, rectangles, catalogs, images and Source bodies do not enter Git.

The test-only frozen Source trace has SHA-256
`8af9703eff54511307b57170bd7bbc98fb8efcd58eb5d7e9ef2e0972ab378073`.
The first gate proves four tick-83 births, sample groups 85–93 through 112–120
after glitch call 84, full initial state from detached test-only arithmetic, all
logical fields, and every XYZUV word. Route comparison covers all 514 frames,
1,235 ordered commands, actual owner/slot/generation bindings, and transition
freeze/clear edges. Seed 1 and the preburst call count appear only in test facts,
not production. This bounded route result is not a general claim of equivalence
to full unstripped Source initialization or all possible emission provenance.

```sh
CELESTE_PARTICLE_NATIVE_TRACE=<fresh-native-trace> \
python3 -B tests/native/test_particle_command_projection.py -v
```

Logical CPU commands only: no shader, GPU, Vita, pixel/scissor parity, or full
Level rendergraph closure. Source NaN Decal geometry remains guarded and is not
fed to a GPU. Review and simplification remain coordinator gates before merge.
