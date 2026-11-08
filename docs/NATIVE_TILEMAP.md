# Bounded native static tilemap

The native kernel accepts **Hitbox queries against immutable target TileGrids**.
The private offline tool prepares the full ForsakenCity global static solidmask,
not an isolated room mask. Explicit room `1` supplies the spawn/probe fixture.
This is headless collision and bounded Normal locomotion, **not a playable room**,
verified startup selection, full map/runtime loader or Vita execution.

## Native contract

```cpp
const celeste::TileGrid grid(2, 1, {1, 1});
celeste::Body tiles{{0, 144}, std::nullopt, true, &grid};
celeste::PlayerWorld world{{{&tiles}, {}}, {&tiles}};
celeste::Player player(world, {19, 144});
```

`Body.grid` is appended and defaults to null; existing Hitbox aggregate
initializers retain their behavior. A body cannot have both shapes. Grid cells
are row-major bytes, exactly zero/one; data length must equal columns × rows.
Columns/rows can be zero, never negative. Cell width/height are explicit positive
finite float32 values (8×8 for real SolidTiles). Collider offset and body position
compose in source order. Grid data/size/offset are immutable; grids, bodies and
world must outlive their users. Player retains the static-world/lifetime/profile
constraints and explicit safe-ground **Body pointer** identities.

Only target Grid dispatch is added. Actor/Player query colliders remain Hitboxes;
Grid queries, mixed shapes, other colliders, moving platforms, carry/push/lift,
hazards, bounds enforcement, room transitions, rendering and audio are excluded.
No virtual collider hierarchy or arbitrary unsupported-shape fallback exists.
World list order, callback identity/payload/order, subpixels and old Hitbox
predicates remain unchanged.

Grid collision uses integer Collider.Bounds: truncate absolute left/top and
width/height toward zero, then strict integer rectangle overlap. Cell endpoints
are `trunc((left-Gx)/cellWidth)` and
`trunc((float(right)-Gx-1)/cellWidth)`, with the analogous Y calculation.
Inclusive ranges are clipped and scanned X then Y. **Floor/ceil are not substitutes**.
Zero-size/fractional query rectangles retain the source predicate, without an
empty-rectangle optimization. The checked cell indexer returns false outside;
raw VirtualMap out-of-range behavior is not modeled.

Nonfinite values, negative dimensions, malformed data, conflicting shapes,
unsafe int32 float conversions/rectangle sums/cell-range arithmetic throw
`std::invalid_argument`. Validation happens when geometry is used; unsupported
Actor Grid queries fail before subpixel accumulation. Source unchecked integer
overflow/nonfinite conversions are outside the differential domain.

## Private offline preparation

No .NET/game execution is required by `prepare_static_tilemap.py`. It reads the
original PC ZIP offline with a small tested standard-library BinaryPacker reader
reused from the private map inventory. It validates both executable and map hashes:

- PC 1.4.0.0 executable: `fd73f8a2311fa5737ded550cbad4b75c85b7686b36432f59185e940fcb65fcfe`
- `Content/Maps/1-ForsakenCity.bin`: `ace1892261c03aa766f45aaa38cb2cd60a8823c34eda673f5b2ed8ab31c890ab`

Only room bounds, solids/background text, filler and the selected spawn are
decoded for this task; no general entity/gameplay conversion is attempted.
The prepared output stays under `.audit`. `provenance.json` hashes the private
driver, mask and generated geometry/Player fixtures and records decoded room facts.

Construction preserves file room order and every supplied character, splitting
CRLF, LFCR, LF or CR. Short rows retain prior/default `'0'`, overlong rows are not
room-clipped, and later zero characters overwrite. Global filler, seven-cell
open-top/bottom reservations and three-cell extrusion are included. Occupied
means char != `'0'`. Global bounds preserve the source's filler/bounds arithmetic;
this is not `Grid.LoadBitstring` or a generic editor/importer.

The actual mask is 541×440 = 238,040 cells, 26,915 occupied. Room `1` has stored
320×184 dimensions normalized to 320×180 bounds, while its 40×23 solids cells
still cover 320×184: 363 occupied (`3`:135, `4`:45, `1`:170, `7`:13), 22 LF/no CR.
All 920 interior cells match the merged construction. Normal movement uses
8×11 at (-4,-11), not the 8×9 hurtbox: spawn (19,144) is clear and (19,145)
collides. Global 1×1 probes (-1,144), (16,-1), (240,-1) hit where isolated data
misses. Actual startup room selection remains unproved.

`global.mask` is a trivial canonical ASCII interchange, not a streaming system:
five LF-terminated lines: `CSTM1`, executable SHA256, map SHA256,
`world_x world_y columns rows`, then exactly columns×rows row-major `0`/`1`
characters. Cells are 8px; origins are world pixels. `read_mask` validates the
version, input hashes, int32 dimensions/edges, bounded size, data length, bits and
canonical serialization. Content hashes live in provenance. Native callers
supply validated cells directly to TileGrid; no runtime asset lifecycle is added.

## Unchanged private source oracle

The existing offline SDK 8.0.425/runtime 8.0.31 and ILSpy 9.1.0.7988 are reused;
no downloads or original game execution. `read_static_tilemap_sources.py`
recovers/validates immutable private loader/MapData reads and their provenance.
The extractor pins full source SHA256s and records unchanged inclusive block
hashes/ranges in `source-manifest.json`:

| Private source | Inclusive lines |
|---|---|
| Collider | 8–22, 205–253, 255–258 |
| Hitbox | 7–98, 180–188 |
| Grid | 8–56, 76–129, 315–346, 418–429, 481–484 |
| LevelData | 76; 113–138 (constructor bounds cases inside a structural shell) |
| MapData | 47; 192–235 (global bounds) |
| LevelLoader | 95–266 (complete map-layer/filler/reservation/extrusion blocks) |
| SolidTiles | 26–48 (Grid construction and char-to-solid conversion) |

The tracked C# contains only synthetic drivers/shims: strict integer Rectangle,
dense checked VirtualMap storage, raw scalar/text input and inert autotiler
LevelBounds collection. Dense segment scans preserve default-zero occupancy;
all valid cells are scanned, not sparse allocation/performance. Neither collision
nor mask-building algorithms are rewritten in C# for the oracle. Binary decoding
and driver field binding are explicit common inputs, not original CIL execution.
Player adds unchanged Grid/Bounds blocks to its accepted source profile; its
other profile guards, gameplay exclusions and 51-field trace remain intact.

## Reproduce

```sh
/usr/bin/cmake -S . -B .audit/native-static-tilemap/host -DCMAKE_BUILD_TYPE=Release
/usr/bin/cmake --build .audit/native-static-tilemap/host -j2
/usr/bin/ctest --test-dir .audit/native-static-tilemap/host --output-on-failure
python3 -B scripts/read_static_tilemap_sources.py
python3 -B scripts/prepare_static_tilemap.py
python3 -B scripts/check_native_oracle.py --domain grid --compile-only
python3 -B scripts/check_native_oracle.py --domain grid --native .audit/native-static-tilemap/host/native_trace_runner
python3 -B scripts/check_static_tilemap.py --native .audit/native-static-tilemap/host/native_trace_runner
python3 -B scripts/check_native_oracle.py --domain player --native .audit/native-static-tilemap/host/native_player_trace_runner --fixtures .audit/native-static-tilemap/prepared/player.fixtures
```

Grid fixtures cover 17 scenarios/41 rows/16 exact fields. Loader verification
covers six synthetic constructions plus the actual map: 573 complete rows,
including all actual cells; actual geometry adds three scenarios/eight rows.
The bounded actual Player walk/jump adds one scenario/20 frames/200 rows/51 fields.
Before equality, both traces must independently satisfy strict grammar and
fixture-derived ordered operation/case/row coverage. Missing, duplicated,
reordered, foreign and identically malformed traces are rejected. No fixed trace
hash/count substitutes for coverage. Comparison uses exact float32 bits and
reports the first divergence. Existing Actor 32/78/16, scheduler 41/303/17,
Input 29/458/21 and synthetic Player 35/860/51 suites remain separate regressions.

Private `.audit/native-static-tilemap` evidence retains first failed and successful
compile gates, red/green logs, the first whole-map divergence, provenance and
exact-commit final checks. Snapshot shared oracle outputs before another run
overwrites them. Release and sanitizer host checks and the existing VitaSDK
`BUILD_TESTING=OFF` static build establish tests/compilation only: **no Vita
execution, performance, hazards, gameplay completion or playable first room**.
