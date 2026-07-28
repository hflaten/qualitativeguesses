create extension if not exists pgcrypto;

create type hypothesis_state as enum (
  'idle',
  'candidate',
  'active',
  'reinforced',
  'confirmed_by_norwegian_source',
  'exiting',
  'exited',
  'expired',
  'contradicted'
);

create type source_class as enum (
  'prediction_market',
  'official_actor',
  'osint',
  'norwegian_confirmation',
  'equinor_or_exchange',
  'market_control'
);

create type equinor_direction as enum (
  'bullish_equinor',
  'bearish_equinor',
  'unclear'
);

create table source_events (
  id uuid primary key default gen_random_uuid(),
  source text not null,
  source_class source_class not null,
  source_event_id text,
  title text not null,
  url text,
  body text,
  payload jsonb not null default '{}'::jsonb,
  source_timestamp timestamptz,
  first_seen_at timestamptz not null default now(),
  idempotency_key text not null unique,
  created_at timestamptz not null default now()
);

create table ingestion_outcomes (
  id uuid primary key default gen_random_uuid(),
  status text not null check (status in ('created', 'duplicate', 'malformed', 'late', 'unsupported')),
  source text not null,
  source_class source_class not null,
  title text not null default '',
  idempotency_key text not null,
  event_id uuid references source_events(id),
  rejection_reason text,
  recorded_at timestamptz not null default now()
);

create table event_clusters (
  id uuid primary key default gen_random_uuid(),
  canonical_event_id uuid references source_events(id),
  cluster_key text not null unique,
  summary text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table event_cluster_members (
  cluster_id uuid not null references event_clusters(id) on delete cascade,
  event_id uuid not null references source_events(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (cluster_id, event_id)
);

create table event_classifications (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references source_events(id) on delete cascade,
  model text not null,
  relevant_to_equinor boolean not null,
  direction equinor_direction not null,
  confidence numeric(5, 4) not null check (confidence >= 0 and confidence <= 1),
  event_type text not null,
  reasoning_summary text not null,
  is_reinforcement boolean not null default false,
  is_contradiction boolean not null default false,
  raw_response jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table hypotheses (
  id uuid primary key default gen_random_uuid(),
  state hypothesis_state not null,
  thesis text not null,
  direction equinor_direction not null,
  confidence numeric(5, 4) not null check (confidence >= 0 and confidence <= 1),
  source_event_ids uuid[] not null default '{}',
  norwegian_confirmation_event_id uuid references source_events(id),
  norwegian_confirmation_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  closed_at timestamptz
);

create unique index one_open_hypothesis
on hypotheses ((true))
where state in ('candidate', 'active', 'reinforced', 'confirmed_by_norwegian_source', 'exiting');

create table paper_orders (
  id uuid primary key default gen_random_uuid(),
  hypothesis_id uuid not null references hypotheses(id),
  side text not null check (side in ('buy', 'sell')),
  instrument text not null default 'EQNR.OL',
  aum_pct numeric(6, 3) not null check (aum_pct > 0 and aum_pct <= 100),
  status text not null check (status in ('pending', 'approved', 'rejected', 'filled', 'cancelled')),
  reason text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table paper_fills (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references paper_orders(id),
  fill_price numeric(18, 6) not null,
  quantity numeric(18, 6) not null,
  fees numeric(18, 6) not null default 0,
  filled_at timestamptz not null default now()
);

create table positions (
  id uuid primary key default gen_random_uuid(),
  hypothesis_id uuid not null references hypotheses(id),
  instrument text not null default 'EQNR.OL',
  quantity numeric(18, 6) not null default 0,
  average_entry_price numeric(18, 6) not null default 0,
  realized_pnl numeric(18, 6) not null default 0,
  unrealized_pnl numeric(18, 6) not null default 0,
  opened_at timestamptz not null default now(),
  closed_at timestamptz,
  updated_at timestamptz not null default now()
);

create table source_health (
  source text primary key,
  source_class source_class not null,
  status text not null check (status in ('unknown', 'online', 'degraded', 'offline')),
  last_event_at timestamptz,
  last_checked_at timestamptz not null default now(),
  last_error text
);

create table audit_log (
  id uuid primary key default gen_random_uuid(),
  hypothesis_id uuid references hypotheses(id),
  event_id uuid references source_events(id),
  action text not null,
  actor text not null default 'system',
  summary text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index source_events_first_seen_at_idx on source_events (first_seen_at desc);
create index source_events_source_idx on source_events (source);
create index ingestion_outcomes_recorded_at_idx on ingestion_outcomes (recorded_at desc);
create index ingestion_outcomes_status_idx on ingestion_outcomes (status);
create index event_classifications_event_id_idx on event_classifications (event_id);
create index hypotheses_state_idx on hypotheses (state);
create index audit_log_created_at_idx on audit_log (created_at desc);
