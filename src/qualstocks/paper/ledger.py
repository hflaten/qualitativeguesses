from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from uuid import uuid4

from qualstocks.strategy import PaperOrderIntent, PaperOrderSide


class StrEnum(str, Enum):
    pass


class PaperOrderStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"


class QuoteFreshness(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    MISSING = "missing"


@dataclass(frozen=True)
class MarketQuote:
    instrument: str
    last_price: Decimal
    currency: str
    source: str
    observed_at: datetime
    bid: Decimal | None = None
    ask: Decimal | None = None

    def __post_init__(self) -> None:
        if self.last_price <= 0:
            raise ValueError("last_price must be positive")


@dataclass(frozen=True)
class PaperLedgerConfig:
    initial_cash: Decimal = Decimal("100000")
    fees_bps: Decimal = Decimal("1")
    slippage_bps: Decimal = Decimal("5")
    quote_stale_after_seconds: int = 60

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if self.fees_bps < 0:
            raise ValueError("fees_bps cannot be negative")
        if self.slippage_bps < 0:
            raise ValueError("slippage_bps cannot be negative")
        if self.quote_stale_after_seconds <= 0:
            raise ValueError("quote_stale_after_seconds must be positive")


@dataclass(frozen=True)
class PaperOrder:
    id: str
    side: PaperOrderSide
    instrument: str
    aum_pct: int
    status: PaperOrderStatus
    reason: str
    source_event_id: str | None
    created_at: datetime
    updated_at: datetime
    reject_reason: str | None = None


@dataclass(frozen=True)
class PaperFill:
    id: str
    order_id: str
    instrument: str
    side: PaperOrderSide
    fill_price: Decimal
    quantity: Decimal
    notional: Decimal
    fees: Decimal
    filled_at: datetime


@dataclass(frozen=True)
class PaperPosition:
    instrument: str
    quantity: Decimal = Decimal("0")
    average_entry_price: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")

    @property
    def is_open(self) -> bool:
        return self.quantity > 0


@dataclass(frozen=True)
class PortfolioValuation:
    cash: Decimal
    starting_aum: Decimal
    equity: Decimal
    instrument: str | None
    quantity: Decimal
    average_entry_price: Decimal
    last_price: Decimal | None
    market_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal
    total_pnl: Decimal
    total_pnl_pct: Decimal
    quote_freshness: QuoteFreshness
    quote_source: str | None
    quote_observed_at: datetime | None


class PaperLedger:
    def __init__(self, config: PaperLedgerConfig = PaperLedgerConfig()) -> None:
        self.config = config
        self.cash = config.initial_cash
        self.orders: list[PaperOrder] = []
        self.fills: list[PaperFill] = []
        self.positions: dict[str, PaperPosition] = {}

    def submit_order(
        self,
        intent: PaperOrderIntent,
        *,
        now: datetime | None = None,
    ) -> PaperOrder:
        timestamp = now or _now()
        order = PaperOrder(
            id=str(uuid4()),
            side=intent.side,
            instrument=intent.instrument,
            aum_pct=intent.aum_pct,
            status=PaperOrderStatus.PENDING,
            reason=intent.reason,
            source_event_id=intent.source_event_id,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.orders.append(order)
        return order

    def approve_order(self, order_id: str, *, now: datetime | None = None) -> PaperOrder:
        return self._replace_order(
            order_id,
            status=PaperOrderStatus.APPROVED,
            updated_at=now or _now(),
            reject_reason=None,
        )

    def reject_order(
        self,
        order_id: str,
        *,
        reason: str,
        now: datetime | None = None,
    ) -> PaperOrder:
        return self._replace_order(
            order_id,
            status=PaperOrderStatus.REJECTED,
            updated_at=now or _now(),
            reject_reason=reason,
        )

    def fill_order(
        self,
        order_id: str,
        quote: MarketQuote,
        *,
        fill_ratio: Decimal = Decimal("1"),
        now: datetime | None = None,
    ) -> PaperFill:
        if fill_ratio <= 0 or fill_ratio > 1:
            raise ValueError("fill_ratio must be between 0 and 1")
        order = self._order(order_id)
        if order.status not in {PaperOrderStatus.PENDING, PaperOrderStatus.APPROVED}:
            raise ValueError("only pending or approved orders can be filled")
        if quote.instrument != order.instrument:
            raise ValueError("quote instrument does not match order instrument")

        timestamp = now or _now()
        fill_price = _execution_price(order.side, quote, self.config.slippage_bps)
        quantity = self._fill_quantity(order, fill_price, fill_ratio)
        if quantity <= 0:
            raise ValueError("fill quantity must be positive")
        notional = _money(quantity * fill_price)
        fees = _money(notional * self.config.fees_bps / Decimal("10000"))
        fill = PaperFill(
            id=str(uuid4()),
            order_id=order.id,
            instrument=order.instrument,
            side=order.side,
            fill_price=fill_price,
            quantity=quantity,
            notional=notional,
            fees=fees,
            filled_at=timestamp,
        )
        self._apply_fill(fill)
        self.fills.append(fill)
        self._replace_order(
            order.id,
            status=(
                PaperOrderStatus.FILLED
                if fill_ratio == Decimal("1")
                else PaperOrderStatus.PARTIALLY_FILLED
            ),
            updated_at=timestamp,
        )
        return fill

    def position(self, instrument: str) -> PaperPosition:
        return self.positions.get(instrument, PaperPosition(instrument=instrument))

    def valuation(
        self,
        *,
        instrument: str = "EQNR.OL",
        quote: MarketQuote | None = None,
        as_of: datetime | None = None,
    ) -> PortfolioValuation:
        timestamp = as_of or _now()
        position = self.position(instrument)
        quote_freshness = self._quote_freshness(quote, timestamp)
        last_price = quote.last_price if quote is not None else None
        market_value = _money(position.quantity * (last_price or Decimal("0")))
        unrealized_pnl = _money(
            (last_price - position.average_entry_price) * position.quantity
            if last_price is not None and position.is_open
            else Decimal("0")
        )
        unrealized_pnl_pct = _pct(unrealized_pnl, position.average_entry_price * position.quantity)
        equity = _money(self.cash + market_value)
        total_pnl = _money(equity - self.config.initial_cash)
        return PortfolioValuation(
            cash=_money(self.cash),
            starting_aum=_money(self.config.initial_cash),
            equity=equity,
            instrument=instrument if position.is_open else None,
            quantity=_shares(position.quantity),
            average_entry_price=_money(position.average_entry_price),
            last_price=_money(last_price) if last_price is not None else None,
            market_value=market_value,
            realized_pnl=_money(position.realized_pnl),
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct,
            total_pnl=total_pnl,
            total_pnl_pct=_pct(total_pnl, self.config.initial_cash),
            quote_freshness=quote_freshness,
            quote_source=quote.source if quote is not None else None,
            quote_observed_at=quote.observed_at if quote is not None else None,
        )

    def _fill_quantity(
        self,
        order: PaperOrder,
        fill_price: Decimal,
        fill_ratio: Decimal,
    ) -> Decimal:
        if order.side == PaperOrderSide.BUY:
            notional = self.config.initial_cash * Decimal(order.aum_pct) / Decimal("100")
            notional = min(notional * fill_ratio, self.cash)
            return _shares(notional / fill_price)

        position = self.position(order.instrument)
        target_quantity = position.quantity * Decimal(order.aum_pct) / Decimal("100")
        return _shares(min(position.quantity, target_quantity * fill_ratio))

    def _apply_fill(self, fill: PaperFill) -> None:
        position = self.position(fill.instrument)
        if fill.side == PaperOrderSide.BUY:
            self.cash = _money(self.cash - fill.notional - fill.fees)
            new_quantity = position.quantity + fill.quantity
            total_cost = (
                position.quantity * position.average_entry_price
                + fill.quantity * fill.fill_price
            )
            self.positions[fill.instrument] = PaperPosition(
                instrument=fill.instrument,
                quantity=_shares(new_quantity),
                average_entry_price=_money(total_cost / new_quantity),
                realized_pnl=position.realized_pnl,
            )
            return

        if fill.quantity > position.quantity:
            raise ValueError("cannot sell more than the open paper position")
        self.cash = _money(self.cash + fill.notional - fill.fees)
        realized = _money(
            position.realized_pnl
            + (fill.fill_price - position.average_entry_price) * fill.quantity
            - fill.fees
        )
        remaining_quantity = _shares(position.quantity - fill.quantity)
        self.positions[fill.instrument] = PaperPosition(
            instrument=fill.instrument,
            quantity=remaining_quantity,
            average_entry_price=(
                position.average_entry_price if remaining_quantity > 0 else Decimal("0")
            ),
            realized_pnl=realized,
        )

    def _quote_freshness(
        self,
        quote: MarketQuote | None,
        as_of: datetime,
    ) -> QuoteFreshness:
        if quote is None:
            return QuoteFreshness.MISSING
        stale_after = timedelta(seconds=self.config.quote_stale_after_seconds)
        if quote.observed_at + stale_after < as_of:
            return QuoteFreshness.STALE
        return QuoteFreshness.FRESH

    def _order(self, order_id: str) -> PaperOrder:
        for order in self.orders:
            if order.id == order_id:
                return order
        raise KeyError(f"unknown order_id: {order_id}")

    def _replace_order(self, order_id: str, **changes: object) -> PaperOrder:
        for index, order in enumerate(self.orders):
            if order.id == order_id:
                updated = replace(order, **changes)
                self.orders[index] = updated
                return updated
        raise KeyError(f"unknown order_id: {order_id}")


def _execution_price(
    side: PaperOrderSide,
    quote: MarketQuote,
    slippage_bps: Decimal,
) -> Decimal:
    base = quote.ask if side == PaperOrderSide.BUY and quote.ask is not None else quote.last_price
    base = quote.bid if side == PaperOrderSide.SELL and quote.bid is not None else base
    sign = Decimal("1") if side == PaperOrderSide.BUY else Decimal("-1")
    return _money(base * (Decimal("1") + sign * slippage_bps / Decimal("10000")))


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == 0:
        return Decimal("0.0000")
    return (numerator / denominator * Decimal("100")).quantize(
        Decimal("0.0001"),
        rounding=ROUND_HALF_UP,
    )


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _shares(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _now() -> datetime:
    return datetime.now(timezone.utc)
