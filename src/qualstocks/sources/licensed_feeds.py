from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from qualstocks.domain import SourceCategory, SourceClass, SourceTier
from qualstocks.sources.adapters import AdapterKind, BaseSourceAdapter
from qualstocks.sources.registry import SourceDefinition


@dataclass(frozen=True)
class LicensedFeedNormalizerConfig:
    default_instrument: str = "EQNR.OL"


@dataclass(frozen=True)
class LsegReutersEventNormalizer:
    config: LicensedFeedNormalizerConfig = LicensedFeedNormalizerConfig()

    def normalize(self, payload: Mapping[str, object]):
        from qualstocks.ingestion.contract import RawAdapterEvent

        headline = _string(payload, "headline") or _string(payload, "title")
        source_timestamp = _timestamp(
            _string(payload, "versionCreated")
            or _string(payload, "firstCreated")
            or _string(payload, "publishedAt")
        )
        story_id = _string(payload, "storyId") or _string(payload, "id") or headline
        url = _string(payload, "uri") or _string(payload, "url")
        topics = _string_list(payload.get("topics") or payload.get("subjects"))
        instruments = _string_list(payload.get("instruments") or payload.get("ric"))

        return RawAdapterEvent(
            source="Reuters / LSEG News Service",
            source_id="reuters_lseg_news",
            source_class=SourceClass.OSINT,
            source_category=SourceCategory.WIRE_OR_NEWSPAPER,
            source_tier=SourceTier.TRIGGER,
            instrument=_instrument(instruments, self.config.default_instrument),
            payload={
                "headline": headline,
                "body": _string(payload, "body") or _string(payload, "storyBody"),
                "topics": topics,
                "instruments": instruments,
                "urgency": _string(payload, "urgency"),
                "provider": "lseg_reuters",
                "raw": dict(payload),
            },
            provenance={
                "provider": "lseg_reuters",
                "url": url,
                "raw_event_ref": story_id,
                "topic_tags": topics,
            },
            source_timestamp=source_timestamp,
            idempotency_key=f"lseg-reuters:{story_id}" if story_id else None,
        )


@dataclass(frozen=True)
class ApMediaEventNormalizer:
    config: LicensedFeedNormalizerConfig = LicensedFeedNormalizerConfig()

    def normalize(self, payload: Mapping[str, object]):
        from qualstocks.ingestion.contract import RawAdapterEvent

        item = _mapping(payload.get("item")) or payload
        meta = _mapping(payload.get("meta"))
        headline = _string(item, "headline") or _string(item, "title")
        item_id = _string(item, "id") or _string(meta, "id") or headline
        source_timestamp = _timestamp(
            _string(item, "versioncreated")
            or _string(item, "firstcreated")
            or _string(item, "published")
            or _string(payload, "updated")
        )
        topics = _string_list(item.get("subjects") or item.get("keywords"))

        return RawAdapterEvent(
            source="AP Media API",
            source_id="ap_media_api",
            source_class=SourceClass.OSINT,
            source_category=SourceCategory.WIRE_OR_NEWSPAPER,
            source_tier=SourceTier.TRIGGER,
            instrument=_instrument(
                _string_list(item.get("instruments")),
                self.config.default_instrument,
            ),
            payload={
                "headline": headline,
                "body": _string(item, "body_text") or _string(item, "description_text"),
                "topics": topics,
                "provider": "ap_media_api",
                "raw": dict(payload),
            },
            provenance={
                "provider": "ap_media_api",
                "url": _string(item, "url") or _string(item, "rendition_url"),
                "raw_event_ref": item_id,
                "topic_tags": topics,
            },
            source_timestamp=source_timestamp,
            idempotency_key=f"ap-media-api:{item_id}" if item_id else None,
        )


class LsegReutersLicensedFeedAdapter(BaseSourceAdapter):
    def __init__(self, source_definition: SourceDefinition | None = None) -> None:
        super().__init__(
            source="Reuters / LSEG News Service",
            source_class=SourceClass.OSINT,
            kind=AdapterKind.STREAMING_API,
            source_definition=source_definition,
        )
        self.normalizer = LsegReutersEventNormalizer()

    def normalize_payload(self, payload: Mapping[str, object]) -> RawAdapterEvent:
        return self.normalizer.normalize(payload)


class ApMediaLicensedFeedAdapter(BaseSourceAdapter):
    def __init__(self, source_definition: SourceDefinition | None = None) -> None:
        super().__init__(
            source="AP Media API",
            source_class=SourceClass.OSINT,
            kind=AdapterKind.FALLBACK_POLLING,
            source_definition=source_definition,
        )
        self.normalizer = ApMediaEventNormalizer()

    def normalize_payload(self, payload: Mapping[str, object]) -> RawAdapterEvent:
        return self.normalizer.normalize(payload)


def _timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _instrument(values: tuple[str, ...], default: str) -> str:
    for value in values:
        normalized = value.upper()
        if normalized in {"EQNR.OL", "EQNR", "EQNR:NO", "EQNR.OSL"}:
            return "EQNR.OL"
    return default


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _string(row: Mapping[str, object], key: str) -> str:
    value = row.get(key, "")
    if isinstance(value, str):
        return value.strip()
    return ""


def _string_list(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()
