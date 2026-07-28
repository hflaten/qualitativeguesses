from __future__ import annotations

import json
from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime, timezone
from typing import Protocol

from qualstocks.domain import SourceEvent
from qualstocks.ingestion.service import (
    AnalysisJob,
    IngestedEvent,
    IngestionOutcome,
    IngestionResult,
    SourceEventStatus,
    _source_latency_seconds,
)


class DatabaseClient(Protocol):
    def insert_source_event(self, values: dict[str, object]) -> dict[str, object] | None:
        """Insert a source event and return the inserted row, or None on duplicate."""

    def fetch_source_event_by_key(self, idempotency_key: str) -> dict[str, object] | None:
        """Fetch an existing source event by idempotency key."""

    def upsert_source_health(self, values: dict[str, object]) -> None:
        """Upsert source health metadata."""

    def insert_ingestion_outcome(self, values: dict[str, object]) -> dict[str, object]:
        """Insert an ingestion outcome for dashboard/audit timeline rendering."""

    def insert_analysis_job(self, values: dict[str, object]) -> dict[str, object]:
        """Insert an analysis job and return the inserted row."""

    def insert_event_classification(self, values: dict[str, object]) -> dict[str, object] | None:
        """Insert an event classification and return the row, or None on duplicate."""

    def fetch_event_classification(self, event_id: str, model: str) -> dict[str, object] | None:
        """Fetch an existing event classification by event and model."""

    def insert_risk_decision(self, values: dict[str, object]) -> dict[str, object] | None:
        """Insert a risk decision and return the row, or None on duplicate."""

    def fetch_risk_decision_by_key(self, idempotency_key: str) -> dict[str, object] | None:
        """Fetch an existing risk decision by idempotency key."""

    def insert_paper_order(self, values: dict[str, object]) -> dict[str, object] | None:
        """Insert a paper order and return the row, or None on duplicate."""

    def fetch_paper_order_by_key(self, idempotency_key: str) -> dict[str, object] | None:
        """Fetch an existing paper order by idempotency key."""

    def insert_paper_fill(self, values: dict[str, object]) -> dict[str, object] | None:
        """Insert a paper fill and return the row, or None on duplicate."""

    def fetch_paper_fill_by_key(self, idempotency_key: str) -> dict[str, object] | None:
        """Fetch an existing paper fill by idempotency key."""

    def upsert_position_snapshot(self, values: dict[str, object]) -> dict[str, object]:
        """Upsert a position snapshot and return the row."""

    def insert_valuation_snapshot(self, values: dict[str, object]) -> dict[str, object]:
        """Insert a paper valuation snapshot and return the row."""

    def insert_audit_event(self, values: dict[str, object]) -> dict[str, object] | None:
        """Insert an audit event and return the row, or None on duplicate."""

    def fetch_audit_event_by_key(self, idempotency_key: str) -> dict[str, object] | None:
        """Fetch an audit event by idempotency key."""

    def fetch_dashboard_read_model(self, hypothesis_id: str | None = None) -> dict[str, object]:
        """Fetch latest paper state for dashboard rendering."""

    def claim_queued_analysis_job(
        self,
        values: dict[str, object],
    ) -> dict[str, object] | None:
        """Atomically claim one queued analysis job."""

    def fetch_source_event(self, event_id: str) -> dict[str, object] | None:
        """Fetch a persisted source event by id."""

    def mark_analysis_job_completed(self, values: dict[str, object]) -> None:
        """Mark an analysis job completed."""

    def mark_analysis_job_failed(self, values: dict[str, object]) -> None:
        """Mark an analysis job failed."""


@dataclass(frozen=True)
class PostgresSourceEventRepository:
    client: DatabaseClient

    def persist_source_event(self, event: SourceEvent, idempotency_key: str) -> IngestionResult:
        row = self.client.insert_source_event(_source_event_values(event, idempotency_key))
        status = SourceEventStatus.CREATED
        if row is None:
            row = self.client.fetch_source_event_by_key(idempotency_key)
            status = SourceEventStatus.DUPLICATE
        if row is None:
            raise RuntimeError("source event insert returned no row and duplicate lookup failed")

        ingested_event = event if status == SourceEventStatus.CREATED else replace(
            event,
            id=str(row.get("id") or event.id),
        )
        ingested = IngestedEvent(
            event=ingested_event,
            idempotency_key=idempotency_key,
            persisted_at=_row_datetime(row.get("created_at")),
            source_latency_seconds=_source_latency_seconds(event),
        )
        return IngestionResult(
            status=status,
            ingested_event=ingested,
            analysis_job=None,
        )

    def record_source_seen(self, event: SourceEvent) -> None:
        self.client.upsert_source_health(_source_health_values(event))

    def record_ingestion_outcome(self, outcome: IngestionOutcome) -> None:
        self.client.insert_ingestion_outcome(_ingestion_outcome_values(outcome))


@dataclass(frozen=True)
class PostgresAnalysisQueue:
    client: DatabaseClient

    def enqueue_analysis(self, ingested_event: IngestedEvent) -> AnalysisJob:
        values = {
            "event_id": ingested_event.event.id,
            "idempotency_key": ingested_event.idempotency_key,
            "source": ingested_event.event.source,
            "source_class": ingested_event.event.source_class.value,
            "source_id": ingested_event.event.source_id,
            "status": "queued",
            "payload": json.dumps(
                {
                    "source_tier": (
                        ingested_event.event.source_tier.value
                        if ingested_event.event.source_tier
                        else None
                    ),
                    "source_category": (
                        ingested_event.event.source_category.value
                        if ingested_event.event.source_category
                        else None
                    ),
                    "raw_event_ref": ingested_event.event.raw_event_ref,
                }
            ),
        }
        row = self.client.insert_analysis_job(values)
        return AnalysisJob(
            event_id=ingested_event.event.id,
            idempotency_key=ingested_event.idempotency_key,
            source=ingested_event.event.source,
            source_class=ingested_event.event.source_class,
            source_id=ingested_event.event.source_id,
            queued_at=_row_datetime(row.get("queued_at")),
        )


@dataclass(frozen=True)
class PsycopgDatabaseClient:
    db_url: str

    def insert_source_event(self, values: dict[str, object]) -> dict[str, object] | None:
        return self._fetchone(
            """
            insert into source_events (
              id,
              source,
              source_class,
              source_event_id,
              title,
              url,
              payload,
              source_timestamp,
              first_seen_at,
              idempotency_key,
              source_id,
              source_tier,
              source_category,
              reliability_score,
              relevance_score,
              language,
              translation_required,
              licensing_class,
              raw_event_ref
            )
            values (
              %(id)s,
              %(source)s,
              %(source_class)s,
              %(source_event_id)s,
              %(title)s,
              %(url)s,
              %(payload)s::jsonb,
              %(source_timestamp)s,
              %(first_seen_at)s,
              %(idempotency_key)s,
              %(source_id)s,
              %(source_tier)s,
              %(source_category)s,
              %(reliability_score)s,
              %(relevance_score)s,
              %(language)s,
              %(translation_required)s,
              %(licensing_class)s,
              %(raw_event_ref)s
            )
            on conflict (idempotency_key) do nothing
            returning id, created_at
            """,
            values,
        )

    def fetch_source_event_by_key(self, idempotency_key: str) -> dict[str, object] | None:
        return self._fetchone(
            """
            select id, created_at
            from source_events
            where idempotency_key = %(idempotency_key)s
            """,
            {"idempotency_key": idempotency_key},
        )

    def upsert_source_health(self, values: dict[str, object]) -> None:
        self._execute(
            """
            insert into source_health (
              source,
              source_class,
              status,
              last_event_at,
              last_checked_at,
              last_error,
              source_id,
              source_tier,
              source_category,
              reliability_score,
              expected_latency_seconds,
              licensing_class,
              language,
              translation_required
            )
            values (
              %(source)s,
              %(source_class)s,
              %(status)s,
              %(last_event_at)s,
              %(last_checked_at)s,
              %(last_error)s,
              %(source_id)s,
              %(source_tier)s,
              %(source_category)s,
              %(reliability_score)s,
              %(expected_latency_seconds)s,
              %(licensing_class)s,
              %(language)s,
              %(translation_required)s
            )
            on conflict (source) do update set
              source_class = excluded.source_class,
              status = excluded.status,
              last_event_at = excluded.last_event_at,
              last_checked_at = excluded.last_checked_at,
              last_error = excluded.last_error,
              source_id = excluded.source_id,
              source_tier = excluded.source_tier,
              source_category = excluded.source_category,
              reliability_score = excluded.reliability_score,
              expected_latency_seconds = excluded.expected_latency_seconds,
              licensing_class = excluded.licensing_class,
              language = excluded.language,
              translation_required = excluded.translation_required
            """,
            values,
        )

    def insert_ingestion_outcome(self, values: dict[str, object]) -> dict[str, object]:
        row = self._fetchone(
            """
            insert into ingestion_outcomes (
              status,
              source,
              source_class,
              title,
              idempotency_key,
              event_id,
              rejection_reason,
              recorded_at
            )
            values (
              %(status)s,
              %(source)s,
              %(source_class)s,
              %(title)s,
              %(idempotency_key)s,
              %(event_id)s,
              %(rejection_reason)s,
              %(recorded_at)s
            )
            returning id, recorded_at
            """,
            values,
        )
        if row is None:
            raise RuntimeError("ingestion outcome insert returned no row")
        return row

    def insert_analysis_job(self, values: dict[str, object]) -> dict[str, object]:
        row = self._fetchone(
            """
            insert into analysis_jobs (
              event_id,
              idempotency_key,
              source,
              source_class,
              source_id,
              status,
              payload
            )
            values (
              %(event_id)s,
              %(idempotency_key)s,
              %(source)s,
              %(source_class)s,
              %(source_id)s,
              %(status)s,
              %(payload)s::jsonb
            )
            returning id, queued_at
            """,
            values,
        )
        if row is None:
            raise RuntimeError("analysis job insert returned no row")
        return row

    def insert_event_classification(self, values: dict[str, object]) -> dict[str, object] | None:
        return self._fetchone(
            """
            insert into event_classifications (
              event_id,
              model,
              relevant_to_equinor,
              direction,
              confidence,
              event_type,
              reasoning_summary,
              is_reinforcement,
              is_contradiction,
              raw_response
            )
            values (
              %(event_id)s,
              %(model)s,
              %(relevant_to_equinor)s,
              %(direction)s,
              %(confidence)s,
              %(event_type)s,
              %(reasoning_summary)s,
              %(is_reinforcement)s,
              %(is_contradiction)s,
              %(raw_response)s::jsonb
            )
            on conflict (event_id, model) do nothing
            returning id, created_at
            """,
            values,
        )

    def fetch_event_classification(self, event_id: str, model: str) -> dict[str, object] | None:
        return self._fetchone(
            """
            select id, created_at
            from event_classifications
            where event_id = %(event_id)s and model = %(model)s
            """,
            {"event_id": event_id, "model": model},
        )

    def insert_risk_decision(self, values: dict[str, object]) -> dict[str, object] | None:
        return self._fetchone(
            """
            insert into risk_decisions (
              hypothesis_id,
              event_id,
              order_id,
              idempotency_key,
              status,
              reason,
              audit_action,
              payload
            )
            values (
              %(hypothesis_id)s,
              %(event_id)s,
              %(order_id)s,
              %(idempotency_key)s,
              %(status)s,
              %(reason)s,
              %(audit_action)s,
              %(payload)s::jsonb
            )
            on conflict (idempotency_key) do nothing
            returning id, created_at
            """,
            values,
        )

    def fetch_risk_decision_by_key(self, idempotency_key: str) -> dict[str, object] | None:
        return self._fetchone(
            """
            select id, created_at
            from risk_decisions
            where idempotency_key = %(idempotency_key)s
            """,
            {"idempotency_key": idempotency_key},
        )

    def insert_paper_order(self, values: dict[str, object]) -> dict[str, object] | None:
        return self._fetchone(
            """
            insert into paper_orders (
              id,
              hypothesis_id,
              side,
              instrument,
              aum_pct,
              status,
              reason,
              source_event_id,
              idempotency_key,
              reject_reason,
              created_at,
              updated_at
            )
            values (
              %(id)s,
              %(hypothesis_id)s,
              %(side)s,
              %(instrument)s,
              %(aum_pct)s,
              %(status)s,
              %(reason)s,
              %(source_event_id)s,
              %(idempotency_key)s,
              %(reject_reason)s,
              %(created_at)s,
              %(updated_at)s
            )
            on conflict (idempotency_key) do nothing
            returning id, created_at
            """,
            values,
        )

    def fetch_paper_order_by_key(self, idempotency_key: str) -> dict[str, object] | None:
        return self._fetchone(
            """
            select id, created_at
            from paper_orders
            where idempotency_key = %(idempotency_key)s
            """,
            {"idempotency_key": idempotency_key},
        )

    def insert_paper_fill(self, values: dict[str, object]) -> dict[str, object] | None:
        return self._fetchone(
            """
            insert into paper_fills (
              id,
              order_id,
              side,
              instrument,
              fill_price,
              quantity,
              notional,
              fees,
              idempotency_key,
              filled_at
            )
            values (
              %(id)s,
              %(order_id)s,
              %(side)s,
              %(instrument)s,
              %(fill_price)s,
              %(quantity)s,
              %(notional)s,
              %(fees)s,
              %(idempotency_key)s,
              %(filled_at)s
            )
            on conflict (idempotency_key) do nothing
            returning id, filled_at
            """,
            values,
        )

    def fetch_paper_fill_by_key(self, idempotency_key: str) -> dict[str, object] | None:
        return self._fetchone(
            """
            select id, filled_at
            from paper_fills
            where idempotency_key = %(idempotency_key)s
            """,
            {"idempotency_key": idempotency_key},
        )

    def upsert_position_snapshot(self, values: dict[str, object]) -> dict[str, object]:
        row = self._fetchone(
            """
            insert into positions (
              hypothesis_id,
              instrument,
              quantity,
              average_entry_price,
              realized_pnl,
              unrealized_pnl,
              opened_at,
              closed_at,
              updated_at
            )
            values (
              %(hypothesis_id)s,
              %(instrument)s,
              %(quantity)s,
              %(average_entry_price)s,
              %(realized_pnl)s,
              %(unrealized_pnl)s,
              %(opened_at)s,
              %(closed_at)s,
              %(updated_at)s
            )
            on conflict (hypothesis_id, instrument) do update set
              quantity = excluded.quantity,
              average_entry_price = excluded.average_entry_price,
              realized_pnl = excluded.realized_pnl,
              unrealized_pnl = excluded.unrealized_pnl,
              closed_at = excluded.closed_at,
              updated_at = excluded.updated_at
            returning id, updated_at
            """,
            values,
        )
        if row is None:
            raise RuntimeError("position snapshot upsert returned no row")
        return row

    def insert_valuation_snapshot(self, values: dict[str, object]) -> dict[str, object]:
        row = self._fetchone(
            """
            insert into paper_valuations (
              hypothesis_id,
              idempotency_key,
              instrument,
              quantity,
              average_entry_price,
              cash,
              starting_aum,
              equity,
              last_price,
              market_value,
              realized_pnl,
              unrealized_pnl,
              unrealized_pnl_pct,
              total_pnl,
              total_pnl_pct,
              quote_freshness,
              quote_source,
              quote_observed_at,
              payload
            )
            values (
              %(hypothesis_id)s,
              %(idempotency_key)s,
              %(instrument)s,
              %(quantity)s,
              %(average_entry_price)s,
              %(cash)s,
              %(starting_aum)s,
              %(equity)s,
              %(last_price)s,
              %(market_value)s,
              %(realized_pnl)s,
              %(unrealized_pnl)s,
              %(unrealized_pnl_pct)s,
              %(total_pnl)s,
              %(total_pnl_pct)s,
              %(quote_freshness)s,
              %(quote_source)s,
              %(quote_observed_at)s,
              %(payload)s::jsonb
            )
            on conflict (idempotency_key) do update set
              payload = excluded.payload
            returning id, created_at
            """,
            values,
        )
        if row is None:
            raise RuntimeError("valuation snapshot insert returned no row")
        return row

    def insert_audit_event(self, values: dict[str, object]) -> dict[str, object] | None:
        return self._fetchone(
            """
            insert into audit_log (
              hypothesis_id,
              event_id,
              order_id,
              action,
              actor,
              summary,
              payload,
              idempotency_key,
              created_at
            )
            values (
              %(hypothesis_id)s,
              %(event_id)s,
              %(order_id)s,
              %(action)s,
              %(actor)s,
              %(summary)s,
              %(payload)s::jsonb,
              %(idempotency_key)s,
              %(created_at)s
            )
            on conflict (idempotency_key) do nothing
            returning id, created_at
            """,
            values,
        )

    def fetch_audit_event_by_key(self, idempotency_key: str) -> dict[str, object] | None:
        return self._fetchone(
            """
            select id, created_at
            from audit_log
            where idempotency_key = %(idempotency_key)s
            """,
            {"idempotency_key": idempotency_key},
        )

    def fetch_dashboard_read_model(self, hypothesis_id: str | None = None) -> dict[str, object]:
        return self._fetchone(
            """
            select
              (
                select to_jsonb(h)
                from hypotheses h
                where h.state in (
                  'candidate',
                  'active',
                  'reinforced',
                  'confirmed_by_norwegian_source',
                  'exiting'
                )
                order by h.updated_at desc
                limit 1
              ) as active_hypothesis,
              (
                select to_jsonb(p)
                from positions p
                where (%(hypothesis_id)s::uuid is null or p.hypothesis_id = %(hypothesis_id)s)
                order by p.updated_at desc
                limit 1
              ) as position,
              (
                select to_jsonb(v)
                from paper_valuations v
                where (%(hypothesis_id)s::uuid is null or v.hypothesis_id = %(hypothesis_id)s)
                order by v.created_at desc
                limit 1
              ) as valuation,
              coalesce(
                (
                  select jsonb_agg(to_jsonb(s) order by s.last_checked_at desc)
                  from source_health s
                ),
                '[]'::jsonb
              ) as source_health,
              coalesce(
                (
                  select jsonb_agg(to_jsonb(e) order by e.first_seen_at desc)
                  from (
                    select id, source, source_class, title, url, first_seen_at, source_id
                    from source_events
                    order by first_seen_at desc
                    limit 20
                  ) e
                ),
                '[]'::jsonb
              ) as latest_events,
              coalesce(
                (
                  select jsonb_agg(to_jsonb(o) order by o.recorded_at desc)
                  from (
                    select
                      id,
                      status,
                      source,
                      source_class,
                      title,
                      idempotency_key,
                      event_id,
                      rejection_reason,
                      recorded_at as timestamp
                    from ingestion_outcomes
                    where status = 'duplicate'
                    order by recorded_at desc
                    limit 20
                  ) o
                ),
                '[]'::jsonb
              ) as duplicate_events,
              coalesce(
                (
                  select jsonb_agg(to_jsonb(o) order by o.recorded_at desc)
                  from (
                    select
                      id,
                      status,
                      source,
                      source_class,
                      title,
                      idempotency_key,
                      event_id,
                      rejection_reason,
                      recorded_at as timestamp
                    from ingestion_outcomes
                    where status in ('malformed', 'late', 'unsupported')
                    order by recorded_at desc
                    limit 20
                  ) o
                ),
                '[]'::jsonb
              ) as rejected_events,
              (
                select jsonb_build_object(
                  'queued', count(*) filter (where status = 'queued'),
                  'running', count(*) filter (where status = 'running'),
                  'failed', count(*) filter (where status = 'failed')
                )
                from analysis_jobs
              ) as queue_status,
              coalesce(
                (
                  select jsonb_agg(to_jsonb(r) order by r.created_at desc)
                  from (
                    select id, status, reason, audit_action, hypothesis_id, event_id, created_at
                    from risk_decisions
                    where (
                      %(hypothesis_id)s::uuid is null
                      or hypothesis_id = %(hypothesis_id)s
                    )
                    order by created_at desc
                    limit 20
                  ) r
                ),
                '[]'::jsonb
              ) as risk_decisions,
              coalesce(
                (
                  select jsonb_agg(to_jsonb(a) order by a.created_at desc)
                  from (
                    select
                      id,
                      action,
                      summary,
                      actor,
                      hypothesis_id,
                      event_id,
                      order_id,
                      payload,
                      created_at
                    from audit_log
                    where (
                      %(hypothesis_id)s::uuid is null
                      or hypothesis_id = %(hypothesis_id)s
                    )
                    order by created_at desc
                    limit 30
                  ) a
                ),
                '[]'::jsonb
              ) as audit_timeline
            """,
            {"hypothesis_id": hypothesis_id},
        ) or {
            "active_hypothesis": None,
            "position": None,
            "valuation": None,
            "source_health": [],
            "latest_events": [],
            "duplicate_events": [],
            "rejected_events": [],
            "queue_status": None,
            "risk_decisions": [],
            "audit_timeline": [],
        }

    def claim_queued_analysis_job(
        self,
        values: dict[str, object],
    ) -> dict[str, object] | None:
        return self._fetchone(
            """
            update analysis_jobs
            set
              status = 'processing',
              attempts = attempts + 1,
              started_at = %(now)s,
              last_error = null
            where id = (
              select id
              from analysis_jobs
              where status = 'queued'
              order by queued_at
              for update skip locked
              limit 1
            )
            returning
              id,
              event_id,
              idempotency_key,
              source,
              source_class,
              source_id,
              payload,
              attempts
            """,
            values,
        )

    def fetch_source_event(self, event_id: str) -> dict[str, object] | None:
        return self._fetchone(
            """
            select *
            from source_events
            where id = %(event_id)s
            """,
            {"event_id": event_id},
        )

    def mark_analysis_job_completed(self, values: dict[str, object]) -> None:
        self._execute(
            """
            update analysis_jobs
            set
              status = 'completed',
              completed_at = %(now)s,
              failed_at = null,
              last_error = null,
              payload = payload || %(payload)s::jsonb
            where id = %(job_id)s
            """,
            values,
        )

    def mark_analysis_job_failed(self, values: dict[str, object]) -> None:
        self._execute(
            """
            update analysis_jobs
            set
              status = 'failed',
              failed_at = %(now)s,
              last_error = %(error)s
            where id = %(job_id)s
            """,
            values,
        )

    def _fetchone(self, query: str, values: dict[str, object]) -> dict[str, object] | None:
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(self.db_url) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(query, values)
                row = cursor.fetchone()
            connection.commit()
        return dict(row) if row is not None else None

    def _execute(self, query: str, values: dict[str, object]) -> None:
        import psycopg

        with psycopg.connect(self.db_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, values)
            connection.commit()


def _source_event_values(event: SourceEvent, idempotency_key: str) -> dict[str, object]:
    return {
        "id": event.id,
        "source": event.source,
        "source_class": event.source_class.value,
        "source_event_id": event.raw_event_ref,
        "title": event.title,
        "url": event.url,
        "payload": json.dumps(event.payload),
        "source_timestamp": event.source_timestamp,
        "first_seen_at": event.first_seen_at,
        "idempotency_key": idempotency_key,
        "source_id": event.source_id,
        "source_tier": event.source_tier.value if event.source_tier else None,
        "source_category": event.source_category.value if event.source_category else None,
        "reliability_score": event.reliability_score,
        "relevance_score": event.relevance_score,
        "language": event.language,
        "translation_required": event.translation_required,
        "licensing_class": event.licensing_class.value if event.licensing_class else None,
        "raw_event_ref": event.raw_event_ref,
    }


def _source_health_values(event: SourceEvent) -> dict[str, object]:
    return {
        "source": event.source,
        "source_class": event.source_class.value,
        "status": "online",
        "last_event_at": event.first_seen_at,
        "last_checked_at": datetime.now(timezone.utc),
        "last_error": None,
        "source_id": event.source_id,
        "source_tier": event.source_tier.value if event.source_tier else None,
        "source_category": event.source_category.value if event.source_category else None,
        "reliability_score": event.reliability_score,
        "expected_latency_seconds": None,
        "licensing_class": event.licensing_class.value if event.licensing_class else None,
        "language": event.language,
        "translation_required": event.translation_required,
    }


def _ingestion_outcome_values(outcome: IngestionOutcome) -> dict[str, object]:
    return {
        "status": outcome.status.value,
        "source": outcome.source,
        "source_class": outcome.source_class.value,
        "title": outcome.title,
        "idempotency_key": outcome.idempotency_key,
        "event_id": outcome.event_id,
        "rejection_reason": outcome.rejection_reason,
        "recorded_at": outcome.recorded_at,
    }


def _row_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.now(timezone.utc)
