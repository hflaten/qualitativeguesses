# Risk Gate

V1 is paper-trading only by default. The risk gate evaluates every order intent
before any order is persisted, filled, or later routed to a broker. The output is
deterministic and includes an audit-log-ready action and payload for every
approval or rejection.

Any future live broker adapter must treat risk approval as a required upstream
contract. No broker-facing order can be created from an intent unless the risk
gate returns an approved decision.

## Allocation Defaults

Paper mode can test the requested 50/50 staged allocation:

- `TRANCHE_ONE_AUM_PCT=50`
- `TRANCHE_TWO_AUM_PCT=50`

Live mode is disabled by default with `LIVE_TRADING_ENABLED=false`. If live mode
is ever introduced, the default max live order size remains much smaller:

- `RISK_LIVE_MAX_ORDER_AUM_PCT=5`

## Live-Mode Preconditions

Live trading is denied unless all live preconditions are true:

- `mode` is `live`.
- `LIVE_TRADING_ENABLED=true`.
- `LIVE_TRADING_ACKNOWLEDGED=true`, representing an explicit manual enablement
  step before deployment.
- `DEPLOYMENT_ENVIRONMENT` matches `RISK_LIVE_ENVIRONMENT_NAME`, which defaults
  to `production`.
- `RISK_KILL_SWITCH_ENABLED=false`.

The defaults are deliberately safe:

- `mode=paper`
- `deployment_environment=development`
- `live_trading_enabled=false`
- `live_trading_acknowledged=false`
- `kill_switch_enabled=false`

This keeps paper trading usable while denying live buys unless the operator has
explicitly configured both environment separation and manual live-mode
acknowledgement.

## Enforced Limits

The gate checks:

- `RISK_MAX_SINGLE_NAME_EXPOSURE_PCT`
- `RISK_MAX_EVENT_EXPOSURE_PCT`
- `RISK_MAX_DAILY_LOSS_PCT`
- `RISK_MAX_OPEN_HYPOTHESES`
- `RISK_KILL_SWITCH_ENABLED`
- forced liquidation state

Buy intents are rejected when a configured limit would be breached. Sell intents
are approved for risk reduction, and forced liquidation sell intents are marked
with `risk_decision_forced_liquidation`.

When the kill switch is enabled, new buy intents are rejected immediately. Sell
intents remain available so the platform can reduce risk or liquidate a paper
position.

## Reinforcement

A reinforcement order is rejected unless it is backed by independent source
confirmation or materially new information. This keeps tranche 2 from being
spent on repeated copies of the same signal.

## Audit Log

Every risk decision exposes:

- `audit_action`, such as `risk_decision_approved` or `risk_decision_rejected`
- status, reason, side, instrument, AUM percentage, source event id, and order
  reason in `audit_payload`
- mode, deployment environment, live enablement, manual acknowledgement, kill
  switch state, and the configured limits that were active during evaluation

Audit rows must be written for approved, rejected, and forced-liquidation
decisions. Rejections are just as important as approvals because they prove that
live-mode defaults, limits, and emergency controls are working.
