from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import StringIO
from typing import Iterable, Mapping, Sequence


DEFAULT_RESPONSE_WINDOWS_MINUTES = (1, 5, 10, 30, 40, 50)
DEFAULT_TRADING_COST_BPS = 10.0


@dataclass(frozen=True)
class ResearchEvent:
    case_id: str
    event_id: str
    source_id: str
    source_name: str
    source_class: str
    source_category: str
    source_tier: str
    event_timestamp: datetime
    source_timestamp: datetime
    first_seen_at: datetime
    headline: str
    body: str
    topic_classification: str
    equinor_relevance: float
    oil_impact_channel: str
    direction: str
    confidence: float

    @property
    def source_latency_seconds(self) -> float:
        return (self.first_seen_at - self.source_timestamp).total_seconds()


@dataclass(frozen=True)
class IntradayPricePoint:
    timestamp: datetime
    mid: float
    bid: float | None = None
    ask: float | None = None


@dataclass(frozen=True)
class ResearchControlPoint:
    timestamp: datetime
    value: float


@dataclass(frozen=True)
class PredictivePowerDataset:
    events: tuple[ResearchEvent, ...]
    eqnr_prices: tuple[IntradayPricePoint, ...]
    brent_points: tuple[ResearchControlPoint, ...] = ()
    usd_nok_points: tuple[ResearchControlPoint, ...] = ()


@dataclass(frozen=True)
class PredictivePowerRow:
    case_id: str
    event_id: str
    source_id: str
    source_name: str
    source_class: str
    source_category: str
    source_tier: str
    topic_classification: str
    oil_impact_channel: str
    direction: str
    confidence: float
    event_timestamp: datetime
    source_timestamp: datetime
    first_seen_at: datetime
    source_latency_seconds: float
    source_lead_lag_seconds: float
    source_rank_in_case: int
    window_minutes: int
    entry_price_at: datetime | None
    exit_price_at: datetime | None
    entry_price: float | None
    exit_price: float | None
    eqnr_return_pct: float | None
    directional_return_pct: float | None
    post_cost_directional_return_pct: float | None
    brent_at_entry: float | None
    brent_at_exit: float | None
    brent_change_pct: float | None
    usd_nok_at_entry: float | None
    usd_nok_at_exit: float | None
    usd_nok_change_pct: float | None
    missing_data_reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "event_id": self.event_id,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "source_class": self.source_class,
            "source_category": self.source_category,
            "source_tier": self.source_tier,
            "topic_classification": self.topic_classification,
            "oil_impact_channel": self.oil_impact_channel,
            "direction": self.direction,
            "confidence": self.confidence,
            "event_timestamp": _iso(self.event_timestamp),
            "source_timestamp": _iso(self.source_timestamp),
            "first_seen_at": _iso(self.first_seen_at),
            "source_latency_seconds": self.source_latency_seconds,
            "source_lead_lag_seconds": self.source_lead_lag_seconds,
            "source_rank_in_case": self.source_rank_in_case,
            "window_minutes": self.window_minutes,
            "entry_price_at": _iso_or_none(self.entry_price_at),
            "exit_price_at": _iso_or_none(self.exit_price_at),
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "eqnr_return_pct": self.eqnr_return_pct,
            "directional_return_pct": self.directional_return_pct,
            "post_cost_directional_return_pct": self.post_cost_directional_return_pct,
            "brent_at_entry": self.brent_at_entry,
            "brent_at_exit": self.brent_at_exit,
            "brent_change_pct": self.brent_change_pct,
            "usd_nok_at_entry": self.usd_nok_at_entry,
            "usd_nok_at_exit": self.usd_nok_at_exit,
            "usd_nok_change_pct": self.usd_nok_change_pct,
            "missing_data_reason": self.missing_data_reason,
        }


@dataclass(frozen=True)
class SourceRanking:
    source_id: str
    source_name: str
    observation_count: int
    first_source_count: int
    avg_latency_seconds: float
    avg_lead_lag_seconds: float
    avg_post_cost_directional_return_pct: float
    hit_rate: float
    uniqueness_score: float
    ranking_score: float

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "observation_count": self.observation_count,
            "first_source_count": self.first_source_count,
            "avg_latency_seconds": self.avg_latency_seconds,
            "avg_lead_lag_seconds": self.avg_lead_lag_seconds,
            "avg_post_cost_directional_return_pct": self.avg_post_cost_directional_return_pct,
            "hit_rate": self.hit_rate,
            "uniqueness_score": self.uniqueness_score,
            "ranking_score": self.ranking_score,
        }


def load_predictive_power_dataset(
    *,
    events_csv: str,
    eqnr_prices_csv: str,
    brent_csv: str = "",
    usd_nok_csv: str = "",
) -> PredictivePowerDataset:
    events = tuple(sorted((_event_from_row(row) for row in _read_rows(events_csv)), key=_event_key))
    prices = _price_points(eqnr_prices_csv)
    if events and not prices:
        raise ValueError("eqnr_prices_csv must include at least one price point")
    return PredictivePowerDataset(
        events=events,
        eqnr_prices=prices,
        brent_points=_control_points(brent_csv),
        usd_nok_points=_control_points(usd_nok_csv),
    )


def build_predictive_power_rows(
    dataset: PredictivePowerDataset,
    *,
    windows_minutes: Sequence[int] = DEFAULT_RESPONSE_WINDOWS_MINUTES,
    trading_cost_bps: float = DEFAULT_TRADING_COST_BPS,
) -> tuple[PredictivePowerRow, ...]:
    first_seen_by_case = _first_seen_by_case(dataset.events)
    rank_by_event = _rank_by_event(dataset.events)
    rows: list[PredictivePowerRow] = []
    for event in dataset.events:
        case_first_seen = first_seen_by_case[event.case_id]
        for window_minutes in windows_minutes:
            rows.append(
                _row_for_window(
                    event=event,
                    eqnr_prices=dataset.eqnr_prices,
                    brent_points=dataset.brent_points,
                    usd_nok_points=dataset.usd_nok_points,
                    case_first_seen=case_first_seen,
                    source_rank_in_case=rank_by_event[event.event_id],
                    window_minutes=window_minutes,
                    trading_cost_bps=trading_cost_bps,
                )
            )
    return tuple(rows)


def rank_sources(rows: Iterable[PredictivePowerRow]) -> tuple[SourceRanking, ...]:
    grouped: dict[str, list[PredictivePowerRow]] = {}
    source_names: dict[str, str] = {}
    for row in rows:
        if row.post_cost_directional_return_pct is None:
            continue
        grouped.setdefault(row.source_id, []).append(row)
        source_names[row.source_id] = row.source_name

    rankings: list[SourceRanking] = []
    for source_id, source_rows in grouped.items():
        observation_count = len(source_rows)
        first_source_count = sum(1 for row in source_rows if row.source_rank_in_case == 1)
        avg_latency = _avg(row.source_latency_seconds for row in source_rows)
        avg_lead_lag = _avg(row.source_lead_lag_seconds for row in source_rows)
        avg_return = _avg(row.post_cost_directional_return_pct for row in source_rows)
        hit_rate = (
            sum(1 for row in source_rows if row.post_cost_directional_return_pct > 0)
            / observation_count
        )
        uniqueness_score = first_source_count / observation_count
        speed_score = 1 / (1 + max(avg_lead_lag, 0) / 60)
        ranking_score = (
            avg_return
            + hit_rate
            + uniqueness_score
            + speed_score
            - max(avg_latency, 0) / 3600
        )
        rankings.append(
            SourceRanking(
                source_id=source_id,
                source_name=source_names[source_id],
                observation_count=observation_count,
                first_source_count=first_source_count,
                avg_latency_seconds=avg_latency,
                avg_lead_lag_seconds=avg_lead_lag,
                avg_post_cost_directional_return_pct=avg_return,
                hit_rate=hit_rate,
                uniqueness_score=uniqueness_score,
                ranking_score=ranking_score,
            )
        )
    return tuple(
        sorted(
            rankings,
            key=lambda ranking: (
                ranking.ranking_score,
                ranking.avg_post_cost_directional_return_pct,
                ranking.uniqueness_score,
            ),
            reverse=True,
        )
    )


def predictive_power_rows_as_dicts(
    rows: Iterable[PredictivePowerRow],
) -> tuple[dict[str, object], ...]:
    return tuple(row.as_dict() for row in rows)


def predictive_power_rows_to_csv(rows: Iterable[PredictivePowerRow]) -> str:
    dicts = predictive_power_rows_as_dicts(rows)
    if not dicts:
        return ""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=tuple(dicts[0]))
    writer.writeheader()
    writer.writerows(dicts)
    return output.getvalue()


def source_rankings_as_dicts(
    rankings: Iterable[SourceRanking],
) -> tuple[dict[str, object], ...]:
    return tuple(ranking.as_dict() for ranking in rankings)


def _row_for_window(
    *,
    event: ResearchEvent,
    eqnr_prices: tuple[IntradayPricePoint, ...],
    brent_points: tuple[ResearchControlPoint, ...],
    usd_nok_points: tuple[ResearchControlPoint, ...],
    case_first_seen: datetime,
    source_rank_in_case: int,
    window_minutes: int,
    trading_cost_bps: float,
) -> PredictivePowerRow:
    exit_target = event.first_seen_at + timedelta(minutes=window_minutes)
    entry_point = _price_at_or_after(eqnr_prices, event.first_seen_at)
    exit_point = _price_at_or_after(eqnr_prices, exit_target)
    missing_reasons: list[str] = []
    if entry_point is None:
        missing_reasons.append("missing_entry_price")
    if exit_point is None:
        missing_reasons.append("missing_exit_price")

    entry_price = None if entry_point is None else entry_point.mid
    exit_price = None if exit_point is None else exit_point.mid
    eqnr_return_pct = _change_pct(entry_price, exit_price)
    directional_return_pct = _directional_return(event.direction, eqnr_return_pct)
    post_cost_directional_return_pct = _subtract_cost(
        directional_return_pct,
        trading_cost_bps,
    )

    brent_at_entry = _control_value_at_or_before(brent_points, event.first_seen_at)
    brent_at_exit = _control_value_at_or_before(brent_points, exit_target)
    usd_nok_at_entry = _control_value_at_or_before(usd_nok_points, event.first_seen_at)
    usd_nok_at_exit = _control_value_at_or_before(usd_nok_points, exit_target)

    return PredictivePowerRow(
        case_id=event.case_id,
        event_id=event.event_id,
        source_id=event.source_id,
        source_name=event.source_name,
        source_class=event.source_class,
        source_category=event.source_category,
        source_tier=event.source_tier,
        topic_classification=event.topic_classification,
        oil_impact_channel=event.oil_impact_channel,
        direction=event.direction,
        confidence=event.confidence,
        event_timestamp=event.event_timestamp,
        source_timestamp=event.source_timestamp,
        first_seen_at=event.first_seen_at,
        source_latency_seconds=event.source_latency_seconds,
        source_lead_lag_seconds=(event.first_seen_at - case_first_seen).total_seconds(),
        source_rank_in_case=source_rank_in_case,
        window_minutes=window_minutes,
        entry_price_at=None if entry_point is None else entry_point.timestamp,
        exit_price_at=None if exit_point is None else exit_point.timestamp,
        entry_price=entry_price,
        exit_price=exit_price,
        eqnr_return_pct=eqnr_return_pct,
        directional_return_pct=directional_return_pct,
        post_cost_directional_return_pct=post_cost_directional_return_pct,
        brent_at_entry=brent_at_entry,
        brent_at_exit=brent_at_exit,
        brent_change_pct=_change_pct(brent_at_entry, brent_at_exit),
        usd_nok_at_entry=usd_nok_at_entry,
        usd_nok_at_exit=usd_nok_at_exit,
        usd_nok_change_pct=_change_pct(usd_nok_at_entry, usd_nok_at_exit),
        missing_data_reason=";".join(missing_reasons) or None,
    )


def _event_from_row(row: Mapping[str, str]) -> ResearchEvent:
    return ResearchEvent(
        case_id=_required(row, "case_id"),
        event_id=_required(row, "event_id"),
        source_id=_required(row, "source_id"),
        source_name=_required(row, "source_name"),
        source_class=_required(row, "source_class"),
        source_category=_required(row, "source_category"),
        source_tier=_required(row, "source_tier"),
        event_timestamp=_datetime(_required(row, "event_timestamp")),
        source_timestamp=_datetime(_required(row, "source_timestamp")),
        first_seen_at=_datetime(_required(row, "first_seen_at")),
        headline=_required(row, "headline"),
        body=row.get("body", ""),
        topic_classification=_required(row, "topic_classification"),
        equinor_relevance=_float(_required(row, "equinor_relevance")),
        oil_impact_channel=_required(row, "oil_impact_channel"),
        direction=_required(row, "direction"),
        confidence=_float(row.get("confidence", "1")),
    )


def _price_points(csv_text: str) -> tuple[IntradayPricePoint, ...]:
    points = tuple(
        IntradayPricePoint(
            timestamp=_datetime(_required(row, "timestamp")),
            mid=_float(_required(row, "mid")),
            bid=_optional_float(row.get("bid", "")),
            ask=_optional_float(row.get("ask", "")),
        )
        for row in _read_rows(csv_text)
    )
    return tuple(sorted(points, key=lambda point: point.timestamp))


def _control_points(csv_text: str) -> tuple[ResearchControlPoint, ...]:
    points = tuple(
        ResearchControlPoint(
            timestamp=_datetime(_required(row, "timestamp")),
            value=_float(_required(row, "value")),
        )
        for row in _read_rows(csv_text)
    )
    return tuple(sorted(points, key=lambda point: point.timestamp))


def _first_seen_by_case(events: Sequence[ResearchEvent]) -> dict[str, datetime]:
    first_seen: dict[str, datetime] = {}
    for event in events:
        current = first_seen.get(event.case_id)
        if current is None or event.first_seen_at < current:
            first_seen[event.case_id] = event.first_seen_at
    return first_seen


def _rank_by_event(events: Sequence[ResearchEvent]) -> dict[str, int]:
    ranked: dict[str, int] = {}
    events_by_case: dict[str, list[ResearchEvent]] = {}
    for event in events:
        events_by_case.setdefault(event.case_id, []).append(event)
    for case_events in events_by_case.values():
        ordered_events = sorted(case_events, key=_event_key)
        for index, event in enumerate(ordered_events, start=1):
            ranked[event.event_id] = index
    return ranked


def _event_key(event: ResearchEvent) -> tuple[datetime, datetime, str]:
    return (event.first_seen_at, event.source_timestamp, event.event_id)


def _price_at_or_after(
    prices: tuple[IntradayPricePoint, ...],
    timestamp: datetime,
) -> IntradayPricePoint | None:
    for point in prices:
        if point.timestamp >= timestamp:
            return point
    return None


def _control_value_at_or_before(
    points: tuple[ResearchControlPoint, ...],
    timestamp: datetime,
) -> float | None:
    selected = None
    for point in points:
        if point.timestamp > timestamp:
            break
        selected = point
    return None if selected is None else selected.value


def _directional_return(direction: str, eqnr_return_pct: float | None) -> float | None:
    if eqnr_return_pct is None:
        return None
    normalized = direction.lower()
    if normalized in {"short", "bearish", "bearish_equinor"}:
        return -eqnr_return_pct
    return eqnr_return_pct


def _subtract_cost(value: float | None, trading_cost_bps: float) -> float | None:
    if value is None:
        return None
    return value - trading_cost_bps / 100


def _change_pct(start: float | None, end: float | None) -> float | None:
    if start is None or end is None:
        return None
    if start == 0:
        return None
    return ((end - start) / start) * 100


def _avg(values: Iterable[float]) -> float:
    collected = tuple(values)
    if not collected:
        return 0.0
    return sum(collected) / len(collected)


def _read_rows(csv_text: str) -> tuple[dict[str, str], ...]:
    if not csv_text.strip():
        return ()
    reader = csv.DictReader(StringIO(csv_text.strip()))
    return tuple({key: value.strip() for key, value in row.items()} for row in reader)


def _required(row: Mapping[str, str], key: str) -> str:
    value = row.get(key, "")
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid datetime: {value}") from exc


def _float(value: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"invalid float: {value}") from exc


def _optional_float(value: str) -> float | None:
    if not value:
        return None
    return _float(value)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _iso_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _iso(value)
