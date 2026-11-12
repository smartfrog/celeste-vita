# Bounded JumpThru logical commands

The opt-in CPU observer independently projects the destination room's five
JumpThru Images: zero commands at ticks 0–373 and five at ticks 374–513, totaling
700 ordered commands across the accepted 514-frame room-1 → room-2 landing route.
This does not wire `src/vita/diagnostic.cpp` or a production renderer.

## Independent visual initialization

`RoomRuntime` continues the **same detached generator** used by Banner Added,
after foreground then background Banner phases, through JumpThru Awake choices
in entity order. The copied observer is cleared before either visual operation.
The shared `choose_jump_thru_cells` retains full-body solid probes at X ±1,
first-column precedence, `Next(1)` and the two-way row choice. Physical
`image_cells` use the original scoped stream separately, without extra draws.

For room 2 / seed 50, visual interior rows are `1,1,0`; physical rows remain
`0,0,1`. Neither physical cells nor RNG state/events are rewritten to fit SOURCE.
Room scopes retain seed/calls 49/19 and 50/15; final global calls remain 946.
This is an explicit detached visual initialization contract, **not full
unstripped SOURCE RNG equivalence**.

Visual cells are private room-instance state, keyed by actual native object
identity. The const lookup throws when absent. Null visual metadata preserves
legacy physical behavior and creates no visual choices; projection never falls
back to physical cells. Existing session metadata injection covers loads,
transitions and reloads. Retained rooms keep their choices until normal
destruction. No update, timer or draw mutation is needed.

## Material and projection

`prepare_jumpthru_catalog.py` checks the actual cached JumpthruPlatform, MTexture
and Image SOURCE hashes, original `Gameplay.meta` and private atlas JSON hashes
before creating an exclusive private `CJTC1` catalog. The one wood material is
derived from matching metadata records, not SOURCE per-frame commands. The
catalog remains outside Git. Existing `CDSC1`/`CDSC2` APIs are unchanged.

The wood logical frame is 24×16 but its atlas clip is 24×12 with zero trim.
Original `MTexture.GetSubtexture`/`GetRelativeRect` clamps row-1 Images to 8×4,
while their logical subtexture size remains 8×8. Logical frame dimensions need
not fit the clip. Nonzero trim and other materials are rejected in this bounded
profile rather than approximated.

`jumpthru_commands::project` is pure/read-only. It binds each dispatched owner to
the actual room instance, entity identity, authored ID and body, then emits
ordered cells at `body.position + (8 * piece, 0)`, zero origin, unit scale,
white color, zero rotation and `None` effects. Unknown/aliased identities,
same-kind identity swaps, missing cells, invalid variants and lifetimes fail
loudly. No SOURCE process-local Image ID becomes a native identity.

The runner accepts `--jumpthru-commands /private/CJTC1-catalog` with complete
authored CDO1 metadata. It composes with Player, Terrain and either decal mode;
it adds no Player Draw call. Legacy 7/8/9 positional invocations remain valid.

## Verification boundary

Fresh Release and ASan/UBSan builds each pass 46 CTests. Fresh native combined
runs compare all 700 logical commands and independent SOURCE owner/Image
bindings, and preserve 605,992 Terrain, 11,938 Player and 49,854 Decal commands,
including 997,080 Decal geometry float32 words and 5,929 nonfinite submissions.
Four fresh stripped-CPU runs (Release 7/8/9 and ASan 9) compare 2,570 phases each,
without extra Player Draw. Immutable SOURCE draw/CPU oracles are reused in place.

Evidence is private under canonical `.audit/native-jumpthru-command-projection-01/`;
failed attempts are retained. Independent review and simplification remain parent
gates. No commit, development update or push is authorized. The broad quota-bound
Python aggregate is not claimed green. Full geometry, rendergraph, GPU, pixels,
hardware/Vita and off-route fidelity are outside this increment.
