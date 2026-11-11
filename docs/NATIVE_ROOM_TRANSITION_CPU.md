# Bounded CPU room transition candidate

This candidate extends the production `FirstRoomSession` through an optional
`RoomCatalog`, also forwarded by `diagnostic::Session`. Existing constructors
retain their single-room path. It is not a GPU, package, physical or full Room 2
claim. It is pending parent simplification and fresh independent review.

Actual bounds and the authored neighbor lookup queue an EOF request. EOF creates
a `Coroutine`; its next update allocates incoming typed room objects before
publication/removal. Player, presentation, world, collision, global Solid and Grid
storage persist. Movement uses Actor exact positions/remainders, not respawn or
teleportation. Completion removes outgoing collider/roster pointers before their
objects are destroyed. The outgoing wind leaves the live roster during loading,
as in SOURCE; its reference remains held through completion.
The initial componentless helper models original `Scene.HelperEntity`, which is
also a nonpersistent entry removed by the first transition.

Normal updates follow the depth/birth-ordered live roster. During transition,
only TransitionUpdate-tagged room objects and the coroutine update. Hair still
runs AfterUpdate with motion approach disabled. Input/clock sampling occurs once.
Existing Global-only trail snapshots also pause during transition; a separate
legal-control Dash variant verifies this filter, not SOURCE parity for that variant.
Scene/session/save clocks, room deaths, chaser timestamps/clear and actual RNG
state/room constructor scopes are observed. The source death reset is zero-to-zero
in this route, not evidence of a nonzero history reset.

Destination JumpThru uses the existing Actor collision path and safe-ground list.
Spring attachment and its idle wiggler, and the reached Strawberry wobble,
sprite/light advancement, have bounded native state. Spring/berry contact,
Room 2 death/reload, Dash/freeze crossing, additional exits, nonzero wind and the
later Strawberry pulse fail loudly. Puffer/holdable materialization is rejected;
their unproved collision bodies are not neutral stubs.

`prepare_native_transition_fixture.py` generates private catalog metadata from
the pinned SOURCE two-room fields, verifying the reused two-room mask. It does
not contain outcome states. It preserves authored entity kinds/order and computes
normalized origins/spawns/seeds. The older generated `rooms.txt` remains preserved;
its generic `type` attribute had overwritten spike names.

`room_transition_trace_runner.cpp` drives only legal fixed controls from the real
spawn, without drawing. Its five-phase observations use actual construction
tokens, member storage and owned room/collider references, never C# ID strings.
The separate native negative API fixtures are explicitly not SOURCE route frames.

`tests/native/room-transition.fidelity.json` is the explicit projection/leaf
manifest. `compare_native_room_transition.py` does not alter the raw SOURCE or its
existing comparator. Integers and booleans retain exact JSON types; only matching
float observations compare float32 bits. This is semantic correspondence, not
complete managed component-container or graphics equivalence.

The grounded idle selector preserves original empty-versus-null semantics.
Original public `Sprite` construction, reset, stop and terminal completion assign
an empty non-null animation ID. `PlayerSprite` uses that constructor; its bank and
the native constructor publish a valid `idle` animation. The internal clone-only
constructor has a transient null, replaced by `CloneInto` before publication; this
bounded native API does not expose it. Native `std::string` therefore needs no
nullable field: an empty completed animation is eligible for grounded idle
recovery. Existing idle variants are not restarted, and carry/holdable animations
remain unsupported. No other empty-string check is changed.

The full 514-frame semantic projection includes the formerly failing frame 492;
there is no prefix-only acceptance or animation exclusion. Broad simplification
and fresh independent review remain parent-owned prerequisites for acceptance.
