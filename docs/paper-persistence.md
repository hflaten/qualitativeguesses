# Paper Trading Persistence

QUA-38 persists the operating loop records that must survive worker restarts and
feed the dashboard read model.

## Durable Records

- `event_classifications`: one AI classification per event/model pair.
- `risk_decisions`: approved/rejected/forced-liquidation risk gate outcomes.
- `paper_orders`: deterministic paper order intents with replay idempotency.
- `paper_fills`: deterministic fills with notional, fees, and replay keys.
- `positions`: latest position snapshot per hypothesis/instrument.
- `paper_valuations`: valuation snapshots for live paper P&L display.

## Dashboard Boundary

`PaperTradingRepository.dashboard_read_model()` returns the latest persisted
position and valuation rows. QUA-39 can use this as the server-side read model
for `/api/status`, then combine it with source health and active hypothesis
state.

## Idempotency

Classifications dedupe by `(event_id, model)`. Risk decisions, orders, fills,
and valuation snapshots use caller-provided idempotency keys so replayed jobs do
not create duplicate dashboard/audit state.
