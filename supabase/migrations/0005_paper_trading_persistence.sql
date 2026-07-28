alter table event_classifications
add constraint event_classifications_event_model_key unique (event_id, model);

create table risk_decisions (
  id uuid primary key default gen_random_uuid(),
  hypothesis_id uuid references hypotheses(id),
  event_id uuid references source_events(id),
  order_id uuid references paper_orders(id),
  idempotency_key text not null unique,
  status text not null check (status in ('approved', 'rejected', 'forced_liquidation')),
  reason text not null,
  audit_action text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

alter table paper_orders
drop constraint paper_orders_status_check;

alter table paper_orders
add constraint paper_orders_status_check
check (status in ('pending', 'approved', 'rejected', 'filled', 'partially_filled', 'cancelled'));

alter table paper_orders
add column source_event_id uuid references source_events(id),
add column idempotency_key text unique,
add column reject_reason text;

alter table paper_fills
add column side text check (side in ('buy', 'sell')),
add column instrument text not null default 'EQNR.OL',
add column notional numeric(18, 6) not null default 0,
add column idempotency_key text unique;

alter table positions
add constraint positions_hypothesis_instrument_key unique (hypothesis_id, instrument);

create table paper_valuations (
  id uuid primary key default gen_random_uuid(),
  hypothesis_id uuid references hypotheses(id),
  idempotency_key text unique,
  instrument text,
  quantity numeric(18, 6) not null default 0,
  average_entry_price numeric(18, 6) not null default 0,
  cash numeric(18, 6) not null,
  starting_aum numeric(18, 6) not null,
  equity numeric(18, 6) not null,
  last_price numeric(18, 6),
  market_value numeric(18, 6) not null default 0,
  realized_pnl numeric(18, 6) not null default 0,
  unrealized_pnl numeric(18, 6) not null default 0,
  unrealized_pnl_pct numeric(10, 4) not null default 0,
  total_pnl numeric(18, 6) not null default 0,
  total_pnl_pct numeric(10, 4) not null default 0,
  quote_freshness text not null check (quote_freshness in ('fresh', 'stale', 'missing')),
  quote_source text,
  quote_observed_at timestamptz,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index risk_decisions_created_at_idx on risk_decisions (created_at desc);
create index paper_orders_hypothesis_id_idx on paper_orders (hypothesis_id);
create index paper_fills_order_id_idx on paper_fills (order_id);
create index paper_valuations_created_at_idx on paper_valuations (created_at desc);
