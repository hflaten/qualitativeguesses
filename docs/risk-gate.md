# Risk Gate

V1 is paper-trading only by default. The risk gate evaluates paper order intents
before any order is persisted or filled. The output is deterministic and includes
an audit-log-ready action and payload for every approval or rejection.

## Allocation Defaults

Paper mode can test the requested 50/50 staged allocation:

- `TRANCHE_ONE_AUM_PCT=50`
- `TRANCHE_TWO_AUM_PCT=50`

Live mode is disabled by default with `LIVE_TRADING_ENABLED=false`. If live mode
is ever introduced, the default max live order size remains much smaller:

- `RISK_LIVE_MAX_ORDER_AUM_PCT=5`

## Enforced Limits

The gate checks:

- `RISK_MAX_SINGLE_NAME_EXPOSURE_PCT`
- `RISK_MAX_EVENT_EXPOSURE_PCT`
- `RISK_MAX_DAILY_LOSS_PCT`
- `RISK_MAX_OPEN_HYPOTHESES`
- forced liquidation state

Buy intents are rejected when a configured limit would be breached. Sell intents
are approved for risk reduction, and forced liquidation sell intents are marked
with `risk_decision_forced_liquidation`.

## Reinforcement

A reinforcement order is rejected unless it is backed by independent source
confirmation or materially new information. This keeps tranche 2 from being
spent on repeated copies of the same signal.

## Audit Log

Every risk decision exposes:

- `audit_action`, such as `risk_decision_approved` or `risk_decision_rejected`
- status, reason, side, instrument, AUM percentage, source event id, and order
  reason in `audit_payload`
