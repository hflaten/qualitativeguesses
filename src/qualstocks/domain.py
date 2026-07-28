from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4


class StrEnum(str, Enum):
    pass


class HypothesisState(StrEnum):
    IDLE = "idle"
    CANDIDATE = "candidate"
    ACTIVE = "active"
    REINFORCED = "reinforced"
    CONFIRMED_BY_NORWEGIAN_SOURCE = "confirmed_by_norwegian_source"
    EXITING = "exiting"
    EXITED = "exited"
    EXPIRED = "expired"
    CONTRADICTED = "contradicted"


class SourceClass(StrEnum):
    PREDICTION_MARKET = "prediction_market"
    OFFICIAL_ACTOR = "official_actor"
    OSINT = "osint"
    NORWEGIAN_CONFIRMATION = "norwegian_confirmation"
    EQUINOR_OR_EXCHANGE = "equinor_or_exchange"
    MARKET_CONTROL = "market_control"


class SourceTier(StrEnum):
    TRIGGER = "trigger"
    CONFIRMATION = "confirmation"
    CONTROL = "control"


class SourceCategory(StrEnum):
    PREDICTION_MARKET = "prediction_market"
    OFFICIAL_US = "official_us"
    OFFICIAL_IRAN = "official_iran"
    NORWEGIAN_MARKET = "norwegian_market"
    NORWEGIAN_PRESS = "norwegian_press"
    WIRE_OR_NEWSPAPER = "wire_or_newspaper"
    MARITIME_SECURITY = "maritime_security"
    AIS_TANKER_FLOW = "ais_tanker_flow"
    ENERGY_MARKET = "energy_market"
    MACRO_FX = "macro_fx"
    OSINT_AGGREGATE = "osint_aggregate"


class AccessMethod(StrEnum):
    WEBSOCKET = "websocket"
    WEBHOOK = "webhook"
    STREAMING_API = "streaming_api"
    REST_API = "rest_api"
    RSS = "rss"
    OFFICIAL_PAGE = "official_page"
    PAID_API = "paid_api"
    EMAIL_ALERT = "email_alert"
    MANUAL_REVIEW_ONLY = "manual_review_only"


class LicensingClass(StrEnum):
    PUBLIC = "public"
    PUBLIC_WITH_TERMS = "public_with_terms"
    PAID_LICENSE_REQUIRED = "paid_license_required"
    SCRAPING_PROHIBITED = "scraping_prohibited"
    UNKNOWN = "unknown"


class Direction(StrEnum):
    BULLISH_EQUINOR = "bullish_equinor"
    BEARISH_EQUINOR = "bearish_equinor"
    UNCLEAR = "unclear"


@dataclass(frozen=True)
class SourceEvent:
    source: str
    source_class: SourceClass
    title: str
    url: str
    payload: dict[str, object]
    instrument: str | None = None
    source_id: str | None = None
    source_tier: SourceTier | None = None
    source_category: SourceCategory | None = None
    reliability_score: float | None = None
    relevance_score: float | None = None
    language: str | None = None
    translation_required: bool = False
    licensing_class: LicensingClass | None = None
    raw_event_ref: str | None = None
    source_timestamp: datetime | None = None
    first_seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: str = field(default_factory=lambda: str(uuid4()))


@dataclass(frozen=True)
class EventClassification:
    event_id: str
    relevant_to_equinor: bool
    direction: Direction
    confidence: float
    event_type: str
    reasoning_summary: str
    is_reinforcement: bool = False
    is_contradiction: bool = False


@dataclass(frozen=True)
class ActiveHypothesis:
    thesis: str
    direction: Direction
    confidence: float
    state: HypothesisState
    source_event_ids: tuple[str, ...]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    norwegian_confirmation_at: datetime | None = None
    id: str = field(default_factory=lambda: str(uuid4()))

    def can_accept_reinforcement(self) -> bool:
        return self.state in {
            HypothesisState.ACTIVE,
            HypothesisState.REINFORCED,
            HypothesisState.CONFIRMED_BY_NORWEGIAN_SOURCE,
        }
