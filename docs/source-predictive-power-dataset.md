# Source Predictive-Power Research Dataset

QUA-15 defines the first research dataset for measuring which sources actually lead
Equinor intraday moves during US-Iran, Strait of Hormuz, oil-supply-shock, sanction,
or shipping-risk events.

The dataset anchors returns on `first_seen_at`, because that is the earliest timestamp
the platform could have acted on. It also preserves `source_timestamp` and
`event_timestamp` so research can separate market-moving facts from ingestion latency.

## Event Schema

Required event columns:

- `case_id`: event cluster or historical scenario identifier used for source lead/lag.
- `event_id`: unique source event identifier.
- `source_id`: stable source key such as `truth-social`, `kalshi`, `e24`, or `reuters`.
- `source_name`: human-readable source label.
- `source_class`: source class, such as `official_actor`, `prediction_market`, or
  `norwegian_confirmation`.
- `source_category`: more specific category, such as `official_us`,
  `official_iran`, `norwegian_press`, `wire_or_newspaper`, or `maritime_security`.
- `source_tier`: `trigger`, `confirmation`, or `control`.
- `event_timestamp`: timestamp of the underlying event being reported.
- `source_timestamp`: timestamp published by the source.
- `first_seen_at`: timestamp when our system first received or observed the event.
- `headline`: source headline or compact event text.
- `body`: body text or extracted summary when available.
- `topic_classification`: topic label, such as `us_iran_war` or `hormuz_closure`.
- `equinor_relevance`: numeric Equinor relevance score.
- `oil_impact_channel`: expected oil channel, such as `hormuz_closure`,
  `sanctions`, `shipping_risk`, or `production_disruption`.
- `direction`: expected Equinor direction. Long/bullish directions score positive
  EQNR returns; short/bearish directions invert them.
- `confidence`: source or classifier confidence.

## Market And Control Inputs

EQNR intraday price rows require:

- `timestamp`
- `mid`
- optional `bid`
- optional `ask`

Control rows for Brent and USD/NOK require:

- `timestamp`
- `value`

## Derived Fields

The loader and row builder produce one row per event per response window:

- default windows: 1, 5, 10, 30, 40, and 50 minutes.
- `source_latency_seconds`: `first_seen_at - source_timestamp`.
- `source_lead_lag_seconds`: event lead/lag versus the first observed source in the
  same `case_id`.
- `source_rank_in_case`: first source is rank 1.
- `eqnr_return_pct`: EQNR return from first seen to the response-window price.
- `directional_return_pct`: return aligned to the event direction.
- `post_cost_directional_return_pct`: directional return after default paper cost.
- `brent_change_pct` and `usd_nok_change_pct`: control movement over the same window
  when available.
- `missing_data_reason`: populated instead of failing when a forward price is missing.

## Source Ranking

Initial source ranking combines:

- speed: lower lead/lag wins.
- uniqueness: how often a source is first in a `case_id`.
- directionality: hit rate of positive post-cost directional outcomes.
- paper outcome: average post-cost directional return.
- latency penalty: slower ingestion slightly reduces score.

The ranking is intentionally simple and inspectable. It is a first baseline for deciding
which sources deserve trigger-grade treatment before introducing more complex statistics.
