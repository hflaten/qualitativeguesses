from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol

from qualstocks.domain import SourceClass, SourceEvent
from qualstocks.ingestion.idempotency import build_idempotency_key


class StrEnum(str, Enum):
    pass


class SourceEventStatus(StrEnum):
    CREATED = "created"
    DUPLICATE = "duplicate"


@dataclass(frozen=True)
class IngestedEvent:
    event: SourceEvent
    idempotency_key: str
    persisted_at: datetime
    source_latency_seconds: float | None


@dataclass(frozen=True)
class AnalysisJob:
    event_id: str
    idempotency_key: str
    source: str
    source_class: SourceClass
    queued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class IngestionResult:
    status: SourceEventStatus
    ingested_event: IngestedEvent
    analysis_job: AnalysisJob | None

    @property
    def created(self) -> bool:
        return self.status == SourceEventStatus.CREATED


class SourceEventRepository(Protocol):
    def persist_source_event(self, event: SourceEvent, idempotency_key: str) -> IngestionResult:
        """Persist a source event and return whether it was new or duplicate."""

    def record_source_seen(self, event: SourceEvent) -> None:
        """Record source health/latency metadata after a successful ingest attempt."""


class AnalysisQueue(Protocol):
    def enqueue_analysis(self, ingested_event: IngestedEvent) -> AnalysisJob:
        """Enqueue durable AI analysis for a newly persisted event."""


@dataclass
class IngestionService:
    repository: SourceEventRepository
    analysis_queue: AnalysisQueue

    async def ingest(self, event: SourceEvent) -> IngestionResult:
        idempotency_key = build_idempotency_key(event)
        result = self.repository.persist_source_event(event, idempotency_key)
        self.repository.record_source_seen(event)
        if result.created:
            job = self.analysis_queue.enqueue_analysis(result.ingested_event)
            return IngestionResult(
                status=result.status,
                ingested_event=result.ingested_event,
                analysis_job=job,
            )
        return result


@dataclass
class InMemoryEventRepository:
    events_by_key: dict[str, IngestedEvent] = field(default_factory=dict)
    source_seen_at: dict[str, datetime] = field(default_factory=dict)

    def persist_source_event(self, event: SourceEvent, idempotency_key: str) -> IngestionResult:
        existing = self.events_by_key.get(idempotency_key)
        if existing:
            return IngestionResult(
                status=SourceEventStatus.DUPLICATE,
                ingested_event=existing,
                analysis_job=None,
            )

        ingested = IngestedEvent(
            event=event,
            idempotency_key=idempotency_key,
            persisted_at=datetime.now(timezone.utc),
            source_latency_seconds=_source_latency_seconds(event),
        )
        self.events_by_key[idempotency_key] = ingested
        return IngestionResult(
            status=SourceEventStatus.CREATED,
            ingested_event=ingested,
            analysis_job=None,
        )

    def record_source_seen(self, event: SourceEvent) -> None:
        self.source_seen_at[event.source] = datetime.now(timezone.utc)


@dataclass
class InMemoryAnalysisQueue:
    jobs: list[AnalysisJob] = field(default_factory=list)

    def enqueue_analysis(self, ingested_event: IngestedEvent) -> AnalysisJob:
        job = AnalysisJob(
            event_id=ingested_event.event.id,
            idempotency_key=ingested_event.idempotency_key,
            source=ingested_event.event.source,
            source_class=ingested_event.event.source_class,
        )
        self.jobs.append(job)
        return job


def _source_latency_seconds(event: SourceEvent) -> float | None:
    if event.source_timestamp is None:
        return None
    return max(0.0, (event.first_seen_at - event.source_timestamp).total_seconds())
