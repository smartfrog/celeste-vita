# Banner presentation state: independent increment

Status: initialization/update only. Logical Banner command projection is blocked
on the reviewed static decal descriptor/shared-command dependency. No Banner
commands, nonfinite geometry preservation, combined Decal parity, full Level,
unstripped SOURCE RNG, GPU, pixels or Vita equivalence are claimed here.

## Initialization boundary

The pinned original `Celeste.Decal.cs` SHA-256 is
`81d04a56cb9b5cb981f3c7823388bed6082db2d5755d364c15c35bbcaf8b7746`.
`Decal.Added` creates Banner (lines 163–182, 372–395); its field initializer
consumes `NextFloat` (line 30), not the Decal constructor.

`RoomRuntime` optionally accepts the existing authored CDO1 owner metadata.
After physical object construction and before JumpThru Awake, it copies the
current scoped generator, immediately clears the copied observer, then consumes
one float-cast `next_double()` per classified Banner: foreground placement
ordinals first, then background placement ordinals. Neither render ordering nor
elapsed frame numbers determine the phase. The copied generator stays local;
only owner identity/current float phase are stored in that room runtime.

The actual room load seed is used, not a route-specific reseed. Tests derive
constructor consumption from the object definitions: seed 49 reaches visual
draws 20–26; seed 50 reaches 10–13 before the six physical Awake draws. Physical
scopes retain 19/15 calls and unchanged state/observer events. This is a detached
visual initialization contract: physical Awake consumption is deliberately not
shifted as it would be in the unstripped SOURCE load.

## Lifetime and updates

`FirstRoomSession` accepts a read-only optional visual catalog before its initial
load and passes each exact definition's metadata into initial, incoming and
reload room creation. The catalog and metadata must outlive the session. It
reuses authored-owner validation and rejects foreign same-name room bindings,
incomplete counts, invalid kinds and aliased/out-of-namespace identities.

The catalog update branch advances the current room's phases once, before the
physical roster loop, only for nontransitioning simulated passes outside the
committed-corpse branch. It adds the sampled `context_.clock.delta` using float
arithmetic. The pinned eleven Banners all have `OnlyIfWindy=false` and multiplier
one (SOURCE lines 28, 41–55); this is not a general windy/animated decal engine.
Render wave/trim/strip math remains unimplemented pending the shared dependency.
Original atlas metadata independently confirms all 27 authored families are
singletons; SOURCE lines 505–510 therefore do not advance their frames.

Incoming phases receive no load-frame update. Both room states pause through
transition; outgoing state belongs to `outgoing_room_` until unload. Reload
creates fresh phases even when authored identities/definition names repeat.
Drawing and phase lookup do not advance state. Missing phases fail loudly.

## Checks and remaining work

`native_banner_unit` covers initialization order/physical RNG isolation, float
accumulation, transition pause, actual session injection, repeat drawing, natural
Dash freeze, natural hazard/corpse/reload, and invalid metadata/phase controls.
The trace runner's optional `--banner-phases` requires complete CDO1 metadata;
it adds read-only observations without an additional `session.draw()`.
`test_banner_phases.py` checks all 514 route frames and rejects phase-bit,
identity, lifetime and missing-phase mutations when supplied a fresh trace via
`CELESTE_NATIVE_BANNER_PHASE_TRACE`.

Private evidence is retained under the canonical
`.audit/native-banner-draw-projection-01/`. All raw failed attempts are retained.
The aggregate Python run encountered existing hard-coded host `/tmp/opencode`
quota errors and an unset host-temp fixture; it is not reported as passing.
Independent simplifier/reviewer acceptance and the static dependency integration
remain parent review gates. No commit or push is part of this increment.
