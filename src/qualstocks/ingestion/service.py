from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Protocol

from qualstocks.domain import SourceClass, SourceEvent
from qualstocks.ingestion.contract import (
    AdapterContractConfig,
    AdapterEventErrorCode,
    RawAdapterEvent,
    normalize_raw_adapter_event,
    validate_raw_adapter_event,
)
from qualstocks.ingestion.idempotency import build_idempotency_key


class StrEnum(str, Enum):
    pass


class SourceEventStatus(StrEnum):
    CREATED = "created"
    DUPLICATE = "duplicate"
    MALFORMED = "malformed"
    LATE = "late"
    UNSUPPORTED = "unsupported"


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
    source_id: str | None = None
    queued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class IngestionResult:
    status: SourceEventStatus
    ingested_event: IngestedEvent | None
    analysis_job: AnalysisJob | None
    rejection_reason: str | None = None

    @property
    def created(self) -> bool:
        return self.status == SourceEventStatus.CREATED

    @property
    def rejected(self) -> bool:
        return self.status in {
            SourceEventStatus.MALFORMED,
            SourceEventStatus.LATE,
            SourceEventStatus.UNSUPPORTED,
        }


@dataclass(frozen=True)
class IngestionOutcome:
    status: SourceEventStatus
    source: str
    source_class: SourceClass
    title: str
    idempotency_key: str
    recorded_at: datetime
    event_id: str | None = None
    rejection_reason: str | None = None


@dataclass(frozen=True)
class IngestionValidationConfig:
    supported_instruments: tuple[str, ...] = ("EQNR.OL",)
    max_source_event_age: timedelta = timedelta(days=7)


class SourceEventRepository(Protocol):
    def persist_source_event(self, event: SourceEvent, idempotency_key: str) -> IngestionResult:
        """Persist a source event and return whether it was new or duplicate."""

    def record_source_seen(self, event: SourceEvent) -> None:
        """Record source health/latency metadata after a successful ingest attempt."""

    def record_ingestion_outcome(self, outcome: IngestionOutcome) -> None:
        """Record created, duplicate, or rejected ingestion attempts for audit."""


class AnalysisQueue(Protocol):
    def enqueue_analysis(self, ingested_event: IngestedEvent) -> AnalysisJob:
        """Enqueue durable AI analysis for a newly persisted event."""


@dataclass
class IngestionService:
    repository: SourceEventRepository
    analysis_queue: AnalysisQueue
    validation_config: IngestionValidationConfig = IngestionValidationConfig()

    async def ingest_raw(self, raw_event: RawAdapterEvent) -> IngestionResult:
        contract_config = AdapterContractConfig(
            supported_instruments=self.validation_config.supported_instruments,
            max_source_event_age=self.validation_config.max_source_event_age,
        )
        validation = validate_raw_adapter_event(raw_event, contract_config)
        if not validation.valid:
            error = validation.errors[0]
            result = IngestionResult(
                status=_status_from_adapter_error(error.code),
                ingested_event=None,
                analysis_job=None,
                rejection_reason=error.reason,
            )
            self.repository.record_ingestion_outcome(
                _raw_outcome(raw_event, result.status, error.reason)
            )
            return result

        normalized = normalize_raw_adapter_event(raw_event, contract_config)
        return await self._ingest_validated(
            normalized.event,
            idempotency_key=normalized.idempotency_key,
        )

    async def ingest(self, event: SourceEvent) -> IngestionResult:
        rejection = _source_event_rejection(event, self.validation_config)
        if rejection is not None:
            status, reason = rejection
            result = IngestionResult(
                status=status,
                ingested_event=None,
                analysis_job=None,
                rejection_reason=reason,
            )
            self.repository.record_ingestion_outcome(
                _event_outcome(
                    event,
                    status,
                    idempotency_key=build_idempotency_key(event),
                    rejection_reason=reason,
                )
            )
            return result

        return await self._ingest_validated(
            event,
            idempotency_key=build_idempotency_key(event),
        )

    async def _ingest_validated(
        self,
        event: SourceEvent,
        *,
        idempotency_key: str,
    ) -> IngestionResult:
        result = self.repository.persist_source_event(event, idempotency_key)
        if result.ingested_event is not None:
            self.repository.record_ingestion_outcome(
                _event_outcome(
                    result.ingested_event.event,
                    result.status,
                    idempotency_key=idempotency_key,
                    rejection_reason=result.rejection_reason,
                )
            )
        self.repository.record_source_seen(event)
        if result.created:
            if result.ingested_event is None:
                raise RuntimeError("created ingestion result is missing ingested_event")
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
    ingestion_outcomes: list[IngestionOutcome] = field(default_factory=list)

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

    def record_ingestion_outcome(self, outcome: IngestionOutcome) -> None:
        self.ingestion_outcomes.append(outcome)


@dataclass
class InMemoryAnalysisQueue:
    jobs: list[AnalysisJob] = field(default_factory=list)

    def enqueue_analysis(self, ingested_event: IngestedEvent) -> AnalysisJob:
        job = AnalysisJob(
            event_id=ingested_event.event.id,
            idempotency_key=ingested_event.idempotency_key,
            source=ingested_event.event.source,
            source_class=ingested_event.event.source_class,
            source_id=ingested_event.event.source_id,
        )
        self.jobs.append(job)
        return job


def _source_latency_seconds(event: SourceEvent) -> float | None:
    if event.source_timestamp is None:
        return None
    return max(0.0, (event.first_seen_at - event.source_timestamp).total_seconds())


def _source_event_rejection(
    event: SourceEvent,
    config: IngestionValidationConfig,
) -> tuple[SourceEventStatus, str] | None:
    if not event.source.strip():
        return SourceEventStatus.MALFORMED, "source is required"
    if not event.title.strip():
        return SourceEventStatus.MALFORMED, "title is required"
    if not isinstance(event.payload, dict):
        return SourceEventStatus.MALFORMED, "payload must be an object"
    if event.instrument and event.instrument not in config.supported_instruments:
        return SourceEventStatus.UNSUPPORTED, "instrument is not supported"
    if event.source_timestamp is not None:
        event_age = event.first_seen_at - event.source_timestamp
        if event_age > config.max_source_event_age:
            return SourceEventStatus.LATE, "source event is too old"
    return None


def _status_from_adapter_error(code: AdapterEventErrorCode) -> SourceEventStatus:
    if code == AdapterEventErrorCode.LATE:
        return SourceEventStatus.LATE
    if code == AdapterEventErrorCode.UNSUPPORTED:
        return SourceEventStatus.UNSUPPORTED
    return SourceEventStatus.MALFORMED


def _event_outcome(
    event: SourceEvent,
    status: SourceEventStatus,
    *,
    idempotency_key: str,
    rejection_reason: str | None = None,
) -> IngestionOutcome:
    return IngestionOutcome(
        status=status,
        source=event.source,
        source_class=event.source_class,
        title=event.title,
        idempotency_key=idempotency_key,
        event_id=event.id,
        rejection_reason=rejection_reason,
        recorded_at=datetime.now(timezone.utc),
    )


def _raw_outcome(
    raw_event: RawAdapterEvent,
    status: SourceEventStatus,
    rejection_reason: str,
) -> IngestionOutcome:
    return IngestionOutcome(
        status=status,
        source=raw_event.source,
        source_class=raw_event.source_class,
        title=_raw_title(raw_event),
        idempotency_key=raw_event.idempotency_key or _raw_event_ref(raw_event),
        event_id=None,
        rejection_reason=rejection_reason,
        recorded_at=datetime.now(timezone.utc),
    )


def _raw_title(raw_event: RawAdapterEvent) -> str:
    for key in ("title", "headline"):
        value = raw_event.payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _raw_event_ref(raw_event: RawAdapterEvent) -> str:
    value = raw_event.provenance.get("raw_event_ref")
    if isinstance(value, str) and value.strip():
        return value.strip()
    title = _raw_title(raw_event)
    if title:
        return f"{raw_event.source}:{title}"
    return f"{raw_event.source}:rejected"
