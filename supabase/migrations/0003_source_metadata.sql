alter table source_events
add column source_id text,
add column source_tier text check (source_tier in ('trigger', 'confirmation', 'control')),
add column source_category text,
add column reliability_score numeric(5, 4) check (
  reliability_score is null or (reliability_score >= 0 and reliability_score <= 1)
),
add column relevance_score numeric(5, 4) check (
  relevance_score is null or (relevance_score >= 0 and relevance_score <= 1)
),
add column language text,
add column translation_required boolean not null default false,
add column licensing_class text,
add column raw_event_ref text;

create index source_events_source_id_idx on source_events (source_id);
create index source_events_source_tier_idx on source_events (source_tier);
create index source_events_source_category_idx on source_events (source_category);

alter table source_health
add column source_id text,
add column source_tier text check (source_tier in ('trigger', 'confirmation', 'control')),
add column source_category text,
add column reliability_score numeric(5, 4) check (
  reliability_score is null or (reliability_score >= 0 and reliability_score <= 1)
),
add column expected_latency_seconds integer check (
  expected_latency_seconds is null or expected_latency_seconds >= 0
),
add column licensing_class text,
add column language text,
add column translation_required boolean not null default false;
