from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite

from qualstocks.domain import SourceCategory, SourceClass, SourceEvent, SourceTier


class StrEnum(str, Enum):
    pass


class HormuzClosureState(StrEnum):
    OPEN = "open"
    DEGRADED = "degraded"
    EFFECTIVELY_CLOSED = "effectively_closed"
    CONFIRMED_CLOSED = "confirmed_closed"
    REOPENED = "reopened"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class HormuzClosureAssessment:
    state: HormuzClosureState
    confidence: float
    reasons: tuple[str, ...]
    source_event_ids: tuple[str, ...]
    oil_price_transmission: str
    opens_or_strengthens_hypothesis: bool

    @property
    def is_actionable(self) -> bool:
        return self.opens_or_strengthens_hypothesis


@dataclass(frozen=True)
class _Evidence:
    state: HormuzClosureState
    score: float
    reason: str
    event_id: str


@dataclass(frozen=True)
class HormuzClosureSignal:
    min_actionable_confidence: float = 0.62
    severe_transit_drop_pct: float = -0.7
    degraded_transit_drop_pct: float = -0.35
    severe_prediction_probability: float = 0.72
    degraded_prediction_probability: float = 0.45
    queue_warning_count: int = 8
    evidence: tuple[_Evidence, ...] = field(default_factory=tuple)

    def assess(self, events: tuple[SourceEvent, ...]) -> HormuzClosureAssessment:
        evidence = tuple(item for event in events for item in self._event_evidence(event))
        if not evidence:
            return self._unknown()

        reopened = [item for item in evidence if item.state == HormuzClosureState.REOPENED]
        closure = [
            item
            for item in evidence
            if item.state
            in {
                HormuzClosureState.CONFIRMED_CLOSED,
                HormuzClosureState.EFFECTIVELY_CLOSED,
                HormuzClosureState.DEGRADED,
            }
        ]
        open_evidence = [item for item in evidence if item.state == HormuzClosureState.OPEN]

        if reopened and not closure:
            return self._assessment(HormuzClosureState.REOPENED, reopened)
        if closure:
            best_state = self._strongest_closure_state(closure)
            return self._assessment(best_state, closure)
        if open_evidence:
            return self._assessment(HormuzClosureState.OPEN, open_evidence, actionable=False)
        return self._unknown()

    def _event_evidence(self, event: SourceEvent) -> tuple[_Evidence, ...]:
        evidence: list[_Evidence] = []
        text = f"{event.title} {event.payload.get('summary', '')}".lower()

        if _mentions_hormuz(text):
            evidence.extend(self._text_evidence(event, text))

        if event.source_category == SourceCategory.AIS_TANKER_FLOW:
            evidence.extend(self._ais_evidence(event))

        if event.source_category == SourceCategory.PREDICTION_MARKET:
            evidence.extend(self._prediction_market_evidence(event, text))

        if event.source_category == SourceCategory.ENERGY_MARKET:
            evidence.extend(self._energy_market_evidence(event))

        return tuple(evidence)

    def _text_evidence(self, event: SourceEvent, text: str) -> tuple[_Evidence, ...]:
        weight = _source_weight(event)
        if any(term in text for term in _REOPENED_TERMS):
            return (
                _Evidence(
                    state=HormuzClosureState.REOPENED,
                    score=min(0.95, 0.72 * weight),
                    reason="Hormuz reopening or resumed navigation report",
                    event_id=event.id,
                ),
            )

        if _source_is_official_or_maritime(event) and any(term in text for term in _CLOSED_TERMS):
            return (
                _Evidence(
                    state=HormuzClosureState.CONFIRMED_CLOSED,
                    score=min(0.98, 0.88 * weight),
                    reason="Official or maritime-security source reports closure/blockade",
                    event_id=event.id,
                ),
            )

        if any(term in text for term in _SEVERE_DISRUPTION_TERMS):
            return (
                _Evidence(
                    state=HormuzClosureState.EFFECTIVELY_CLOSED,
                    score=min(0.9, 0.78 * weight),
                    reason="Severe Hormuz navigation disruption reported",
                    event_id=event.id,
                ),
            )

        if any(term in text for term in _DEGRADED_TERMS):
            return (
                _Evidence(
                    state=HormuzClosureState.DEGRADED,
                    score=min(0.82, 0.62 * weight),
                    reason="Hormuz maritime risk or degraded navigation report",
                    event_id=event.id,
                ),
            )

        return ()

    def _ais_evidence(self, event: SourceEvent) -> tuple[_Evidence, ...]:
        transit_drop_pct = _number(event.payload.get("transit_drop_pct"))
        queue_count = _integer(event.payload.get("queue_count"))
        reroute_count = _integer(event.payload.get("reroute_count"))
        ais_gap_rate = _number(event.payload.get("ais_gap_rate"))

        if transit_drop_pct is not None and transit_drop_pct <= self.severe_transit_drop_pct:
            return (
                _Evidence(
                    state=HormuzClosureState.EFFECTIVELY_CLOSED,
                    score=0.86,
                    reason="AIS/tanker flow shows severe transit collapse",
                    event_id=event.id,
                ),
            )

        if (
            transit_drop_pct is not None
            and transit_drop_pct <= self.degraded_transit_drop_pct
            or queue_count is not None
            and queue_count >= self.queue_warning_count
            or reroute_count is not None
            and reroute_count >= self.queue_warning_count
            or ais_gap_rate is not None
            and ais_gap_rate >= 0.4
        ):
            return (
                _Evidence(
                    state=HormuzClosureState.DEGRADED,
                    score=0.66,
                    reason="AIS/tanker flow shows degraded Hormuz traffic",
                    event_id=event.id,
                ),
            )

        if transit_drop_pct is not None and transit_drop_pct > -0.1:
            return (
                _Evidence(
                    state=HormuzClosureState.OPEN,
                    score=0.58,
                    reason="AIS/tanker flow remains near baseline",
                    event_id=event.id,
                ),
            )

        return ()

    def _prediction_market_evidence(
        self,
        event: SourceEvent,
        text: str,
    ) -> tuple[_Evidence, ...]:
        probability = _number(event.payload.get("probability"))
        delta = _number(event.payload.get("probability_delta"))
        if not _mentions_hormuz(text):
            return ()

        if probability is not None and probability >= self.severe_prediction_probability:
            return (
                _Evidence(
                    state=HormuzClosureState.EFFECTIVELY_CLOSED,
                    score=0.74,
                    reason="Prediction market implies high Hormuz closure probability",
                    event_id=event.id,
                ),
            )

        if (
            probability is not None
            and probability >= self.degraded_prediction_probability
            or delta is not None
            and delta >= 0.18
        ):
            return (
                _Evidence(
                    state=HormuzClosureState.DEGRADED,
                    score=0.62,
                    reason="Prediction market reprices Hormuz closure risk upward",
                    event_id=event.id,
                ),
            )

        return ()

    def _energy_market_evidence(self, event: SourceEvent) -> tuple[_Evidence, ...]:
        brent_move_pct = _number(event.payload.get("brent_move_pct"))
        wti_move_pct = _number(event.payload.get("wti_move_pct"))
        if (
            brent_move_pct is not None
            and brent_move_pct >= 4.0
            or wti_move_pct is not None
            and wti_move_pct >= 4.0
        ):
            return (
                _Evidence(
                    state=HormuzClosureState.DEGRADED,
                    score=0.52,
                    reason="Oil prices moved sharply; use as confirmation, not sole trigger",
                    event_id=event.id,
                ),
            )
        return ()

    def _assessment(
        self,
        state: HormuzClosureState,
        evidence: list[_Evidence],
        actionable: bool | None = None,
    ) -> HormuzClosureAssessment:
        confidence = min(0.99, sum(item.score for item in evidence) / max(1, len(evidence)) + 0.08)
        if len({item.event_id for item in evidence}) > 1:
            confidence = min(0.99, confidence + 0.08)
        if actionable is None:
            actionable = (
                state
                in {
                    HormuzClosureState.DEGRADED,
                    HormuzClosureState.EFFECTIVELY_CLOSED,
                    HormuzClosureState.CONFIRMED_CLOSED,
                }
                and confidence >= self.min_actionable_confidence
            )
        return HormuzClosureAssessment(
            state=state,
            confidence=round(confidence, 4),
            reasons=tuple(item.reason for item in evidence),
            source_event_ids=tuple(item.event_id for item in evidence),
            oil_price_transmission=_oil_price_transmission(state),
            opens_or_strengthens_hypothesis=actionable,
        )

    def _unknown(self) -> HormuzClosureAssessment:
        return HormuzClosureAssessment(
            state=HormuzClosureState.UNKNOWN,
            confidence=0,
            reasons=(),
            source_event_ids=(),
            oil_price_transmission="No concrete Hormuz closure signal is present.",
            opens_or_strengthens_hypothesis=False,
        )

    @staticmethod
    def _strongest_closure_state(evidence: list[_Evidence]) -> HormuzClosureState:
        rank = {
            HormuzClosureState.DEGRADED: 1,
            HormuzClosureState.EFFECTIVELY_CLOSED: 2,
            HormuzClosureState.CONFIRMED_CLOSED: 3,
        }
        return max(evidence, key=lambda item: rank[item.state]).state


_HORMUZ_TERMS = ("hormuz", "strait", "gulf of oman", "persian gulf")
_CLOSED_TERMS = ("closed", "closure", "blockade", "blocked", "halted navigation")
_SEVERE_DISRUPTION_TERMS = (
    "mine",
    "mines",
    "missile",
    "seized",
    "seizure",
    "attack",
    "attacked",
    "suspended transit",
    "navigation suspended",
)
_DEGRADED_TERMS = (
    "warning",
    "advisory",
    "incident",
    "rerouting",
    "rerouted",
    "delayed",
    "traffic disruption",
    "elevated risk",
)
_REOPENED_TERMS = ("reopened", "resumed", "navigation resumed", "traffic resumed")


def _mentions_hormuz(text: str) -> bool:
    return any(term in text for term in _HORMUZ_TERMS)


def _source_is_official_or_maritime(event: SourceEvent) -> bool:
    return event.source_class == SourceClass.OFFICIAL_ACTOR or event.source_category in {
        SourceCategory.MARITIME_SECURITY,
        SourceCategory.AIS_TANKER_FLOW,
    }


def _source_weight(event: SourceEvent) -> float:
    if event.reliability_score is not None:
        return max(0.6, min(1.15, event.reliability_score + 0.18))
    if event.source_tier == SourceTier.TRIGGER:
        return 1
    return 0.82


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if isfinite(number) else None
    return None


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _oil_price_transmission(state: HormuzClosureState) -> str:
    if state == HormuzClosureState.CONFIRMED_CLOSED:
        return "Confirmed Hormuz closure is a direct oil supply chokepoint shock."
    if state == HormuzClosureState.EFFECTIVELY_CLOSED:
        return (
            "Practical Hormuz closure implies severe tanker-flow disruption "
            "and oil-risk repricing."
        )
    if state == HormuzClosureState.DEGRADED:
        return "Degraded Hormuz navigation increases oil supply-risk premium."
    if state == HormuzClosureState.REOPENED:
        return "Reopening reduces the oil supply-risk premium created by Hormuz disruption."
    if state == HormuzClosureState.OPEN:
        return "Open Hormuz traffic weakens the oil supply-risk thesis."
    return "No concrete Hormuz closure signal is present."
