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

## Reproduce the source proof offline

All handwritten preparation, range metadata, C# service/recording shims, replay,
comparison, whitelist, coverage assertions, and mutation tests are tracked.
Original binaries, original decompiled bodies, generated reference code, art,
and output traces remain private. The following uses only the already installed
SDK 8.0.425/runtime 8.0.31 and pinned ILSpy tool; no installation or downloads:

```sh
proof=".audit/native-player-presentation/$(git rev-parse HEAD)-repro"
/usr/bin/python3 -B scripts/read_player_presentation_sources.py --output "$proof/source"
/usr/bin/python3 -B scripts/prepare_player_presentation_oracle.py --source "$proof/source" --output "$proof/oracle"
/usr/bin/python3 -B scripts/prepare_player_presentation.py --oracle "$proof/oracle" --output "$proof/assets"
/usr/bin/cmake -S . -B "$proof/release" -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=/usr/bin/python3
/usr/bin/cmake --build "$proof/release" -j2
/usr/bin/ctest --test-dir "$proof/release" --output-on-failure
/usr/bin/python3 -B scripts/compare_player_presentation.py --native "$proof/release/native_presentation_trace_runner" --geometry-native "$proof/release/native_presentation_geometry_runner" --oracle "$proof/oracle" --player-dir "$proof/assets" --output "$proof/presentation"
```

Use a fresh output root. The checker requires a clean committed source/config
revision and re-extracts/recompiles the reference from the hash-pinned original
source closure using the current tracked harness. It records recipe, native
binary, source assembly, original inputs, fixture, bank, and page identities.
The source replay receives **only** validated physics/probe `P` records. Native
`R/D/V` records never enter that input file; the C# replay also rejects them.
Actual native `R/D/V` mutations and a long-idle RNG-ordinal mutation must fail
comparison while leaving a freshly executed original reference unchanged.
Empty traces, omitted presentation ticks, phase reordering, undeclared input,
and incomplete independent source-family coverage cannot establish parity.

The separate low-level geometry contract uses twelve fixed caller cases with
both facings, fractional positions, signed squash, body/bangs/tail origins, and
zero/nonzero rotation. Its source driver calls the unchanged original draw and
vertex methods, not native output or a second canvas renderer.

Actual native feedback and independent review remain separate acceptance gates.
Death/respawn animation, sweat/particles/audio, decals, backdrops, faithful spike
art, menus, additional states, and full-game fidelity are excluded. A removed
player may retain its diagnostic pose until manual reset; that is not original
death presentation. Emulator completion is not healthy-host, hardware, or
performance proof.

The actual animated Climb image and complete guest lifecycle were executed at
`d4f512b2a137877bf39aa059336b465fdc0a900f`. A host-proof-only corrective revision
does not become guest-executed by reusing that evidence. Reuse requires an
explicit comparison of runtime source/header bytes, effective application
compile settings, dependency bytes, and every staged asset/page/command byte
against the original d4 package, apart from generated revision metadata.
Fresh corrective-tip ELF/SELF/VPK inspection is static evidence only.
