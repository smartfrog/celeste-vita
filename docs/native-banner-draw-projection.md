# Bounded Banner CPU draw projection

The native two-room CPU observer projects all 52 authored Decal owners: 41 static
owners / 11,746 commands and 11 Banner owners / 38,108 commands over the accepted
514-frame route. All 49,854 logical tuples and original pre-batch geometry float32
bits compare exactly, including 5,929 zero-height/nonfinite geometry submissions.
This is not full Level, unstripped SOURCE RNG, GPU, pixels or Vita equivalence.

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
Banner state stores only owner identity/current float phase in that room runtime.
The same detached stream subsequently initializes independent JumpThru visual
cells; see [the JumpThru contract](native-jumpthru-command-projection.md).

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
Original atlas metadata independently confirms all 27 authored families are
singletons; SOURCE lines 505–510 therefore do not advance their frames.

Incoming phases receive no load-frame update. Both room states pause through
transition; outgoing state belongs to `outgoing_room_` until unload. Reload
creates fresh phases even when authored identities/definition names repeat.
Drawing and phase lookup do not advance state. Missing phases fail loudly.

## Shared descriptors, strip math and geometry

The reviewed static module and `DecalCommand` are extended, not replaced.
The descriptor generator retains byte-compatible `CDSC1` static-only output and
adds explicitly selected `CDSC2`: 27 original atlas frames, unchanged static and
Banner owner bindings, plus four family parameter records extracted from the
pinned original `MakeBanner` cases. Float parameters are serialized as bits.
Inputs are pinned atlas/CDO1/Decal metadata, never expected draw frames or phases.
Animated, windy, missing and aliased metadata are rejected rather than guessed.

Banner wave evaluation retains float argument arithmetic, double sine/products,
the final float cast, integer frame halves, original trim/subtexture clipping,
signed scales and strip order. Source rectangles with zero height remain commands.
The separate CPU-only `project_geometry` helper follows original SpriteBatch
normalization and vertex arithmetic, serializing all four XYZ/UV vertices as
signed float32 bit integers. Logical fields remain finite while zero-height
normalization produces the original nonfinite vertex bits. No GPU finite guard
is changed and these observations are not GPU-consumption or safety approval.

The trace runner accepts `--decal-commands /private/CDSC2-catalog` with complete
CDO1 positional inputs. It initializes phases before room load and emits ordered
`decal-command` records, including `finiteGeometry` and `verticesFloat32Bits`.
`--banner-phases` adds read-only lifetime observations. Existing
`--static-decal-commands /private/CDSC1-catalog` still projects only the 41 static
owners and explicitly defers the 11 Banners; its old flag/format remain intact.
The two decal modes are mutually exclusive. Neither observer adds a Player draw.

## Checks and review boundary

`native_banner_unit` covers initialization order/physical RNG isolation, float
accumulation, transition pause, actual session injection, repeat drawing, natural
Dash freeze, natural hazard/corpse/reload, and invalid metadata/phase controls.
The trace runner's optional `--banner-phases` requires complete CDO1 metadata;
it adds read-only observations without an additional `session.draw()`.
`test_banner_phases.py` checks all 514 route frames and rejects phase-bit,
identity, lifetime and missing-phase mutations when supplied a fresh trace via
`CELESTE_NATIVE_BANNER_PHASE_TRACE`.
`test_banner_commands.py` compares all ordered Source logical fields and geometry
bits, and rejects missing/swapped owners, float/sign/Source-field/descriptor and
nonfinite-bit mutations. Release and ASan/UBSan are checked separately, alongside
the existing static, Player, Terrain, owner and stripped-CPU comparisons.

Private evidence is retained under the canonical
`.audit/native-banner-draw-projection-01/`. All raw failed attempts are retained.
The aggregate Python run encountered existing hard-coded host `/tmp/opencode`
quota errors and an unset host-temp fixture; it is not reported as passing.
The phase-only prerequisite review is not full draw acceptance. Full working-diff
simplifier/reviewer acceptance remains a parent gate. The only authorized commits
are the phase WIP checkpoint and normal merge of reviewed development; no delivery
commit, development update or push is part of this increment.
