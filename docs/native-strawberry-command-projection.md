# Bounded native Strawberry Sprite projection

Append `--strawberry-commands <private-catalog>` to
`native_room_transition_trace_runner`. It composes with the existing 6/7/8
positional-input forms, Spike, Terrain, Player, static/full Decal and Banner
phase observers. The catalog is validated before trace publication.

`strawberry_commands::project` reads the actual draw dispatch, live room roster,
native entity identity/authored id and `RoomStrawberry` visual state. It does not
update anything, call Player Draw, consume RNG, or load expected Source commands.
The existing Strawberry initialization/update hook is unchanged.

The source idle animation has **36 animation positions but only eight texture
frames**: `(0..6)` four times followed by `(0..7)`. Native `sprite_frame` is the
animation position; the private catalog maps it to the texture frame. Sprite
position is body position plus the existing unrounded `light_y` wobble offset.
Origin is half the untrimmed frame size plus the atlas offset. The represented
normal, seedless, uncollected, non-winged branch is white, unit scale, zero
rotation and `None` effects. Collection remains guarded by `Strawberry.OnPlayer`;
animation position 35/pulse and later branches are explicitly unsupported.
There is no invented follower, leader, idle-spin or route-table state.

## Private catalog

`scripts/prepare_strawberry_material_catalog.py` reads the pinned original
Strawberry source, atlas JSON and `Sprites.xml` **in place**, checking all SHA-256
pins before creating an exclusive descriptor directory under canonical
`.audit/native-strawberry-command-projection-01/`. It writes eight atlas
clip/trim/frame records and the idle sequence, not images, sheets or Source
bodies. Original keys, rectangles and generated catalogs must not enter Git.

`CSTR1` is newline-terminated ASCII: version, three provenance pins (original
Strawberry source, atlas, sprite XML), `idle 36`, one sequence row, count `8`,
then eight ordered `index sheet x y width height offsetX offsetY frameWidth
frameHeight texture` rows. The runner pins its FNV-1a integrity; this checksum is
not a substitute for the preparer's SHA-256 provenance checks. Parsing rejects
unknown animation/version, missing/unordered frames, duplicate keys, invalid
numbers/bounds/provenance, truncation and trailing data. Spike and Strawberry
reuse the same atlas text parser and command serializer/geometry helper.

## Focused proof

```sh
CELESTE_STRAWBERRY_NATIVE_TRACE=<fresh-native-trace> \
python3 -B tests/native/test_strawberry_command_projection.py -v
```

The test streams the frozen accepted Source oracle in place. It compares all
514 frames and 140 ordered Sprite commands, every logical field and all 2,800
pre-batch XYZUV float32 components. Commands begin at load tick 374; incoming
state is frozen through tick 413, with the first eligible update at 414.
Source process-local entity/component tokens are bound to the authored room,
position and Sprite component; native identities bind to actual roster/dispatch
and whole-owner order. Negatives cover genuine known-identity exchange, alias,
unknown identity, lifetime, animation-vs-texture index, phase, clip and geometry.
Lifetime inference is limited to this zero-reload recording. A synthetic test
only verifies that fresh native instances expose distinct identities; it does
not claim generic route reload support.

This is logical CPU Sprite projection only. The recording contains no separate
Strawberry Bloom/Light submissions, so their graph is **not** closed. No full
Level rendergraph, shader/light behavior, GPU/Vita, pixel or scissor parity is
claimed. Physical RNG 19/15 and global 946 describe the accepted stripped
contract, not equivalence to full unstripped Source initialization.
