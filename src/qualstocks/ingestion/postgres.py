from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from qualstocks.domain import SourceEvent
from qualstocks.ingestion.service import (
    AnalysisJob,
    IngestedEvent,
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

    def insert_analysis_job(self, values: dict[str, object]) -> dict[str, object]:
        """Insert an analysis job and return the inserted row."""


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

        ingested = IngestedEvent(
            event=event,
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


def _row_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.now(timezone.utc)
