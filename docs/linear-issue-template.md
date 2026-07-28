# Linear Issue Template

Use this template when Codex creates or refines Linear issues for the trading
platform. Delete sections that do not apply, but keep risk and verification
explicit.

## Title

`<verb> <specific outcome>`

Examples:

- `Implement Euronext NewsWeb source adapter`
- `Research licensed wire-feed access`
- `Add paper-trading kill switch requirement`

## Type

Choose one:

- Product: user-visible workflow, dashboard behavior, or trading operator need.
- Architecture: boundary, ADR, service shape, database contract, or integration
  decision.
- Implementation: code, migration, adapter, worker, API, UI, or tests.
- Research: dataset, source evaluation, backtest, vendor comparison, or market
  hypothesis validation.
- Operations: Railway, Doppler, Supabase, GitHub, Linear, monitoring, or runbook
  work.

## Context

Explain why this exists and what decision, workflow, or platform capability it
unblocks.

Include links to relevant docs, PRs, previous issues, and source material.

## Scope

In scope:

- `<specific behavior or artifact>`
- `<affected component/path>`

Out of scope:

- `<nearby work intentionally excluded>`
- `<future live-trading behavior, unless this issue is specifically about live-readiness requirements>`

Suggested write scope:

- `src/...`
- `tests/...`
- `docs/...`

## Acceptance Criteria

- `<observable result>`
- `<contract or data shape>`
- `<error/failure behavior>`
- `<dashboard/audit behavior if relevant>`
- `<no prohibited scraping or unsafe live-trading changes>`

## Test Expectations

Required checks:

- `PYTHONPATH=src make test`
- `PYTHONPATH=src make typecheck`
- `make lint`
- `git diff --check`

Focused tests:

- `<specific test module or scenario>`

If a check cannot run locally, the PR and Linear completion comment must include
the exact reason.

## Risk Notes

Paper trading and safety:

- V1 must remain paper-trading-only.
- Live trading must stay disabled unless a future live-readiness ADR and risk
  gate explicitly allow it.
- Any order, fill, risk decision, or hypothesis transition must be auditable.

Data and licensing:

- Do not add scraping of prohibited sources.
- Preserve source provenance, timestamps, language, and licensing notes.
- Do not store secrets or signed request material in logs, issues, or commits.

Operational risks:

- Identify restart/idempotency implications.
- Identify rate limits, fallback behavior, and degraded-service behavior.

## GitHub Branch Hint

`qua-<issue-number>-<short-slug>`

Examples:

- `qua-41-norwegian-confirmation-adapters`
- `qua-42-backtest-dataset-loader`

## Completion Comment Shape

When done, comment on the Linear issue with:

- GitHub PR link.
- What changed.
- Files or modules touched.
- Verification commands and results.
- Known limitations, skipped checks, or follow-up tickets.
