from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from io import StringIO
from typing import Iterable, Mapping, Sequence

from qualstocks.paper.backtest import (
    BacktestCase,
    ExitBacktestConfig,
    ExitBacktestResult,
    PricePoint,
    run_exit_backtest,
)


class StrEnum(str, Enum):
    pass


class ControlSeriesName(StrEnum):
    BRENT = "brent"
    USD_NOK = "usd_nok"


@dataclass(frozen=True)
class ControlPoint:
    timestamp: datetime
    value: float


@dataclass(frozen=True)
class HistoricalBacktestDataset:
    cases: tuple[BacktestCase, ...]
    brent_points: tuple[ControlPoint, ...] = ()
    usd_nok_points: tuple[ControlPoint, ...] = ()

    def case_ids(self) -> tuple[str, ...]:
        return tuple(case.case_id for case in self.cases)


@dataclass(frozen=True)
class BacktestSummaryRow:
    case_id: str
    norwegian_confirmation_status: str
    anchor: str
    window_minutes: int
    first_official_signal_at: datetime
    first_source_ingested_at: datetime
    norwegian_confirmation_at: datetime | None
    order_entry_at: datetime
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
    brent_at_entry: float | None
    brent_at_exit: float | None
    usd_nok_at_entry: float | None
    usd_nok_at_exit: float | None

    def as_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "norwegian_confirmation_status": self.norwegian_confirmation_status,
            "anchor": self.anchor,
            "window_minutes": self.window_minutes,
            "first_official_signal_at": _iso(self.first_official_signal_at),
            "first_source_ingested_at": _iso(self.first_source_ingested_at),
            "norwegian_confirmation_at": _iso_or_none(self.norwegian_confirmation_at),
            "order_entry_at": _iso(self.order_entry_at),
            "anchor_time": _iso(self.anchor_time),
            "target_exit_at": _iso(self.target_exit_at),
            "actual_exit_at": _iso(self.actual_exit_at),
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "gross_pnl_pct": self.gross_pnl_pct,
            "net_pnl_pct": self.net_pnl_pct,
            "paper_pnl_aum_pct": self.paper_pnl_aum_pct,
            "peak_favorable_excursion_pct": self.peak_favorable_excursion_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "brent_at_entry": self.brent_at_entry,
            "brent_at_exit": self.brent_at_exit,
            "usd_nok_at_entry": self.usd_nok_at_entry,
            "usd_nok_at_exit": self.usd_nok_at_exit,
        }


def load_historical_backtest_dataset(
    *,
    event_cases_csv: str,
    eqnr_prices_csv: str,
    brent_csv: str = "",
    usd_nok_csv: str = "",
) -> HistoricalBacktestDataset:
    case_rows = _read_rows(event_cases_csv)
    price_rows = _read_rows(eqnr_prices_csv)
    prices_by_case = _price_points_by_case(price_rows)
    cases = tuple(_case_from_row(row, prices_by_case) for row in case_rows)
    return HistoricalBacktestDataset(
        cases=cases,
        brent_points=_control_points(brent_csv),
        usd_nok_points=_control_points(usd_nok_csv),
    )


def run_historical_exit_backtest(
    dataset: HistoricalBacktestDataset,
    config: ExitBacktestConfig = ExitBacktestConfig(),
) -> tuple[ExitBacktestResult, ...]:
    return tuple(run_exit_backtest(case, config=config) for case in dataset.cases)


def summarize_exit_backtests(
    dataset: HistoricalBacktestDataset,
    config: ExitBacktestConfig = ExitBacktestConfig(),
) -> tuple[BacktestSummaryRow, ...]:
    rows: list[BacktestSummaryRow] = []
    for result in run_historical_exit_backtest(dataset, config=config):
        for variant in result.variants:
            rows.append(
                BacktestSummaryRow(
                    case_id=result.case_id,
                    norwegian_confirmation_status=result.norwegian_confirmation_status.value,
                    anchor=variant.anchor.value,
                    window_minutes=variant.window_minutes,
                    first_official_signal_at=result.first_official_signal_at,
                    first_source_ingested_at=result.first_source_ingested_at,
                    norwegian_confirmation_at=result.norwegian_confirmation_at,
                    order_entry_at=result.order_entry_at,
                    anchor_time=variant.anchor_time,
                    target_exit_at=variant.target_exit_at,
                    actual_exit_at=variant.actual_exit_at,
                    entry_price=variant.entry_price,
                    exit_price=variant.exit_price,
                    gross_pnl_pct=variant.gross_pnl_pct,
                    net_pnl_pct=variant.net_pnl_pct,
                    paper_pnl_aum_pct=variant.paper_pnl_aum_pct,
                    peak_favorable_excursion_pct=variant.peak_favorable_excursion_pct,
                    max_drawdown_pct=variant.max_drawdown_pct,
                    brent_at_entry=_control_value_at_or_before(
                        dataset.brent_points,
                        result.order_entry_at,
                    ),
                    brent_at_exit=_control_value_at_or_before(
                        dataset.brent_points,
                        variant.actual_exit_at,
                    ),
                    usd_nok_at_entry=_control_value_at_or_before(
                        dataset.usd_nok_points,
                        result.order_entry_at,
                    ),
                    usd_nok_at_exit=_control_value_at_or_before(
                        dataset.usd_nok_points,
                        variant.actual_exit_at,
                    ),
                )
            )
    return tuple(rows)


def summary_rows_as_dicts(rows: Iterable[BacktestSummaryRow]) -> tuple[dict[str, object], ...]:
    return tuple(row.as_dict() for row in rows)


def summary_rows_to_csv(rows: Iterable[BacktestSummaryRow]) -> str:
    dicts = summary_rows_as_dicts(rows)
    if not dicts:
        return ""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=tuple(dicts[0]))
    writer.writeheader()
    writer.writerows(dicts)
    return output.getvalue()


def _read_rows(csv_text: str) -> tuple[dict[str, str], ...]:
    if not csv_text.strip():
        return ()
    reader = csv.DictReader(StringIO(csv_text.strip()))
    return tuple({key: value.strip() for key, value in row.items()} for row in reader)


def _case_from_row(
    row: Mapping[str, str],
    prices_by_case: Mapping[str, tuple[PricePoint, ...]],
) -> BacktestCase:
    case_id = _required(row, "case_id")
    price_points = prices_by_case.get(case_id, ())
    if not price_points:
        raise ValueError(f"missing EQNR price points for case_id: {case_id}")
    return BacktestCase(
        case_id=case_id,
        first_official_signal_at=_datetime(_required(row, "first_official_signal_at")),
        first_source_ingested_at=_datetime(_required(row, "first_source_ingested_at")),
        norwegian_confirmation_at=_optional_datetime(row.get("norwegian_confirmation_at", "")),
        order_entry_at=_datetime(_required(row, "order_entry_at")),
        price_points=price_points,
        aum_pct=_int(row.get("aum_pct", ""), default=100),
        direction=row.get("direction", "long") or "long",
    )


def _price_points_by_case(
    rows: Sequence[Mapping[str, str]],
) -> dict[str, tuple[PricePoint, ...]]:
    points: dict[str, list[PricePoint]] = {}
    for row in rows:
        case_id = _required(row, "case_id")
        points.setdefault(case_id, []).append(
            PricePoint(
                timestamp=_datetime(_required(row, "timestamp")),
                mid=_float(_required(row, "mid")),
                bid=_optional_float(row.get("bid", "")),
                ask=_optional_float(row.get("ask", "")),
            )
        )
    return {
        case_id: tuple(sorted(case_points, key=lambda point: point.timestamp))
        for case_id, case_points in points.items()
    }


def _control_points(csv_text: str) -> tuple[ControlPoint, ...]:
    points = tuple(
        ControlPoint(
            timestamp=_datetime(_required(row, "timestamp")),
            value=_float(_required(row, "value")),
        )
        for row in _read_rows(csv_text)
    )
    return tuple(sorted(points, key=lambda point: point.timestamp))


def _control_value_at_or_before(
    points: tuple[ControlPoint, ...],
    timestamp: datetime,
) -> float | None:
    selected = None
    for point in points:
        if point.timestamp > timestamp:
            break
        selected = point
    return None if selected is None else selected.value


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


def _optional_datetime(value: str) -> datetime | None:
    if not value:
        return None
    return _datetime(value)


def _float(value: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"invalid float: {value}") from exc


def _optional_float(value: str) -> float | None:
    if not value:
        return None
    return _float(value)


def _int(value: str, *, default: int) -> int:
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"invalid integer: {value}") from exc


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _iso_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _iso(value)
