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

At the initial implementation, ticks 375 and 513 match all 22 commands. All 514
blocks (11,938 commands) are exported: 462 complete blocks match. The remaining
52 sweat commands at ticks 160–182 and 268–296 require unsupported `still`/`climb`
animation frames; native currently appends only its idle sweat frame. Rectangle
and corresponding trim-origin mismatches are retained, and comparison exits
nonzero. No commands are skipped or repaired from the oracle.

This is not full-Level, shader, scissor, vertex, GPU, pixel, or Vita acceptance.
