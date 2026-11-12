# Bounded native spike command projection

`native_room_transition_trace_runner` keeps its 6/7/8-positional-argument
update-only behavior. Appending `--spike-commands <material-catalog>` emits one
logical CPU command for every piece of every live Up/Left spike owner after the
existing post-update draw-owner projection. The option remains composable in
either order with `--player-commands`, `--terrain-catalog` and
`--static-decal-commands`.

The projection reads the actual native `RoomEntity.image_cells`, entity position,
authored id and the existing native draw dispatch. Piece order is the native
component/`image_cells` order. It does not render, step physics or input, re-run
the timestep, consume RNG, or read the SOURCE trace. The accepted SOURCE trace is
a test oracle only.

## Private material catalog

Only two atlas frames are missing from the existing native spike data. The owned
preparer reads the pinned original `Celeste.Spikes.cs`, the pinned original
`Gameplay0` atlas metadata and the pinned bounded two-room metadata, validates
their SHA-256 pins and room spike owner/piece/direction facts, then writes one
small private catalog outside Git:

```sh
python3 -B scripts/prepare_spike_material_catalog.py \
  --atlas <pinned-original-atlas.json> \
  --spikes-source <pinned-original-Celeste.Spikes.cs> \
  --rooms <pinned-two-rooms.json> \
  --output <fresh-file-under-canonical-.audit>
```

`CSPK1` is newline-terminated canonical ASCII:

- Version; three 64-character lowercase SHA-256 provenance pins (Spikes source,
  atlas metadata, room metadata).
- Frame count 2; exactly one `up` row then one `left` row.
- `direction sheet x y width height offsetX offsetY frameWidth frameHeight texture`.

The catalog stores the original sheet, clip/trim/frame data and texture key. It
is generated data and must never enter Git. The runner pins its FNV-1a integrity;
the parser also checks bounds, canonical integers, duplicate keys, unknown or
unordered directions, checksum, truncation and trailing data. FNV-1a is build
integrity, not provenance authorization. The bounded room preparer also rejects
non-default spike types, so unsupported variants cannot silently reuse this
catalog.

## Logical command contract

Each emitted command carries the native owner identity, room, authored id,
direction, piece, original texture/sheet, unchanged source rectangle, world
position, origin, scale, color, rotation and effects.

- Up: world position is `entity + ((piece + 0.5) * 8, 1)`; origin is
  `frame/2` horizontally and `frame` height minus the atlas draw offset
  vertically.
- Left: world position is `entity + (1, (piece + 0.5) * 8)`; origin is
  `frame` width minus the atlas draw offset horizontally and `frame/2`
  vertically.
- Scale is `(1,1)`, color is enabled white, rotation is zero and effects are
  `None`, matching the bounded non-disabled, non-shaken route. These are
  source-faithful branches, not arbitrary defaults.
- A spike owner is matched by its live native roster entity identity, never by
  kind alone. Missing/aliased/double-dispatched owners, foreign room bindings,
  unsupported directions, non-singleton image cells, incomplete image-cell
  counts and absent catalog families fail loudly before trace publication.

## Route proof

The focused test streams the frozen accepted SOURCE trace in place and compares
all 514 frames and all 9,107 ordered spike commands, including every logical
field above:

```sh
CELESTE_SPIKE_NATIVE_TRACE=<fresh-native.jsonl> \
CELESTE_SPIKE_CATALOG=<private-catalog.txt> \
python3 -B tests/native/test_spike_command_projection.py
```

The route has 19 commands on ticks 0-373, 28 on ticks 374-412 (room 1 outgoing
commands before room 2 incoming commands) and 9 on ticks 413-513. The native
projection emits no commands when the option is absent; all legacy loaders,
Terrain, Player, Static decal and CPU comparisons are unchanged.

This claims logical CPU Up/Left spike command identity, order and geometry only.
It does not claim full-owner command interleaving, GL/GPU, vertices, pixels,
scissor, hardware, Vita or full Level parity.
