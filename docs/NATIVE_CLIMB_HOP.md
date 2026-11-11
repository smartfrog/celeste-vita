# Bounded ClimbHop presentation correction

Original `Player.ClimbHop` resets `fastJump` immediately after
`forceMoveXTimer = 0.2f`. Native `Player::climb_hop` emits the corresponding
`PlayerCosmeticPhase::climb_hop` at that point. Presentation clears only its
`fast_jump` flag; the later animation selector observes the reset. Physics,
input, timing, RNG and the neighboring excluded wind/audio effects are unchanged.

The production `FirstRoomSession` legal-input prefix is compared without drawing
against the accepted two-room SOURCE recording through frame 372, including
animation and hair. This corrects the inherited `jumpFast`/`fallFast` selection
at frames 297–309. It does not implement a room transition or prove Room 2.

The older presentation-projection protocol has no ClimbHop event. Its existing
hop fixtures reset an already-false flag: the adapter applies that no-op without
adding protocol rows. A true flag instead throws at an explicit unsupported
projection boundary; a meaningful reset must never be omitted from comparison.
The full-gameplay SOURCE prefix and direct event/natural-hop tests cover the
meaningful reset. Original profiles, recordings and comparators are unchanged.

The separate inherited Dash repeat landing/hair gap is not corrected here.
