# Native Player command projection

`native_room_transition_trace_runner` keeps its 7/8/9-argument update-only
behavior. Appending `--player-commands <logical-mapping>` enables one normal
`FirstRoomSession::draw()` after each update. The returned command vector is cached
locally and serialized without another draw, hair flooring, update, or RNG call.
Normal draw-time hair mutations remain visible to subsequent updates.
The opt-in works with no decals, legacy CSD1 first-room decals, or a complete CDO1
authored catalog; catalog validation still precedes any trace output.

Prepare the observer mapping from the frozen native player metadata, independently
pinned original atlas metadata, and the accepted profile's sheet dimensions:

```sh
python3 -B scripts/compare_native_player_draw.py \
  --metadata "$METADATA" --atlas "$ATLAS" --sheets "$SHEETS" \
  --mapping-output "$AUDIT/logical-mapping.txt"
```

`AUDIT` must be the canonical repository's `.audit/native-player-draw-projection-01`
directory. Outputs must not already exist. Original inputs are read in place;
neither the runner nor its mapping producer loads expected Source commands.

For a regenerated Sweat bank, add `--player-provenance "$PLAYER_DIR/provenance.json"`
to mapping and comparison commands. This mode reconstructs the extended bank
from the pinned original body bank, source manifest, XML and atlas, and verifies
every metadata/page payload pin. It does not replace the frozen legacy metadata
pin. Its fresh outputs belong to canonical `.audit/native-sweat-animation-parity-01`.
Set `CELESTE_PLAYER_DRAW_METADATA` and `CELESTE_PLAYER_DRAW_PROVENANCE` alongside
`CELESTE_PLAYER_DRAW_NATIVE_TRACE` to run the focused evidence tests on that bank.

Append the flag and mapping to the existing runner command, saving stdout to a
fresh private trace. Compare it with the immutable Source oracle:

```sh
python3 -B scripts/compare_native_player_draw.py \
  --metadata "$METADATA" --atlas "$ATLAS" --sheets "$SHEETS" \
  --source "$SOURCE_TRACE" --native "$NATIVE_TRACE" --output "$AUDIT/comparison.json"
```

Rows retain native frame/page/clip/trim identity alongside logical sheet/rectangle,
position, trim-normalized origin, signed scale, rotation, color, and Player-local
command order. Component types describe the native draw branch, not observed
Source component object identities. No global command spans are fabricated.
Comparison uses float32 semantics, not decimal-string equality.

The legacy idle-only Sweat bank matches ticks 375 and 513 (22 commands each),
but retains 52 `still`/`climb` rectangle/trim-origin mismatches across all 514
blocks (11,938 commands). The optional complete Sweat bank must match every
command in all 514 blocks; these failures are not waived or filtered. Neither
mode skips commands or repairs them from the oracle.

This is not full-Level, shader, scissor, vertex, GPU, pixel, or Vita acceptance.
