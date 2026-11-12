# Bounded idle Floor Spring commands

`--spring-commands CSPR1` adds a read-only logical command observer to the native
room-transition runner. It composes with the existing positional forms and
Player, terrain, decal, Banner, spike, JumpThru and Strawberry observers.

The projector binds each dispatched Spring to its actual native room entity and
authored identity. It reads the current body position, emitting eight opaque
black outline images in x-outer/y-inner order, followed by the opaque white main
image. Native entities and random streams are not created, updated or mutated by
sampling. Piece indices distinguish the nine commands without inventing physical
component identities.

The constructor uses logical bottom-center, not the center of the clipped crop.
Atlas metadata stores negative trim offsets; MTexture negates these into its
DrawOffset. Submitted origin is therefore `(logicalWidth / 2, logicalHeight)`
plus the raw atlas offsets. Shared native geometry arithmetic and serialization
are reused without replaying expected Source positions or vertices.

## Private preparation and integrity

`scripts/prepare_spring_material_catalog.py` accepts seven pinned cached inputs:
Spring, Sprite, GraphicsComponent, MTexture, Image, raw atlas metadata and its
JSON projection. It verifies every SHA-256 before creating an exclusive output
directory. It validates the complete bounded constructor family, matching raw
and JSON metadata and logical dimensions, but writes only the idle frame.
Sprites.xml and atlas images are not inputs; other catalogs are not regenerated.

The small private CSPR1 format contains the seven provenance pins, the explicit
Floor/idle/frame-zero/zero-wiggler contract, one frame count and one atlas row.
The loader reuses `atlas_frame_text.hpp` and `asset_text.hpp`; schema, pins,
resource, sheet, integer/crop/trim bounds, trailing data and build-pinned integrity
must validate before the runner publishes output. FNV-1a is build integrity, not
cryptographic provenance. No catalog or original asset payload belongs in Git.

## Supported state and verification

The native representation currently constructs only Floor Springs. Projection
rejects non-Floor collider shapes, active wiggler values, disabled/noncollidable
or unattached bodies and invalid native identity/dispatch bindings. Existing
Spring interaction exceptions remain unchanged. There is no bounce animation,
wall Spring, sound, particle, cooldown, gameplay or physics implementation here.

Synthetic C++ tests cover ordering, colors, signed trimming, odd logical widths,
negative world coordinates, XYZUV bits, actual body reads, purity, catalog
negatives and identity/lifetime guards. Python tests bind the frozen original
authored Spring independently by room, authored ID and position, then verify
Source component ordering: outlines are direct entity rendering; only the main
image is attributed to ComponentList's Sprite dispatch.

The differential checks all 514 frames, including 374 empty frames, 1,260 ordered
commands and 25,200 XYZUV components. Runtime and tamper tests also validate the
actual native roster, dispatch, body state and immutable lifetime ID mapping.
Identity lifetime claims are limited to this zero-reload route.

Other accepted command streams, physical RNG scopes and CPU phases remain
regression requirements. The stripped profile's RNG contract is not complete
unstripped Source RNG equivalence. ParticleSystem commands remain outside this
closure; no GPU, scissor, full Level/light/shader graph, pixels or Vita execution
is claimed. The broad quota-sensitive aggregate is not a globally green claim.
