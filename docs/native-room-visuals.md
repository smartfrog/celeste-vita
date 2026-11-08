# Partial native room presentation

This is our native Vita renderer, not the original game runtime. The optional
`CELESTE_ROOM_TEXTURED=ON` presentation draws source PC 1.4 static background tiles,
one `idle00` Player **body** pose, and foreground tiles for the explicitly selected
first room. The body follows movement and facing but does not animate. Without the
optional spike-art intent, red spike hitbox markers remain a **diagnostic overlay,
not faithful spike artwork**.
There is no hair, decals, backdrops, animation, audio, menu, or full-game fidelity
unless the separately bounded animated-player intent is enabled.
Normal, Climb, Dash, jumps, collision, hazards, reset, and input are unchanged.
The default build remains the debug/hitbox renderer.

`CELESTE_ROOM_SPIKE_ART=ON` (requires `CELESTE_ROOM_TEXTURED=ON`) replaces the five
red diagnostic marker rectangles with the **nineteen static source spike image
pieces** for the same five hazards: 17 Up pieces and 2 Left pieces. The two
`danger/spikes/default_up00` and `default_left00` singleton families are decoded
from the pinned atlas, extruded by one pixel into two 16×16 RGBA textures, and
drawn between the Player body and the foreground layer. Source placement and
FNA vertices execute in a narrow offline oracle that runs the unchanged
`Spikes` constructor/`Added` bodies, `Calc.Random.Choose`, bundled mscorlib
`System.Random`, `MTexture`/`Image`, and FNA vertex generation. Up evaluates
`Choose` 19 times with `Next(1) == 0` because each family has exactly one entry.
All nineteen quads are partly visible and partly covered by opaque foreground
tiles. The spike hitboxes, player depth/order, and all hazard physics remain
unchanged. The old six-texture `CSRV1` protocol and debug markers remain
available.

## Private preparation

All original assets, decompilations, source-derived commands, and generated files
stay under ignored `.audit/`. Nothing in the public repository contains game art
or decompiled game implementation bodies.

`scripts/prepare_room_visual_oracle.py` consumes pinned private source extractions
and the existing all-38-room/filler `native-static-tilemap/prepared/driver.json`.
It compiles unchanged loader, VirtualMap, Autotiler, Tileset, Calc selection, bundled
mscorlib Random, and overlay-assignment bodies using the existing private offline
SDK 8.0.425/runtime 8.0.31. Metadata-only texture/grid shims do not choose rules or
variants. The full 541×440 BG bake precedes FG on one seed-553 stream. Every source
character and level bound is compared before collision-mask collapse. The existing
collision mask must remain byte-identical. Method-body identities, calls, full-map
commands, rules, variants, source rectangles, and RNG ordinals are retained privately.

`scripts/prepare_room_visuals.py --oracle <closed-bake> --output <fresh-private-dir>`
validates the complete source RLE stream while retaining only five tileset crops
and the body crop. Room commands are selected only after the full bake. Atlas
signed trim fields and references are checked. Six raw textures use one extruded
pixel border: five 64×128 and one 16×16, totaling **164,864 submitted RGBA bytes**.
This is not an assertion about physical GPU allocation. Upload is one texture at a
time with at most 32,768 temporary CPU pixel bytes; the full atlas is never loaded
on Vita. Pixels remain premultiplied and unchanged; point filtering, clamp, white
modulation, and `ONE / ONE_MINUS_SRC_ALPHA` are explicit. All six selected crops
actually have only alpha 0/255; they cannot prove partial-alpha blending. The
preparation separately records a known partial-alpha atlas pixel for diagnostics.

## Source spike artwork preparation

```sh
python3 -B scripts/read_player_presentation_sources.py --output <fresh-source-closure>
python3 -B scripts/prepare_spike_art_oracle.py --source <fresh-source-closure> \
  --output <fresh-spike-oracle>
python3 -B scripts/prepare_room_visual_oracle.py --output <fresh-bake>
python3 -B scripts/prepare_room_visuals.py --oracle <fresh-bake> --output <fresh-six-texture>
python3 -B scripts/prepare_spike_art.py --visuals <fresh-six-texture> \
  --oracle <fresh-spike-oracle> --output <fresh-eight-texture>
```

The spike oracle uses pinned private ILSpy sources and the existing offline SDK
8.0.425/runtime 8.0.31. It consumes only the prepared selected-room hazards and
the pinned Gameplay atlas metadata. It records both source families as exactly
one entry, the nineteen pieces, the two source crops' SHA-256 values and alpha
sets, and three seed/prefix runs of 19 `Next(1) -> 0` calls. The art proof does not
claim a complete `MapData`/`Level.LoadLevel` RNG trace or level closure.

## Frame feedback

```sh
python3 -B scripts/feedback_native_room.py --textured --spike-art \
  --visual-dir <private-eight-texture-assets> --player-dir <private-player-assets> \
  --after-climb --output .audit/native-room-vita/<fresh-checkpoint>
```

The existing pipeline requires exact clean source before and after staging/build,
verifies the VPK, runs isolated Vita3K OpenGL 1× with surface synchronization enabled,
and takes one guest `glReadPixels(GL_BACK)` export after `glFinish`, before swap.
The PPM and receipt are closed before lossless PNG conversion. There is no OS/window
capture or CPU-rendered reference canvas. Textured intent checks source-color probes
and draw/style/byte receipts rather than the debug palette. Camera is explicitly
(0,0); row 23 is clipped at logical y=180; 960×544 output has two black rows per side.
Frame-only feedback does not claim input, clean guest exit, host health, performance,
or hardware proof. Parent visual review and independent code review remain required.
