# Native static decal command projection

`native_room_transition_trace_runner` retains its 7/8/9-argument update-only
behavior. Appending `--static-decal-commands <descriptor-catalog>` to the complete
9-argument authored catalog form emits one logical CPU command for each live
STATIC authored decal after the existing post-update draw-owner projection.
`--player-commands <mapping>` remains composable in either flag order.

The descriptor catalog is generated privately from the pinned `COMPILE-01`
original atlas metadata and the verified two-room `CDO1` authored owner catalog.
It binds 23 atlas families to all 41 STATIC owners and lists the 11 Banner owners
explicitly. The catalog is never a SOURCE expected-command asset: the original
trace is read only by the comparison test. Outputs live outside Git under the
canonical `.audit/native-static-decal-draw-projection-01` namespace.

Each command carries the verified authored owner identity, room/layer/ordinal,
original texture key, sheet, unchanged atlas source rectangle, authored world
position, center-minus-draw-offset origin (`frame/2 + atlas offset`), signed
scale, white modulation, zero rotation and `None` effects. Negative scale keeps
the source rectangle and origin unchanged. Banner owners are reported as
`static-decal-deferred` with identity and key; they are not projected or counted
as static commands.

Generate the private catalog:

```sh
python3 -B scripts/prepare_static_decal_descriptors.py \
  --atlas <compile-01/atlas.json> \
  --authored-catalog <verified-cdo1-catalog.txt> \
  --output <new-file-under-audit>
```

Run the focused comparison:

```sh
CELESTE_STATIC_DECAL_NATIVE_TRACE=<fresh-native.jsonl> \
python3 -B tests/native/test_static_decal_draw_projection.py
```

The accepted SOURCE oracle contains 11,746 static Decal commands over 514 frames
(22/41/19/19 at ticks 0/374/413/513) and 38,108 Banner commands. The test compares
every static command and counts the deferred Banner commands without claiming
Banner projection. This is logical CPU command identity/order/geometry only; no
GPU, scissor, pixel, Vita or full Level parity is claimed.
