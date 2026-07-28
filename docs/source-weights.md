# Source Weights

QUA-47 connects the QUA-15 predictive-power research output to strategy
decisions without hardcoding source names into the lifecycle engine.

## Inputs

`SourceWeightBook.from_rankings(...)` consumes `SourceRanking` rows produced by
`rank_sources(...)`.

Each source weight uses four components:

- speed: how quickly the source appears inside an event case
- uniqueness: how often it is the first source in a case
- directionality: historical positive post-cost hit rate
- outcome: average post-cost directional return

The resulting source weight adjusts AI classification confidence into an
effective confidence used by lifecycle decisions.

## Conservative Defaults

If a source has no historical ranking, the strategy engine does not fail open
with full confidence. It applies a conservative default multiplier:

- trigger source: `0.9`
- confirmation source: `0.8`
- control or unknown source: `0.65`

Source tier still controls eligibility. A confirmation-only source can reinforce
or anchor timers, but it cannot open a new hypothesis by itself.

## Strategy Use

The lifecycle engine uses effective confidence for:

- opening the first hypothesis
- accepting reinforcement signals
- accepting contradiction exits

The decision payload includes both `source_weight` and `effective_confidence`, so
the dashboard/audit layer can show why a signal opened, reinforced, contradicted,
or failed to qualify.
