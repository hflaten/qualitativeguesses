# Production Dry-Run Runbook

This runbook is for the always-on Railway paper-trading deployment. It is a
production runtime for paper trading, not live trading.

## Startup Order

1. Confirm Doppler is synced to the Railway Production environment.
2. Deploy `api-service` from `main`.
3. Open `GET /health` and confirm `ok: true`.
4. Open `GET /api/status` and confirm the dashboard payload returns.
5. Deploy `watcher-service`.
6. Confirm watcher logs show startup validation and at least one configured
   source adapter.
7. Deploy `worker-service`.
8. Confirm worker logs show startup validation and no missing OpenAI/Supabase
   errors.
9. Run the smoke check from Railway or a Doppler-backed shell.

## Required Secret And Config Checks

Required for all deployed paper runtime services:

- `APP_ENV=prod`
- `PAPER_TRADING_ONLY=true`
- `LIVE_TRADING_ENABLED=false`
- `MAX_OPEN_HYPOTHESES=1`
- `SOURCE_PERSISTENCE_BACKEND=postgres`
- `SUPABASE_DB_URL`
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `OPENAI_API_KEY`

At least one watcher source must be enabled:

- `SOURCE_OFFICIAL_US_RSS_ENABLED=true`
- `SOURCE_OFFICIAL_IRAN_RSS_ENABLED=true`
- `SOURCE_NORWEGIAN_CONFIRMATION_RSS_ENABLED=true`
- `SOURCE_LSEG_REUTERS_ENABLED=true` only after a licensed contract allows use
- `SOURCE_AP_MEDIA_API_ENABLED=true` only after a licensed contract allows use

Quote config must be present:

- `QUOTE_SOURCE=yahoo`
- `QUOTE_INSTRUMENT=EQNR.OL`

## Smoke Check

Run locally with Doppler:

```bash
doppler run -- make smoke
```

Run on Railway from the deployed service shell:

```bash
make smoke
```

The smoke check verifies:

- API startup validation.
- Watcher startup validation.
- Worker startup validation.
- Paper worker startup validation.
- API, watcher, AI worker, quote provider, and paper-trading worker component
  readiness.
- Paper-only live gate: `PAPER_TRADING_ONLY=true`,
  `LIVE_TRADING_ENABLED=false`, and `MAX_OPEN_HYPOTHESES=1`.

The command prints JSON and exits non-zero if any check fails.

## Health Endpoints

API:

```text
GET /health
GET /api/status
GET /api/timeline
```

Expected dry-run state:

- `/health` has `ok: true`.
- `/api/status` includes `mode: "paper"`.
- `/api/status.paper_position` is either null or includes live mark-to-market
  P&L fields.
- `/api/status.event_timeline` is ordered newest-first.
- `/api/timeline` returns `system_state`, `paper_position`, and
  `event_timeline`.

## Incident Pause Procedure

Use this when the system is behaving unexpectedly, sources are noisy, or paper
orders are being generated from questionable signals.

1. In Railway shared variables, set all watcher source flags to `false`.
2. Redeploy or restart `watcher-service`.
3. Confirm `/api/status.source_health` stops receiving new events.
4. Leave `api-service` running so the dashboard remains visible.
5. Leave `worker-service` running only if queued jobs are trusted. Otherwise,
   stop the worker service too.
6. Add an incident note in Linear with timestamp, service logs, and the last
   dashboard timeline items.

## Kill-Switch Procedure

V1 is paper trading only, so the hard live-trading gate is:

```bash
PAPER_TRADING_ONLY=true
LIVE_TRADING_ENABLED=false
MAX_OPEN_HYPOTHESES=1
```

If live trading is ever accidentally enabled, `make smoke` and production
startup validation must fail. Immediately:

1. Set `LIVE_TRADING_ENABLED=false` in Railway/Doppler.
2. Confirm `PAPER_TRADING_ONLY=true`.
3. Restart all Railway services.
4. Run `make smoke`.
5. Confirm `/health` returns `ok: true`.
6. Document the incident in Linear before re-enabling watcher sources.

For strategy-level paper order pauses, keep watcher ingestion running but disable
buy-side processing by stopping `worker-service`. The dashboard and source event
timeline remain available through `api-service`.
