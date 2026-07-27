create table analysis_jobs (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references source_events(id) on delete cascade,
  idempotency_key text not null,
  source text not null,
  source_class source_class not null,
  status text not null check (status in ('queued', 'processing', 'completed', 'failed', 'cancelled')),
  attempts integer not null default 0 check (attempts >= 0),
  queued_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  failed_at timestamptz,
  last_error text,
  payload jsonb not null default '{}'::jsonb
);

create unique index analysis_jobs_event_id_idx on analysis_jobs (event_id);
create index analysis_jobs_status_queued_at_idx on analysis_jobs (status, queued_at);

