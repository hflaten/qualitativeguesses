# Broker Adapter Interface

QUA-50 defines the future live-execution boundary without implementing live
trading.

V1 remains paper-only. The only enabled execution implementation is
`PaperExecutionAdapter`.

## Boundary Objects

The execution boundary separates:

- `PaperOrderIntent`: strategy-created order intent.
- `RiskApprovedOrder`: order intent plus approved risk decision.
- `BrokerSubmission`: broker-facing submission attempt.
- `BrokerAcknowledgement`: broker accepts or rejects the submission.
- `BrokerExecutionFill`: broker-reported execution fill.
- `BrokerCancellation`: cancellation request outcome.
- `BrokerReconciliation`: broker-side open orders, position quantity, and cash
  snapshot.

No broker adapter may accept a raw strategy intent. A broker-facing order must be
created from a `RiskApprovedOrder`.

## Live Preconditions

`LiveBrokerAdapter` cannot be constructed unless all live preconditions are true:

- risk mode is `live`
- live trading is enabled
- live trading is manually acknowledged
- deployment environment matches the configured live environment
- kill switch is disabled

Even when those conditions are satisfied, the current live adapter raises
`NotImplementedError` for submit, acknowledge, cancel, and reconcile operations.
That is intentional. A broker must be selected before any live implementation is
written.

## Broker Selection Decision

Before live execution can be implemented, create a new ADR and Linear plan for:

- broker/vendor choice for Equinor on Oslo Bors
- order types, time-in-force, market hours, and currency handling
- account funding and account-level hard cap
- API authentication and key custody
- pre-trade and post-trade reconciliation
- operator kill switch and incident process
- compliance, tax, and reporting constraints

Until that ADR is approved, Railway services must keep:

```bash
PAPER_TRADING_ONLY=true
LIVE_TRADING_ENABLED=false
```
