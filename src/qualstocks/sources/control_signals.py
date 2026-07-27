from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol

from qualstocks.domain import SourceEvent
from qualstocks.sources.registry import DEFAULT_SOURCE_REGISTRY, SourceDefinition


class StrEnum(str, Enum):
    pass


class ControlSignalKind(StrEnum):
    MARITIME_ALERT = "maritime_alert"
    AIS_TANKER_FLOW = "ais_tanker_flow"
    ENERGY_MARKET = "energy_market"
    MACRO_FX = "macro_fx"
    MEDIA_ACCELERATION = "media_acceleration"
    NUCLEAR_ESCALATION = "nuclear_escalation"


class ControlSignalAction(StrEnum):
    ANNOTATE = "annotate"
    STRENGTHEN = "strengthen"
    WEAKEN = "weaken"
    SUPPRESS = "suppress"


@dataclass(frozen=True)
class ControlSignalSnapshot:
    source_id: str
    kind: ControlSignalKind
    title: str
    url: str
    summary: str
    confidence: float
    action: ControlSignalAction = ControlSignalAction.ANNOTATE
    observed_at: datetime | None = None
    raw_event_ref: str | None = None
    metrics: dict[str, object] | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")


class ControlSignalProvider(Protocol):
    def snapshots(self) -> tuple[ControlSignalSnapshot, ...]:
        """Return normalized provider snapshots without exposing credentials."""


@dataclass(frozen=True)
class ControlSignalNormalizer:
    def normalize(self, snapshot: ControlSignalSnapshot) -> SourceEvent:
        source_definition = DEFAULT_SOURCE_REGISTRY.require(snapshot.source_id)
        payload = {
            "summary": snapshot.summary,
            "control_signal_kind": snapshot.kind.value,
            "control_signal_action": snapshot.action.value,
            "confidence": snapshot.confidence,
            "raw_event_ref": snapshot.raw_event_ref or snapshot.title,
        }
        if snapshot.metrics:
            payload.update(snapshot.metrics)
        return _source_event(
            source_definition=source_definition,
            title=snapshot.title,
            url=snapshot.url,
            payload=payload,
            raw_event_ref=snapshot.raw_event_ref or snapshot.title,
            source_timestamp=snapshot.observed_at,
        )


def ukmto_alert_event(
    *,
    title: str,
    url: str,
    summary: str,
    confidence: float,
    observed_at: datetime | None = None,
    raw_event_ref: str | None = None,
) -> SourceEvent:
    snapshot = ControlSignalSnapshot(
        source_id="ukmto",
        kind=ControlSignalKind.MARITIME_ALERT,
        title=title,
        url=url,
        summary=summary,
        confidence=confidence,
        action=ControlSignalAction.STRENGTHEN,
        observed_at=observed_at,
        raw_event_ref=raw_event_ref,
    )
    return ControlSignalNormalizer().normalize(snapshot)


def ais_tanker_flow_event(
    *,
    source_id: str,
    title: str,
    url: str,
    transit_drop_pct: float | None = None,
    queue_count: int | None = None,
    reroute_count: int | None = None,
    ais_gap_rate: float | None = None,
    observed_at: datetime | None = None,
    raw_event_ref: str | None = None,
) -> SourceEvent:
    metrics: dict[str, object] = {}
    if transit_drop_pct is not None:
        metrics["transit_drop_pct"] = transit_drop_pct
    if queue_count is not None:
        metrics["queue_count"] = queue_count
    if reroute_count is not None:
        metrics["reroute_count"] = reroute_count
    if ais_gap_rate is not None:
        metrics["ais_gap_rate"] = ais_gap_rate
    confidence = _bounded_confidence(
        0.45
        + abs(transit_drop_pct or 0) * 0.5
        + min(queue_count or 0, 20) * 0.01
        + min(reroute_count or 0, 20) * 0.01
        + (ais_gap_rate or 0) * 0.25
    )
    action = (
        ControlSignalAction.STRENGTHEN
        if transit_drop_pct is not None and transit_drop_pct <= -0.35
        else ControlSignalAction.ANNOTATE
    )
    snapshot = ControlSignalSnapshot(
        source_id=source_id,
        kind=ControlSignalKind.AIS_TANKER_FLOW,
        title=title,
        url=url,
        summary="AIS/tanker-flow control signal for Hormuz transit risk.",
        confidence=confidence,
        action=action,
        observed_at=observed_at,
        raw_event_ref=raw_event_ref,
        metrics=metrics,
    )
    return ControlSignalNormalizer().normalize(snapshot)


def energy_market_event(
    *,
    source_id: str = "brent_wti",
    title: str,
    url: str,
    brent_move_pct: float | None = None,
    wti_move_pct: float | None = None,
    observed_at: datetime | None = None,
    raw_event_ref: str | None = None,
) -> SourceEvent:
    metrics: dict[str, object] = {}
    if brent_move_pct is not None:
        metrics["brent_move_pct"] = brent_move_pct
    if wti_move_pct is not None:
        metrics["wti_move_pct"] = wti_move_pct
    max_move = max(abs(brent_move_pct or 0), abs(wti_move_pct or 0))
    snapshot = ControlSignalSnapshot(
        source_id=source_id,
        kind=ControlSignalKind.ENERGY_MARKET,
        title=title,
        url=url,
        summary="Oil-market control signal; confirms repricing but is not a standalone trigger.",
        confidence=_bounded_confidence(0.35 + max_move / 10),
        action=ControlSignalAction.ANNOTATE,
        observed_at=observed_at,
        raw_event_ref=raw_event_ref,
        metrics=metrics,
    )
    return ControlSignalNormalizer().normalize(snapshot)


def macro_fx_event(
    *,
    title: str,
    url: str,
    usd_nok_move_pct: float,
    observed_at: datetime | None = None,
    raw_event_ref: str | None = None,
) -> SourceEvent:
    snapshot = ControlSignalSnapshot(
        source_id="usd_nok",
        kind=ControlSignalKind.MACRO_FX,
        title=title,
        url=url,
        summary="USD/NOK control signal for Norway/Equinor market translation.",
        confidence=_bounded_confidence(0.3 + abs(usd_nok_move_pct) / 6),
        action=ControlSignalAction.ANNOTATE,
        observed_at=observed_at,
        raw_event_ref=raw_event_ref,
        metrics={"usd_nok_move_pct": usd_nok_move_pct},
    )
    return ControlSignalNormalizer().normalize(snapshot)


def gdelt_media_acceleration_event(
    *,
    title: str,
    url: str,
    article_count: int,
    acceleration_ratio: float,
    observed_at: datetime | None = None,
    raw_event_ref: str | None = None,
) -> SourceEvent:
    snapshot = ControlSignalSnapshot(
        source_id="gdelt",
        kind=ControlSignalKind.MEDIA_ACCELERATION,
        title=title,
        url=url,
        summary="GDELT media acceleration control signal.",
        confidence=_bounded_confidence(0.25 + min(acceleration_ratio, 5) / 8),
        action=ControlSignalAction.ANNOTATE,
        observed_at=observed_at,
        raw_event_ref=raw_event_ref,
        metrics={
            "article_count": article_count,
            "acceleration_ratio": acceleration_ratio,
        },
    )
    return ControlSignalNormalizer().normalize(snapshot)


def iaea_nuclear_escalation_event(
    *,
    title: str,
    url: str,
    summary: str,
    confidence: float,
    observed_at: datetime | None = None,
    raw_event_ref: str | None = None,
) -> SourceEvent:
    snapshot = ControlSignalSnapshot(
        source_id="iaea",
        kind=ControlSignalKind.NUCLEAR_ESCALATION,
        title=title,
        url=url,
        summary=summary,
        confidence=confidence,
        action=ControlSignalAction.ANNOTATE,
        observed_at=observed_at,
        raw_event_ref=raw_event_ref,
    )
    return ControlSignalNormalizer().normalize(snapshot)


def _source_event(
    *,
    source_definition: SourceDefinition,
    title: str,
    url: str,
    payload: dict[str, object],
    raw_event_ref: str,
    source_timestamp: datetime | None,
) -> SourceEvent:
    return SourceEvent(
        source=source_definition.name,
        source_class=source_definition.source_class,
        title=title,
        url=url,
        payload=payload,
        source_id=source_definition.source_id,
        source_tier=source_definition.tier,
        source_category=source_definition.category,
        reliability_score=source_definition.reliability_score,
        language=source_definition.language,
        translation_required=source_definition.translation_required,
        licensing_class=source_definition.licensing_class,
        raw_event_ref=raw_event_ref,
        source_timestamp=source_timestamp,
    )


def _bounded_confidence(value: float) -> float:
    return max(0.0, min(1.0, round(value, 4)))
