# Native room static decals

Bounded native rendering of the 22 source-proven static `DecalImage` instances in the
selected first room. The 7 time-driven `Banner` decals are explicitly omitted.

## Source gate

`scripts/prepare_decals_oracle.py` composes a narrow oracle from the pinned decompiled
`Celeste.Decal`, `Monocle.MTexture`, `Monocle.Atlas`, `Monocle.Calc`, bundled
`System.Random`, and FNA `SpriteBatch` vertex generation. It executes the unchanged
`Decal` constructor, `Added`, `Update`, `Render`, and nested `DecalImage.Render` against
the verified `raw-room.json` and `Gameplay.meta`.

The oracle records:

- 22 static `DecalImage` draws: 20 `bgdecals` (depth 9000) and 2 `fgdecals` (depth -10500)
- 15 unique static texture families, each a single atlas frame
- zero shared-RNG calls across the static constructor/Added/Update/Render path
- 7 `Banner` components, each consuming exactly one `sineTimer` field-initializer call,
  explicitly rejected from the static profile; no banner phase is claimed

Every draw records the source atlas clip, frame, `DrawOffset`, `Center-DrawOffset`
origin, signed scale, FNA vertex positions, and FNA texture coordinates.

## Assets

`scripts/prepare_decals.py` re-decodes the 15 pinned source crops with the existing
bounded RLEA reader, verifies their SHA-256 identity and alpha totals, and packs them
into one private 64x128 RGBA page with one-pixel edge extrusion. The packer checks
actual bounds, overlap, and total occupancy rather than assuming a fit.

`decals.txt` is the optional `CSD1` protocol: one page, 15 crop records, 22 ordered
draw instances, and 7 explicit Banner omission rows. Existing six/eight-texture room
assets and player assets remain byte-identical.

## Render order

`BG tiles -> 20 static BG decals -> hair/body -> 19 source spikes -> FG tiles -> 2 static FG decals`

`scripts/compare_decal_draws.py` parses the actual serialized `CSD1` records and verifies
that their positions, signed scales, depth, frame, draw offset, origin, crop bytes, render
order, and 7 Banner omissions match the executed source draws. File hashes alone are not
treated as semantic proof, so a refreshed-checksum protocol mutation still fails.
Malformed crop coordinates are rejected with widened arithmetic before any `u+width`
or `v+height` evaluation.

## Build

```sh
python3 scripts/prepare_decals_oracle.py --discovery <pinned il> --pins <pinned framework sources> \
  --raw-room <verified raw-room.json> --corrections <corrected source contract> --output <fresh-private-dir>
python3 scripts/prepare_decals.py --oracle <oracle> --raw-room <raw-room.json> \
  --visuals <prepared visuals> --hazards <hazards.json> --output <fresh-private-dir>
python3 scripts/stage_native_room.py --visual-dir <visuals> --player-dir <player> \
  --decal-dir <decals> --output <fresh-private-staging>
cmake -DCELESTE_VITA=ON -DCELESTE_ROOM_TEXTURED=ON -DCELESTE_ROOM_SPIKE_ART=ON \
  -DCELESTE_ROOM_ANIMATED_PLAYER=ON -DCELESTE_ROOM_DECALS=ON ...
```

The decal page is 32768 submitted RGBA bytes and is uploaded through the existing
bounded NEAREST/CLAMP path. That is a submitted byte count, not a claimed physical GPU
allocation. No parallax, mirror, smoke, scared-animal, or banner animation behavior is
implemented.
