# Initial Schema Review Notes

## Scope

Reviewed `supabase/migrations/0001_initial_schema.sql` against V1 requirements:

- source event dedupe
- one active hypothesis
- paper order and fill linkage
- source health
- audit log coverage

## Findings

No blocking schema issue was found for the foundation PR.

The migration covers the required V1 durable records:

- `source_events` persists raw events before AI analysis and has a unique
  `idempotency_key` for dedupe.
- `ingestion_outcomes` records created, duplicate, malformed, late, and
  unsupported ingestion attempts for dashboard/audit timeline visibility.
- `event_clusters` and `event_cluster_members` support later clustering without
  changing the raw event table.
- `event_classifications` stores model, confidence, direction, reinforcement,
  contradiction, and raw response data.
- `hypotheses` stores the one-hypothesis lifecycle, Norwegian confirmation
  anchor, linked source events, and closure timestamps.
- `one_open_hypothesis` prevents more than one active candidate or open
  hypothesis state at a time.
- `paper_orders`, `paper_fills`, and `positions` provide enough paper-trading
  linkage for staged entries and exits.
- `source_health` can power source status in the operator dashboard.
- `audit_log` can record events, AI decisions, risk decisions, paper orders,
  exits, and state transitions.

## Follow-up recommendations

These should be later tickets unless Supabase migration testing reveals a
problem:

- Add `updated_at` triggers for mutable tables instead of relying on
  application code.
- Consider replacing `hypotheses.source_event_ids` with a join table if the
  source-event relationship becomes query-heavy.
- Add a dedicated service heartbeat table if watcher and worker health should
  be tracked independently from source health.
- Add row-level security policies before exposing Supabase Realtime directly to
  browser clients.
- Add migration smoke tests once the Supabase CLI is part of the local toolchain.

## Decision

Keep the initial schema as-is for QUA-7. It is adequate for the first foundation
merge and should not block source adapter or dashboard contract work.
