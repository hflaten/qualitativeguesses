# Staged Hypothesis Trade Lifecycle

V1 is paper-trading only and allows one open hypothesis at a time. A source
adapter never opens a trade directly; the strategy lifecycle consumes persisted
source events and AI event classifications, then emits paper order intents and
audit actions.

## States

- `candidate`: a watched thesis that is not yet allocated.
- `active`: first qualifying trigger opened the hypothesis and tranche 1 paper
  order intent.
- `reinforced`: a second independent signal supported the thesis and tranche 2
  paper order intent.
- `confirmed_by_norwegian_source`: a Norwegian market-facing source anchored the
  30/40/50 minute exits.
- `exiting`: an exit timer, fallback timer, or contradiction created a paper exit
  intent.
- `exited`: paper position is closed.
- `expired`: a non-allocated candidate aged out.
- `contradicted`: new evidence invalidated the thesis before normal exit.

## Opening And Reinforcement

A first signal can open an `active` hypothesis when it is trigger-tier, relevant
to Equinor, directional, and above the configured confidence floor. The default
paper allocation is 50% AUM for tranche 1.

A second independent trigger or confirmation signal can move the hypothesis to
`reinforced` when it supports the same Equinor direction. The default tranche 2
paper allocation is another 50% AUM.

## Norwegian Confirmation Anchor

The exit anchor is the first market-facing Norwegian confirmation:

- Norwegian press article, represented by `SourceCategory.NORWEGIAN_PRESS`.
- Equinor release or Oslo Bors/Euronext announcement, represented by
  `SourceClass.EQUINOR_OR_EXCHANGE` or `SourceCategory.NORWEGIAN_MARKET`.
- Dedicated Norwegian confirmation adapters, represented by
  `SourceClass.NORWEGIAN_CONFIRMATION`.

When this source arrives, the lifecycle schedules paper exits at 30, 40, and 50
minutes after the confirmation event's `first_seen_at`.

## Fallbacks And Contradictions

If no Norwegian confirmation arrives before the configured fallback window, V1
creates a paper exit intent instead of leaving the position open indefinitely.
The default fallback window is 90 minutes after hypothesis creation.

If a later classification is explicitly contradictory, or confidently points in
the opposite Equinor direction, the hypothesis becomes `contradicted` and an
immediate paper exit intent is emitted.
