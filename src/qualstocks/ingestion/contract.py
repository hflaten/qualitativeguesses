from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Mapping

from qualstocks.domain import SourceCategory, SourceClass, SourceEvent, SourceTier
from qualstocks.ingestion.idempotency import build_idempotency_key


class StrEnum(str, Enum):
    pass


class AdapterEventErrorCode(StrEnum):
    MALFORMED = "malformed"
    LATE = "late"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class RawAdapterEvent:
    source: str
    source_class: SourceClass
    instrument: str
    payload: Mapping[str, object]
    provenance: Mapping[str, object]
    source_id: str | None = None
    source_tier: SourceTier | None = None
    source_category: SourceCategory | None = None
    source_timestamp: datetime | None = None
    first_seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    idempotency_key: str | None = None


@dataclass(frozen=True)
class NormalizedAdapterEvent:
    event: SourceEvent
    idempotency_key: str


@dataclass(frozen=True)
class AdapterEventValidationError:
    code: AdapterEventErrorCode
    reason: str


@dataclass(frozen=True)
class AdapterEventValidationResult:
    errors: tuple[AdapterEventValidationError, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class AdapterContractConfig:
    supported_instruments: tuple[str, ...] = ("EQNR.OL",)
    max_source_event_age: timedelta = timedelta(days=7)


def validate_raw_adapter_event(
    raw_event: RawAdapterEvent,
    config: AdapterContractConfig = AdapterContractConfig(),
) -> AdapterEventValidationResult:
    errors: list[AdapterEventValidationError] = []
    if not raw_event.source.strip():
        errors.append(AdapterEventValidationError(AdapterEventErrorCode.MALFORMED, "source is required"))
    if not raw_event.instrument.strip():
        errors.append(
            AdapterEventValidationError(AdapterEventErrorCode.MALFORMED, "instrument is required")
        )
    elif raw_event.instrument not in config.supported_instruments:
        errors.append(
            AdapterEventValidationError(
                AdapterEventErrorCode.UNSUPPORTED,
                "instrument is not supported",
            )
        )
    title = _string_field(raw_event.payload, "title") or _string_field(
        raw_event.payload,
        "headline",
    )
    if not title:
        errors.append(AdapterEventValidationError(AdapterEventErrorCode.MALFORMED, "title is required"))
    if raw_event.source_timestamp is not None:
        event_age = raw_event.first_seen_at - raw_event.source_timestamp
        if event_age > config.max_source_event_age:
            errors.append(
                AdapterEventValidationError(
                    AdapterEventErrorCode.LATE,
                    "source event is too old",
                )
            )
    return AdapterEventValidationResult(errors=tuple(errors))


def normalize_raw_adapter_event(
    raw_event: RawAdapterEvent,
    config: AdapterContractConfig = AdapterContractConfig(),
) -> NormalizedAdapterEvent:
    validation = validate_raw_adapter_event(raw_event, config)
    if not validation.valid:
        reasons = ", ".join(error.reason for error in validation.errors)
        raise ValueError(f"raw adapter event is invalid: {reasons}")

    title = _string_field(raw_event.payload, "title") or _string_field(
        raw_event.payload,
        "headline",
    )
    if not title:
        raise ValueError("raw adapter event is invalid: title is required")

    url = _string_field(raw_event.provenance, "url") or _string_field(
        raw_event.provenance,
        "canonical_url",
    )
    raw_event_ref = _string_field(raw_event.provenance, "raw_event_ref")
    payload = dict(raw_event.payload)
    payload["provenance"] = dict(raw_event.provenance)
    if raw_event_ref:
        payload["raw_event_ref"] = raw_event_ref

    event = SourceEvent(
        source=raw_event.source,
        source_class=raw_event.source_class,
        title=title,
        url=url,
        payload=payload,
        instrument=raw_event.instrument,
        source_id=raw_event.source_id,
        source_tier=raw_event.source_tier,
        source_category=raw_event.source_category,
        raw_event_ref=raw_event_ref,
        source_timestamp=raw_event.source_timestamp,
        first_seen_at=raw_event.first_seen_at,
    )
    return NormalizedAdapterEvent(
        event=event,
        idempotency_key=raw_event.idempotency_key or build_idempotency_key(event),
    )


def _string_field(row: Mapping[str, object], key: str) -> str:
    value = row.get(key, "")
    if isinstance(value, str):
        return value.strip()
    return ""
