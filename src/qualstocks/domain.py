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
