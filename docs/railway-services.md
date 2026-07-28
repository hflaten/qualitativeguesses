# Railway Services

## Purpose

Railway runs the always-on compute for the V1 paper-trading platform. Supabase
stores durable data, Doppler syncs secrets into Railway, and GitHub stores the
source code.

## Project shape

Create three Railway services from the same GitHub repository:

- `api-service`
- `watcher-service`
- `worker-service`

The checked-in service template is `railway/service-templates.json`, with usage
notes in `docs/railway-service-templates.md`.

All services should use the same branch while the foundation is being reviewed.
After merge, production services should track `main`.

## Shared variables

Doppler should sync project secrets into Railway shared variables. Attach the
shared variables to every service.

Required variables:

- `OPENAI_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_DB_URL`
- `PAPER_TRADING_ONLY=true`
- `MAX_OPEN_HYPOTHESES=1`

Recommended variables:

- `APP_ENV=prod`
- `APP_NAME=qualitativeguesses`
- `SOURCE_PERSISTENCE_BACKEND=postgres`
- `SOURCE_OFFICIAL_US_RSS_ENABLED=true`
- `SOURCE_OFFICIAL_IRAN_RSS_ENABLED=true`
- `SOURCE_NORWEGIAN_CONFIRMATION_RSS_ENABLED=true`
- `OPENAI_FILTER_MODEL=gpt-5-nano`
- `OPENAI_ANALYSIS_MODEL=gpt-5-mini`
- `OPENAI_ESCALATION_MODEL=gpt-5.1`
- `OPENAI_EMBEDDING_MODEL=text-embedding-3-small`
- `TRANCHE_ONE_AUM_PCT=50`
- `TRANCHE_TWO_AUM_PCT=50`
- `EXIT_WINDOWS_MINUTES=30,40,50`

Do not expose `SUPABASE_SERVICE_ROLE_KEY` to browser code. It is for backend
services only.

## Service commands

Use these Railway start commands:

```bash
# api-service
uvicorn qualstocks.main:app --host 0.0.0.0 --port $PORT
```

```bash
# watcher-service
python -m qualstocks.watcher
```

```bash
# worker-service
python -m qualstocks.worker
```

## Deployment order

1. Create `api-service` first and confirm `/health` returns `ok: true`.
2. Create `watcher-service` and confirm logs show it started.
3. Create `worker-service` and confirm logs show it started.
4. Verify all services have the Doppler-synced shared variables attached.
5. Keep paper trading enabled and live trading unavailable.

## Health checks

The API exposes:

```text
GET /health
GET /api/status
```

V1 watcher and worker services log startup status. Later issues should add
database-backed service heartbeat records in `source_health` or a dedicated
service health table.

Each service logs a startup validation payload. In `APP_ENV=prod` or
`APP_ENV=production`, startup fails when:

- `PAPER_TRADING_ONLY` is missing or not `true`.
- `LIVE_TRADING_ENABLED=true`.
- `MAX_OPEN_HYPOTHESES` is missing or not `1`.
- A service-specific secret is missing.

Service-specific requirements:

- `api-service`: `SUPABASE_DB_URL` when `SOURCE_PERSISTENCE_BACKEND=postgres`.
- `watcher-service`: `SUPABASE_DB_URL` when `SOURCE_PERSISTENCE_BACKEND=postgres`.
- `worker-service`: `SOURCE_PERSISTENCE_BACKEND=postgres`, `SUPABASE_DB_URL`,
  and `OPENAI_API_KEY`.
- `paper-trading-worker`: `SOURCE_PERSISTENCE_BACKEND=postgres` and
  `SUPABASE_DB_URL` before a dedicated paper worker service is enabled.

The API `/health` response includes component status for API, watcher, AI worker,
quote provider, and paper-trading worker. In local/dev environments, missing
runtime wiring is reported as warnings or degraded component status so the app
can still be opened while secrets are being configured.

Run the deployment smoke check after every production paper-runtime deployment:

```bash
make smoke
```

The full dry-run process, expected endpoint checks, and pause/kill-switch
procedure are documented in `docs/production-dry-run-runbook.md`.

## Notes

Railway's default environment may be named `Production` even while we are still
building paper-trading infrastructure. Treat the deployed system as production
runtime for paper trading only, not live trading.
