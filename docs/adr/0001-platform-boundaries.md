# ADR 0001: Platform Boundaries

## Status

Accepted for V1 paper trading.

## Context

The platform trades from fast qualitative event analysis. It must stay
auditable, restart-safe, and paper-trading-only while the source universe,
strategy behavior, and execution assumptions are still being researched.

The V1 target is one Equinor Oslo Bors paper position at a time. Source events
may arrive from prediction markets, official actors, Norwegian press,
issuer/exchange announcements, OSINT, and market-control signals. No source
adapter should be able to bypass analysis, risk checks, or audit logging.

## Decision

The system is split into explicit boundaries:

- Event ingestion receives source updates, normalizes them into `SourceEvent`,
  records source health, and enqueues analysis jobs.
- Signal generation classifies source events, scores Equinor relevance,
  direction, confidence, reinforcement, contradiction, and oil-impact channel.
- Strategy lifecycle owns hypothesis state and emits paper order intents. It
  allows one active hypothesis at a time.
- Risk checks evaluate every order intent before any fill is created.
- Execution is paper-only in V1. Paper fills are deterministic and replayable.
- Portfolio state records orders, fills, positions, valuations, realized P&L,
  unrealized P&L, and quote freshness.
- Audit logging records source provenance, model outputs, lifecycle decisions,
  risk decisions, order/fill events, exits, and operator-visible status.
- Dashboard/API reads from persisted state and live quote boundaries. It does
  not mutate trading state.

Paper trading precedes live trading. Live broker execution must not exist until
a future ADR accepts broker choice, live-mode risk gates, kill switch behavior,
operator approval flow, and audit requirements.

## Boundary Rules

### Event Ingestion

Source adapters may connect to WebSocket, webhook, streaming, RSS, polling, or
licensed APIs. They normalize provider payloads and preserve provenance. They
must not create hypotheses, trades, risk decisions, or fills.

Ingestion persists raw/normalized event data with idempotency keys. One failing
adapter must not stop other enabled adapters.

### Signal Generation

AI analysis workers consume queued source events and store classifications.
Model prompts and raw responses are retained for audit. The worker can reject
irrelevant or malformed output, but it cannot open trades directly.

Fast filtering and stronger analysis models may differ. Model choice is runtime
configuration, not hardcoded strategy behavior.

### Strategy Lifecycle

The lifecycle consumes persisted classifications and current hypothesis state.
It decides whether to open, reinforce, contradict, confirm, exit, expire, or
ignore a hypothesis.

The Norwegian confirmation anchor starts the 30/40/50 minute exit windows. A
fallback exit prevents a paper position from staying open indefinitely.

### Risk Checks

The risk gate approves or rejects every paper order intent before persistence or
fill simulation. It enforces configured allocation, exposure, daily loss, open
hypothesis, reinforcement, and forced-liquidation constraints.

Risk output is audit-log-ready. Rejections are first-class records, not just log
messages.

### Execution

V1 execution is deterministic paper trading only. Fill assumptions for spread,
slippage, partial fills, rejections, and closeouts must remain explicit and
testable.

Live trading defaults stay disabled through `LIVE_TRADING_ENABLED=false` and
production startup checks must fail unsafe configurations.

### Portfolio State

Portfolio state is persisted in Supabase Postgres so restarts do not lose paper
orders, fills, positions, valuations, or classification/risk history. Replay must
not duplicate records with stable idempotency keys.

### Audit Logging

Every consequential action must be reconstructable from durable records:
source event, classification, hypothesis transition, risk decision, paper order,
paper fill, valuation, planned exit, actual exit, and operator-visible status.

Audit logs must not contain secrets or full signed requests.

## Consequences

- Source adapter work can proceed independently from strategy and execution.
- The paper-trading loop can be replayed and inspected before live execution is
  considered.
- The dashboard can show system health and paper P&L without gaining write
  authority over trading state.
- Live execution requires a new ADR and cannot emerge accidentally from paper
  trading work.
- Some speed is traded for auditability: every step crosses a persisted boundary
  rather than directly chaining source events into orders.

## Current Deployment Decision

V1 runtime uses:

- Python for API, workers, adapters, paper ledger, and research tooling.
- FastAPI for API and dashboard shell.
- Supabase Postgres for durable operating state.
- Railway for always-on services.
- Doppler for secrets synced into Railway.
- GitHub for source, PRs, CI, and release history.
- Linear for planning, issue tracking, and implementation logs.

## Open Questions

- Broker: Which broker API can support future live Equinor Oslo Bors trading
  with strong order controls, account isolation, and audit access?
- Data vendor: Which licensed low-latency news/wire provider should become the
  first paid trigger or confirmation feed?
- Market data: Which paid quote/intraday data vendor should replace free quote
  sources for production-grade research and paper P&L?
- Runtime: Should long-lived adapters remain simple Railway workers, or should
  high-volume streams move to a dedicated queue/streaming service?
- Queue: Should Supabase-backed jobs remain enough for V1, or should a
  dedicated Redis/queue service be introduced for delayed exits and retries?
- Live readiness: What operator approval, kill switch, daily loss, max order,
  max exposure, and monitoring gates are required before live broker access?
- Deployment: Should paper-trading worker and AI worker remain one service or
  split once strategy execution is wired end to end?
