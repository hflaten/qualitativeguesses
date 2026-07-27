from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class StrEnum(str, Enum):
    pass


class ExitAnchor(StrEnum):
    NORWEGIAN_CONFIRMATION = "norwegian_confirmation"
    FIRST_SEEN_SIGNAL = "first_seen_signal"
    ORDER_ENTRY = "order_entry"


class NorwegianConfirmationStatus(StrEnum):
    AVAILABLE = "available"
    LATE = "late"
    MISSING = "missing"


@dataclass(frozen=True)
class PricePoint:
    timestamp: datetime
    mid: float
    bid: float | None = None
    ask: float | None = None

    @property
    def spread_bps(self) -> float:
        if self.bid is None or self.ask is None or self.mid <= 0:
            return 0.0
        return ((self.ask - self.bid) / self.mid) * 10_000


@dataclass(frozen=True)
class BacktestCase:
    case_id: str
    first_official_signal_at: datetime
    first_source_ingested_at: datetime
    order_entry_at: datetime
    price_points: tuple[PricePoint, ...]
    norwegian_confirmation_at: datetime | None = None
    aum_pct: int = 100
    direction: str = "long"


@dataclass(frozen=True)
class ExitBacktestConfig:
    exit_windows_minutes: tuple[int, ...] = (30, 40, 50)
    slippage_bps: float = 5.0
    fallback_confirmation_late_minutes: int = 90

    def __post_init__(self) -> None:
        if not self.exit_windows_minutes:
            raise ValueError("at least one exit window is required")
        if any(window <= 0 for window in self.exit_windows_minutes):
            raise ValueError("exit windows must be positive")
        if self.slippage_bps < 0:
            raise ValueError("slippage_bps cannot be negative")
        if self.fallback_confirmation_late_minutes <= 0:
            raise ValueError("fallback_confirmation_late_minutes must be positive")


@dataclass(frozen=True)
class ExitVariantResult:
    case_id: str
    anchor: ExitAnchor
    window_minutes: int
    anchor_time: datetime
    target_exit_at: datetime
    actual_exit_at: datetime
    entry_price: float
    exit_price: float
    gross_pnl_pct: float
    net_pnl_pct: float
    paper_pnl_aum_pct: float
    peak_favorable_excursion_pct: float
    max_drawdown_pct: float
    slippage_bps: float
    spread_bps: float


@dataclass(frozen=True)
class ExitBacktestResult:
    case_id: str
    first_official_signal_at: datetime
    first_source_ingested_at: datetime
    norwegian_confirmation_at: datetime | None
    order_entry_at: datetime
    norwegian_confirmation_status: NorwegianConfirmationStatus
    variants: tuple[ExitVariantResult, ...]

    def variants_for_anchor(self, anchor: ExitAnchor) -> tuple[ExitVariantResult, ...]:
        return tuple(variant for variant in self.variants if variant.anchor == anchor)


def run_exit_backtest(
    case: BacktestCase,
    config: ExitBacktestConfig = ExitBacktestConfig(),
) -> ExitBacktestResult:
    if not case.price_points:
        raise ValueError("price_points must be non-empty")
    price_points = tuple(sorted(case.price_points, key=lambda point: point.timestamp))
    entry_point = _point_at_or_after(price_points, case.order_entry_at)
    entry_price = _execution_price(entry_point, side="buy", slippage_bps=config.slippage_bps)
    variants: list[ExitVariantResult] = []

    for anchor, anchor_time in _available_anchors(case):
        for window in config.exit_windows_minutes:
            target_exit_at = anchor_time + timedelta(minutes=window)
            exit_point = _point_at_or_after(price_points, target_exit_at)
            exit_price = _execution_price(
                exit_point,
                side="sell",
                slippage_bps=config.slippage_bps,
            )
            path = _points_between(price_points, case.order_entry_at, exit_point.timestamp)
            gross_pnl_pct = _pnl_pct(entry_price, exit_price, direction=case.direction)
            net_pnl_pct = gross_pnl_pct - _round_bps(config.slippage_bps * 2)
            variants.append(
                ExitVariantResult(
                    case_id=case.case_id,
                    anchor=anchor,
                    window_minutes=window,
                    anchor_time=anchor_time,
                    target_exit_at=target_exit_at,
                    actual_exit_at=exit_point.timestamp,
                    entry_price=round(entry_price, 6),
                    exit_price=round(exit_price, 6),
                    gross_pnl_pct=round(gross_pnl_pct, 6),
                    net_pnl_pct=round(net_pnl_pct, 6),
                    paper_pnl_aum_pct=round(net_pnl_pct * (case.aum_pct / 100), 6),
                    peak_favorable_excursion_pct=round(
                        _peak_favorable_excursion(entry_price, path, case.direction),
                        6,
                    ),
                    max_drawdown_pct=round(_max_drawdown(entry_price, path, case.direction), 6),
                    slippage_bps=config.slippage_bps,
                    spread_bps=round(exit_point.spread_bps, 6),
                )
            )

    return ExitBacktestResult(
        case_id=case.case_id,
        first_official_signal_at=case.first_official_signal_at,
        first_source_ingested_at=case.first_source_ingested_at,
        norwegian_confirmation_at=case.norwegian_confirmation_at,
        order_entry_at=case.order_entry_at,
        norwegian_confirmation_status=_norwegian_status(case, config),
        variants=tuple(variants),
    )


def _available_anchors(case: BacktestCase) -> tuple[tuple[ExitAnchor, datetime], ...]:
    anchors: list[tuple[ExitAnchor, datetime]] = [
        (ExitAnchor.FIRST_SEEN_SIGNAL, case.first_source_ingested_at),
        (ExitAnchor.ORDER_ENTRY, case.order_entry_at),
    ]
    if case.norwegian_confirmation_at is not None:
        anchors.insert(0, (ExitAnchor.NORWEGIAN_CONFIRMATION, case.norwegian_confirmation_at))
    return tuple(anchors)


def _norwegian_status(
    case: BacktestCase,
    config: ExitBacktestConfig,
) -> NorwegianConfirmationStatus:
    if case.norwegian_confirmation_at is None:
        return NorwegianConfirmationStatus.MISSING
    late_after = case.order_entry_at + timedelta(minutes=config.fallback_confirmation_late_minutes)
    if case.norwegian_confirmation_at > late_after:
        return NorwegianConfirmationStatus.LATE
    return NorwegianConfirmationStatus.AVAILABLE


def _point_at_or_after(points: tuple[PricePoint, ...], timestamp: datetime) -> PricePoint:
    for point in points:
        if point.timestamp >= timestamp:
            return point
    return points[-1]


def _points_between(
    points: tuple[PricePoint, ...],
    start: datetime,
    end: datetime,
) -> tuple[PricePoint, ...]:
    selected = tuple(point for point in points if start <= point.timestamp <= end)
    if selected:
        return selected
    return (_point_at_or_after(points, start), _point_at_or_after(points, end))


def _execution_price(point: PricePoint, *, side: str, slippage_bps: float) -> float:
    base = point.ask if side == "buy" and point.ask is not None else point.mid
    base = point.bid if side == "sell" and point.bid is not None else base
    sign = 1 if side == "buy" else -1
    return base * (1 + sign * (slippage_bps / 10_000))


def _pnl_pct(entry_price: float, exit_price: float, *, direction: str) -> float:
    if entry_price <= 0:
        raise ValueError("entry price must be positive")
    change = (exit_price - entry_price) / entry_price
    if direction == "short":
        change = -change
    return change * 100


def _peak_favorable_excursion(
    entry_price: float,
    path: tuple[PricePoint, ...],
    direction: str,
) -> float:
    if direction == "short":
        best = min(point.mid for point in path)
        return ((entry_price - best) / entry_price) * 100
    best = max(point.mid for point in path)
    return ((best - entry_price) / entry_price) * 100


def _max_drawdown(entry_price: float, path: tuple[PricePoint, ...], direction: str) -> float:
    if direction == "short":
        worst = max(point.mid for point in path)
        return ((entry_price - worst) / entry_price) * 100
    worst = min(point.mid for point in path)
    return ((worst - entry_price) / entry_price) * 100


def _round_bps(value: float) -> float:
    return value / 100
