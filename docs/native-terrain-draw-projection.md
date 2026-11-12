# Persistent native terrain projection

`src/core/terrain.*` parses a visual catalog and streams camera-window commands
through a const consumer. It does not use collision bits, room-owned draw lists,
expected per-frame commands, simulation, RNG, or graphics APIs. Null cells are
implicit; two persistent indexed grids share material and sheet tables. Projection
allocates no per-frame command array and traverses x outer/y inner, skipping nulls.
The existing draw-owner projection still determines owner interleaving. Terrain
commands are exported as separate BG (+10000) and FG (-10000) layers bound to those
existing persistent global owners, not concatenated room snapshots.

## Private preparation and format

`scripts/prepare_terrain_catalog.py` reads the accepted original bake in place.
All six input SHA-256 pins (commands, atlas, result, RNG, driver, sheet dimensions)
and result artifact/seed/count bindings are checked before any output is created.
No new autotiling, SOURCE execution, image extraction, or image copying occurs.

```sh
python3 -B scripts/prepare_terrain_catalog.py \
  --commands "$COMMANDS" --atlas "$ATLAS_JSON" --result "$RESULT" \
  --rng "$RNG_JSON" --driver "$DRIVER" --sheets "$SHEETS" \
  --output "$AUDIT/catalog.txt"
```

`AUDIT` is the canonical repository's `.audit/native-terrain-draw-projection-01`.
Outputs must be fresh. The generated catalog contains original private atlas keys
and must never enter Git. Public tests use only synthetic identities.

`CSTV1` is newline-terminated canonical ASCII:

- Version; four 64-character lowercase SHA-256 values: commands, atlas, bake result,
  accepted gameplay-DRAW profile binding.
- `originX originY columns rows tileSize visualExtend` (tileSize 8, extend 1).
- Sheet count, then `name width height` rows.
- Material count, then `sourceAtlasPath sheetIndex u v width height offsetX offsetY
  frameWidth frameHeight r g b a alpha`. Only 8x8, zero offset, 8x8 frame,
  opaque white, alpha 1 are supported.
- Layer count 2; `B 10000 cellCount`, then `x y materialIndex` rows; likewise
  `F -10000 cellCount`. Each layer has strictly increasing `(x,y)` identities.

Dimensions/counts/indices/ranges, sheets, material uniqueness, duplicate cells,
version, truncation, trailing bytes and numeric spelling are checked. The core
parser is source-independent and accepts an expected FNV-1a checksum supplied by
its caller. This is an integrity pin, **not cryptographic authorization**. The
test runner pins this generated asset to `16d1da6c`; malformed input is rejected
before any trace output. The accepted asset has 48,815 cells (21,900 BG / 26,915 FG),
origin (-64,-3272), dimensions 541x440; it is not the old 1,840-command room parser
and implies no GPU capacity.

## Camera and observer

Frozen `TransitionExtracted.cs` `TileGrid.GetClippedRenderTiles/RenderAt`
(11572–11621) supplies origin-relative floor-left/top, ceil-right/bottom,
one-tile extension and grid clamping. `Camera.UpdateMatrices` (9872–9875) floors
camera position before deriving viewport edges. Here this is the accepted
GameplayRenderer camera alias at 320x180, unit zoom, zero angle/origin, **not** the
complete Level.BeforeRender hook graph. Session camera state is never modified.
Partial edge tiles remain full 8x8 logical quads, including negative world positions
and extension/filler cells; there is no room scissor. A viewport beyond catalog
bounds is explicitly reported by `Window.outside_catalog`, with safe empty/partial
clamping rather than invented terrain.

Append `--terrain-catalog "$AUDIT/catalog.txt"` to the existing 7/8/9-argument
`native_room_transition_trace_runner`. It may be combined in either order with
`--player-commands "$PLAYER_MAPPING"`. Legacy modes stay update-only; terrain
observation never calls `draw()`, and Player opt-in still calls it exactly once.
The observer emits one descriptor table and two terrain blocks per tick; each
compact command is `[materialIndex, worldX, worldY]`. Array order is render order.
Each block records actual session camera, renderer camera, window and owner.

```sh
python3 -B scripts/compare_native_terrain_draw.py \
  --source "$FROZEN_SOURCE_TRACE" --native "$NATIVE_TRACE" \
  --output "$AUDIT/comparison.json"
```

The separate test-only comparator streams all 514 frames and compares all 605,992
ordered logical terrain commands, not counts alone. Logical fields use exact
float32 semantics. SOURCE `verticesFloat32Bits` are signed IEEE754 words encoding
pre-batch XY/Z/UV; their finiteness is checked, but they are not logical-position
bits or a claimed native vertex/GPU comparison. Terrain has no Banner-NaN exception.

## Coverage boundary

The accepted route observes 2,980 distinct cells and all authored cells of rooms
1 and 2. The remaining 45,835 cells (36 other rooms and unobserved extension/filler)
are accepted on exact provenance only, not per-cell behavioral verification.
Requiring behavioral assurance there requires a separately authorized frozen-profile-02
full-grid static bake/comparison. Moving the camera there does not upgrade that
claim. The full catalog is deliberately retained, not reduced to route playback.

No full-owner command interleaving, full-Level rendergraph, shaders, scissor,
vertices, GPU, pixels, hardware or Vita equivalence is claimed. Physics, input,
timestep and RNG are unchanged. The independent sweat correction is not included;
the existing Player comparison must still report its known 52 mismatches at this base.
