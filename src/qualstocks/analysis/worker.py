from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Mapping, Protocol

from qualstocks.domain import (
    Direction,
    EventClassification,
    LicensingClass,
    SourceCategory,
    SourceClass,
    SourceEvent,
    SourceTier,
)
from qualstocks.ingestion import PaperTradingRepository, PersistenceResult


class StrEnum(str, Enum):
    pass


class AnalysisJobStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    NO_JOB = "no_job"


class MalformedModelOutput(ValueError):
    pass


@dataclass(frozen=True)
class AnalysisJobClaim:
    id: str
    event_id: str
    idempotency_key: str
    source: str
    source_class: str
    source_id: str | None = None
    payload: dict[str, object] = field(default_factory=dict)
    attempts: int = 0


@dataclass(frozen=True)
class AnalysisJobResult:
    status: AnalysisJobStatus
    job: AnalysisJobClaim | None = None
    classification: EventClassification | None = None
    persistence_result: PersistenceResult | None = None
    error: str | None = None
    raw_response: dict[str, object] | None = None


class ClassificationModelClient(Protocol):
    def classify(self, prompt: dict[str, object], *, model: str) -> dict[str, object]:
        """Return structured model output for the supplied prompt payload."""


class AnalysisQueueRepository(Protocol):
    def claim_queued_analysis_job(self, *, now: datetime | None = None) -> AnalysisJobClaim | None:
        """Claim one queued analysis job safely."""

    def fetch_source_event(self, event_id: str) -> SourceEvent:
        """Load the source event for a claimed job."""

    def mark_analysis_job_completed(
        self,
        job_id: str,
        *,
        classification: EventClassification,
        raw_response: dict[str, object],
        now: datetime | None = None,
    ) -> None:
        """Mark a claimed job completed."""

    def mark_analysis_job_failed(
        self,
        job_id: str,
        *,
        error: str,
        now: datetime | None = None,
    ) -> None:
        """Mark a claimed job failed."""


class AnalysisWorkerDatabaseClient(Protocol):
    def claim_queued_analysis_job(
        self,
        values: dict[str, object],
    ) -> dict[str, object] | None:
        """Claim one queued job row."""

    def fetch_source_event(self, event_id: str) -> dict[str, object] | None:
        """Fetch one source event row."""

    def mark_analysis_job_completed(self, values: dict[str, object]) -> None:
        """Mark a job row completed."""

    def mark_analysis_job_failed(self, values: dict[str, object]) -> None:
        """Mark a job row failed."""


@dataclass(frozen=True)
class DatabaseAnalysisQueueRepository:
    client: AnalysisWorkerDatabaseClient

    def claim_queued_analysis_job(self, *, now: datetime | None = None) -> AnalysisJobClaim | None:
        row = self.client.claim_queued_analysis_job({"now": now or datetime.now(timezone.utc)})
        if row is None:
            return None
        return AnalysisJobClaim(
            id=str(row["id"]),
            event_id=str(row["event_id"]),
            idempotency_key=str(row["idempotency_key"]),
            source=str(row["source"]),
            source_class=str(row["source_class"]),
            source_id=str(row["source_id"]) if row.get("source_id") else None,
            payload=_json_dict(row.get("payload")),
            attempts=int(row.get("attempts") or 0),
        )

    def fetch_source_event(self, event_id: str) -> SourceEvent:
        row = self.client.fetch_source_event(event_id)
        if row is None:
            raise KeyError(f"unknown source event: {event_id}")
        return SourceEvent(
            source=str(row["source"]),
            source_class=SourceClass(str(row["source_class"])),
            title=str(row["title"]),
            url=str(row.get("url") or ""),
            payload=_json_dict(row.get("payload")),
            source_id=str(row["source_id"]) if row.get("source_id") else None,
            source_tier=_optional_enum(SourceTier, row.get("source_tier")),
            source_category=_optional_enum(SourceCategory, row.get("source_category")),
            reliability_score=_float_or_none(row.get("reliability_score")),
            relevance_score=_float_or_none(row.get("relevance_score")),
            language=str(row["language"]) if row.get("language") else None,
            translation_required=bool(row.get("translation_required") or False),
            licensing_class=_optional_enum(LicensingClass, row.get("licensing_class")),
            raw_event_ref=str(row["raw_event_ref"]) if row.get("raw_event_ref") else None,
            source_timestamp=row.get("source_timestamp"),
            first_seen_at=row.get("first_seen_at") or datetime.now(timezone.utc),
            id=str(row["id"]),
        )

    def mark_analysis_job_completed(
        self,
        job_id: str,
        *,
        classification: EventClassification,
        raw_response: dict[str, object],
        now: datetime | None = None,
    ) -> None:
        self.client.mark_analysis_job_completed(
            {
                "job_id": job_id,
                "now": now or datetime.now(timezone.utc),
                "payload": json.dumps(
                    {
                        "classification": {
                            "event_id": classification.event_id,
                            "relevant_to_equinor": classification.relevant_to_equinor,
                            "direction": classification.direction.value,
                            "confidence": classification.confidence,
                            "event_type": classification.event_type,
                            "reasoning_summary": classification.reasoning_summary,
                            "is_reinforcement": classification.is_reinforcement,
                            "is_contradiction": classification.is_contradiction,
                        },
                        "raw_response": raw_response,
                    },
                    default=str,
                    sort_keys=True,
                ),
            }
        )

    def mark_analysis_job_failed(
        self,
        job_id: str,
        *,
        error: str,
        now: datetime | None = None,
    ) -> None:
        self.client.mark_analysis_job_failed(
            {
                "job_id": job_id,
                "now": now or datetime.now(timezone.utc),
                "error": error,
            }
        )


@dataclass(frozen=True)
class EventAnalysisWorker:
    queue: AnalysisQueueRepository
    classification_repository: PaperTradingRepository
    filter_model_client: ClassificationModelClient
    analysis_model_client: ClassificationModelClient
    filter_model: str = "gpt-5-nano"
    analysis_model: str = "gpt-5-mini"

    def run_once(self, *, now: datetime | None = None) -> AnalysisJobResult:
        timestamp = now or datetime.now(timezone.utc)
        job = self.queue.claim_queued_analysis_job(now=timestamp)
        if job is None:
            return AnalysisJobResult(status=AnalysisJobStatus.NO_JOB)

        try:
            event = self.queue.fetch_source_event(job.event_id)
            filter_response = self.filter_model_client.classify(
                _filter_prompt(event, job),
                model=self.filter_model,
            )
            if not _bool(filter_response.get("relevant_to_equinor")):
                raw_response = {
                    "filter_model": self.filter_model,
                    "analysis_model": None,
                    "filter_response": filter_response,
                    "analysis_response": None,
                }
                classification = EventClassification(
                    event_id=event.id,
                    relevant_to_equinor=False,
                    direction=Direction.UNCLEAR,
                    confidence=_confidence(filter_response.get("confidence"), default=0),
                    event_type=str(filter_response.get("event_type") or "not_relevant"),
                    reasoning_summary=str(
                        filter_response.get("reasoning_summary")
                        or "Fast relevance filter found no Equinor trade relevance."
                    ),
                )
            else:
                analysis_response = self.analysis_model_client.classify(
                    _analysis_prompt(event, job, filter_response),
                    model=self.analysis_model,
                )
                raw_response = {
                    "filter_model": self.filter_model,
                    "analysis_model": self.analysis_model,
                    "filter_response": filter_response,
                    "analysis_response": analysis_response,
                }
                classification = classify_from_payload(event.id, analysis_response)

            persistence_result = self.classification_repository.persist_event_classification(
                classification,
                model=(
                    self.analysis_model
                    if classification.relevant_to_equinor
                    else self.filter_model
                ),
                raw_response=raw_response,
            )
            self.queue.mark_analysis_job_completed(
                job.id,
                classification=classification,
                raw_response=raw_response,
                now=timestamp,
            )
            return AnalysisJobResult(
                status=AnalysisJobStatus.COMPLETED,
                job=job,
                classification=classification,
                persistence_result=persistence_result,
                raw_response=raw_response,
            )
        except Exception as exc:
            error = str(exc)
            self.queue.mark_analysis_job_failed(job.id, error=error, now=timestamp)
            return AnalysisJobResult(
                status=AnalysisJobStatus.FAILED,
                job=job,
                error=error,
            )


@dataclass(frozen=True)
class OpenAIJsonClassificationClient:
    api_key: str

    def classify(self, prompt: dict[str, object], *, model: str) -> dict[str, object]:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key)
        response = client.responses.create(
            model=model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Return only JSON with fields relevant_to_equinor, direction, "
                        "confidence, event_type, reasoning_summary, is_reinforcement, "
                        "and is_contradiction."
                    ),
                },
                {"role": "user", "content": str(prompt)},
            ],
        )
        return _json_from_response(response)


@dataclass
class ReplayClassificationClient:
    responses_by_model: dict[str, list[dict[str, object] | Exception]]
    calls: list[dict[str, object]] = field(default_factory=list)

    @classmethod
    def from_mapping(
        cls,
        responses_by_model: Mapping[str, tuple[dict[str, object] | Exception, ...]],
    ) -> "ReplayClassificationClient":
        return cls(
            responses_by_model={
                model: list(responses)
                for model, responses in responses_by_model.items()
            }
        )

    def classify(self, prompt: dict[str, object], *, model: str) -> dict[str, object]:
        self.calls.append({"prompt": prompt, "model": model})
        responses = self.responses_by_model.get(model)
        if not responses:
            raise AssertionError(f"unexpected model call: {model}")
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def classify_from_payload(event_id: str, payload: dict[str, object]) -> EventClassification:
    direction = _direction(payload.get("direction"))
    confidence = _confidence(payload.get("confidence"), default=None)
    reasoning_summary = payload.get("reasoning_summary")
    event_type = payload.get("event_type")
    if confidence is None:
        raise MalformedModelOutput("confidence is required")
    if not isinstance(reasoning_summary, str) or not reasoning_summary.strip():
        raise MalformedModelOutput("reasoning_summary is required")
    if not isinstance(event_type, str) or not event_type.strip():
        raise MalformedModelOutput("event_type is required")
    return EventClassification(
        event_id=event_id,
        relevant_to_equinor=_bool(payload.get("relevant_to_equinor")),
        direction=direction,
        confidence=confidence,
        event_type=event_type,
        reasoning_summary=reasoning_summary,
        is_reinforcement=_bool(payload.get("is_reinforcement")),
        is_contradiction=_bool(payload.get("is_contradiction")),
    )


def _filter_prompt(event: SourceEvent, job: AnalysisJobClaim) -> dict[str, object]:
    return {
        "task": "fast_relevance_filter",
        "source": event.source,
        "source_class": event.source_class.value,
        "source_id": event.source_id,
        "source_tier": event.source_tier.value if event.source_tier else None,
        "title": event.title,
        "url": event.url,
        "payload": event.payload,
        "job_payload": job.payload,
    }


def _analysis_prompt(
    event: SourceEvent,
    job: AnalysisJobClaim,
    filter_response: dict[str, object],
) -> dict[str, object]:
    return {
        "task": "trade_relevant_event_classification",
        "instrument": "EQNR.OL",
        "thesis_context": (
            "Classify whether this public event affects Equinor through oil price, "
            "US-Iran escalation, Hormuz closure risk, sanctions, or market control signals."
        ),
        "source": event.source,
        "source_class": event.source_class.value,
        "source_id": event.source_id,
        "source_tier": event.source_tier.value if event.source_tier else None,
        "source_category": event.source_category.value if event.source_category else None,
        "title": event.title,
        "url": event.url,
        "payload": event.payload,
        "job_payload": job.payload,
        "filter_response": filter_response,
    }


def _direction(value: object) -> Direction:
    try:
        return Direction(str(value))
    except ValueError as exc:
        raise MalformedModelOutput(f"unsupported direction: {value}") from exc


def _confidence(value: object, *, default: float | None) -> float | None:
    if value is None:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise MalformedModelOutput("confidence must be numeric") from exc
    if not 0 <= parsed <= 1:
        raise MalformedModelOutput("confidence must be between 0 and 1")
    return parsed


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _json_from_response(response: object) -> dict[str, object]:
    import json

    output_text = getattr(response, "output_text", None)
    if not isinstance(output_text, str):
        raise MalformedModelOutput("OpenAI response did not include output_text")
    parsed = json.loads(output_text)
    if not isinstance(parsed, dict):
        raise MalformedModelOutput("model output must be a JSON object")
    return parsed


def _json_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _optional_enum(enum_type: type[Enum], value: object) -> object | None:
    if value is None:
        return None
    return enum_type(str(value))


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    return float(value)
