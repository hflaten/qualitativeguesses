# Qualitative Guesses

Event-triggered, paper-trading-first research platform for Equinor news events.

The V1 system listens for US-Iran war, oil shock, shipping risk, sanctions, and official actor signals. It creates at most one active hypothesis at a time, performs AI-assisted qualitative analysis, paper trades Equinor on Oslo Bors, and exits using 30/40/50 minute windows after Norwegian market-facing confirmation.

## Safety

V1 is paper trading only. Live trading must remain disabled unless a future explicitly reviewed risk gate enables it.

## Stack

- Runtime: Railway always-on services
- Database and realtime: Supabase Postgres + Realtime
- Secrets: Doppler synced into Railway
- API and dashboard: Python + FastAPI
- AI analysis: OpenAI model cascade
- Tracking: Linear project `Event-Triggered Trading Platform`

## Services

- `api-service`: FastAPI API, health checks, inbound event endpoint, dashboard shell
- `watcher-service`: source listeners and fallback poll adapters
- `worker-service`: AI analysis, hypothesis state machine, paper trades, exit timers

Railway service setup is documented in `docs/railway-services.md`.

Codex, Linear, and GitHub operating workflow is documented in
`docs/operating-workflow.md`.

Reusable Linear issue template is documented in `docs/linear-issue-template.md`.

Linear and GitHub sync behavior is documented in `docs/linear-github-sync.md`.

Initial platform boundary decisions are captured in
`docs/adr/0001-platform-boundaries.md`.

The first source predictive-power research dataset is documented in
`docs/source-predictive-power-dataset.md`.

Licensed newspaper and wire-feed source research is documented in
`docs/licensed-news-feed-research.md`.

Licensed feed adapter skeletons are documented in
`docs/licensed-feed-adapter-skeletons.md`.

Replayable paper-trading dry runs are documented in
`docs/paper-scenario-runner.md`.

## Local Setup

Install Python 3.12, then:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run with Doppler:

```bash
doppler run -- make api
```

Run tests:

```bash
make test
```

Run the import/type baseline:

```bash
make typecheck
```

## CI

GitHub Actions runs the repository foundation checks on pull requests:

```bash
PYTHONPATH=src make test
PYTHONPATH=src make typecheck
```

## Database

Supabase migrations live in `supabase/migrations`.

The initial schema creates durable tables for:

- source events
- event clusters
- AI classifications
- hypotheses
- paper orders and fills
- paper positions
- analysis jobs
- source health
- audit log

## Required Environment

See `.env.example`.

Required for deployed services:

- `OPENAI_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_DB_URL`

## V1 Constraint

Only one active hypothesis is allowed at a time. New unrelated events are logged while a hypothesis is active, but they cannot open a second position. Reinforcing or contradicting signals update the active hypothesis. After exit, the system resets to idle.
