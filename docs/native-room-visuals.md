# Partial native room presentation

This is our native Vita renderer, not the original game runtime. The optional
`CELESTE_ROOM_TEXTURED=ON` presentation draws source PC 1.4 static background tiles,
one `idle00` Player **body** pose, and foreground tiles for the explicitly selected
first room. The body follows movement and facing but does not animate. Red spike
hitbox markers remain a **diagnostic overlay, not faithful spike artwork**.
There is no hair, decals, backdrops, animation, audio, menu, or full-game fidelity.
Normal, Climb, Dash, jumps, collision, hazards, reset, and input are unchanged.
The default build remains the debug/hitbox renderer.

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

## Frame feedback

```sh
python3 -B scripts/feedback_native_room.py --textured --visual-dir <private-assets> \
  --frame-only --output .audit/native-room-vita/<fresh-checkpoint>
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
