# Bounded player presentation

This adds one animated body **and simulated hair**, not a full Sprite engine or
new gameplay states. The supported caller is default-inventory Madeline in
Normal (0), Climb (1), and Dash (2), with the existing static collision world.
Debug hitboxes and the older static textured diagnostic remain available.

## Source boundary

The private executable is 2,572,800 bytes, SHA256
`fd73f8a2311fa5737ded550cbad4b75c85b7686b36432f59185e940fcb65fcfe`.
The Forsaken City area uses default inventory; its Backpack flag makes the
original Level caller choose Madeline, whose PlayerSprite constructor selects
the `player` bank. Its default four nodes are valid only for this bounded
profile, not a claim about every player mode or inventory.

The offline reference compiles unchanged extracted Sprite, PlayerSprite,
PlayerHair, selector, callbacks, hair-color, cosmetic-event, metadata, original
mscorlib Random, and relevant FNA math/draw methods. Their full-file and selected
block hashes stay in private source manifests. FNA types compiled into this
reference are source-local types, **not execution of the original FNA binary**.
The original x86 assembly cannot load in the available arm64 .NET runtime.

The diagnostic caller supplies RNG seed 0 explicitly. This is not original
unseeded startup-RNG parity and is not the separate tile-bake seed 553. Original
single-choice Chooser transitions do not consume RNG. Manual diagnostic reset
reinitializes player pose while retaining the scene clock and RNG stream.

Read-only cosmetic hooks preserve scene tick, preamble, Hair.Update,
PlayerSprite.Update, state update/coroutine, movement, selector, hazards,
UpdateHair, and Level hair AfterUpdate ordering. Existing physics observer rows
are unchanged. Positive-freeze ticks, including the zero-crossing tick, do not
advance presentation; input sampling still continues. Entry into Dash completes
the current presentation tick.

## Rendering and assets

The order is BG, hair outlines and reverse-node fills, body, diagnostic spike
markers, FG. Body flooring, trim-adjusted origins, signed squash, facing, and
rotation use source draw parameters. Hair nodes retain fractional positions
except the source's floored root during rendering. Original FNA vertex methods
are part of the private geometry reference; no reference full-canvas renderer is
used.

The measured 188-frame body/hair closure deduplicates into five fixed 128x64 RGBA
pages with one-pixel extrusion. Player uploads total 163,840 bytes; including
the unchanged six legacy room textures, actual submitted bytes are 328,704.
Temporary uploads remain at most 32 KiB. These are submitted-byte bounds, not
physical GPU-allocation or hardware-performance claims. Every used new crop has
only alpha 0/255. Blending remains `GL_ONE, GL_ONE_MINUS_SRC_ALPHA`; this does not
establish a general semitransparent-edge GPU proof.

`prepare_player_presentation.py` consumes the original source-exported frame
bank, independently checks actual atlas metadata and archive members, and emits
only ignored private assets. `--player-dir` on the existing stage/feedback tools
explicitly enables animation and hair and requires textured-room assets.
Deferred Climb capture additionally requires upward motion, an animation index
greater than zero, and an on-screen simulated hair root. The renderer still
exports exactly one closed GL_BACK readback, not an OS screenshot.

## Verification scope

Host traces compare filtered pose, callback, RNG, original draw-parameter, and
vertex records, not whole-file hashes or framebuffer canvases. Shared reference
inputs are ordered read-only physics projections and cosmetic events; native
visual outputs are not reference inputs. Physics/source-oracle checks remain
separate. Required coverage includes reversal, jumps/apex/landing, duck/fastfall,
wall slide, Climb/look-back/dangling, tired/boost, Dash/freeze/tail/refill, and long
idle/RNG, plus the remaining grounded selector branches.

Actual native feedback and independent review remain separate acceptance gates.
Death/respawn animation, sweat/particles/audio, decals, backdrops, faithful spike
art, menus, additional states, and full-game fidelity are excluded. A removed
player may retain its diagnostic pose until manual reset; that is not original
death presentation. Emulator completion is not healthy-host, hardware, or
performance proof.
