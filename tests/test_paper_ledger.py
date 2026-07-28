from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from qualstocks.paper import (
    MarketQuote,
    PaperLedger,
    PaperLedgerConfig,
    PaperOrderStatus,
    QuoteFreshness,
)
from qualstocks.strategy import PaperOrderIntent, PaperOrderSide


class PaperLedgerTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc)
        self.ledger = PaperLedger(
            PaperLedgerConfig(
                initial_cash=Decimal("100000"),
                fees_bps=Decimal("1"),
                slippage_bps=Decimal("0"),
                quote_stale_after_seconds=60,
            )
        )

    def test_buy_fill_creates_position_and_reduces_cash(self):
        order = self.ledger.submit_order(self._intent(PaperOrderSide.BUY, 50), now=self.now)
        self.ledger.approve_order(order.id, now=self.now)

        fill = self.ledger.fill_order(order.id, self._quote(Decimal("300")), now=self.now)
        position = self.ledger.position("EQNR.OL")

        self.assertEqual(self.ledger.orders[0].status, PaperOrderStatus.FILLED)
        self.assertEqual(fill.notional, Decimal("50000.0001"))
        self.assertEqual(fill.fees, Decimal("5.0000"))
        self.assertEqual(position.quantity, Decimal("166.666667"))
        self.assertEqual(position.average_entry_price, Decimal("300.0000"))
        self.assertEqual(self.ledger.cash, Decimal("49994.9999"))

    def test_partial_fill_marks_order_and_scales_quantity(self):
        order = self.ledger.submit_order(self._intent(PaperOrderSide.BUY, 50), now=self.now)

        fill = self.ledger.fill_order(
            order.id,
            self._quote(Decimal("250")),
            fill_ratio=Decimal("0.5"),
            now=self.now,
        )

        self.assertEqual(self.ledger.orders[0].status, PaperOrderStatus.PARTIALLY_FILLED)
        self.assertEqual(fill.notional, Decimal("25000.0000"))
        self.assertEqual(self.ledger.position("EQNR.OL").quantity, Decimal("100.000000"))

    def test_rejected_order_cannot_be_filled(self):
        order = self.ledger.submit_order(self._intent(PaperOrderSide.BUY, 50), now=self.now)
        self.ledger.reject_order(order.id, reason="risk rejected", now=self.now)

        with self.assertRaises(ValueError):
            self.ledger.fill_order(order.id, self._quote(Decimal("300")), now=self.now)

    def test_sell_fill_realizes_pnl_and_reduces_position(self):
        buy = self.ledger.submit_order(self._intent(PaperOrderSide.BUY, 50), now=self.now)
        self.ledger.fill_order(buy.id, self._quote(Decimal("300")), now=self.now)
        sell = self.ledger.submit_order(
            self._intent(PaperOrderSide.SELL, 50),
            now=self.now + timedelta(minutes=5),
        )

        self.ledger.fill_order(
            sell.id,
            self._quote(Decimal("330")),
            now=self.now + timedelta(minutes=5),
        )
        position = self.ledger.position("EQNR.OL")

        self.assertEqual(position.quantity, Decimal("83.333333"))
        self.assertEqual(position.realized_pnl, Decimal("2497.2500"))

    def test_bid_ask_quotes_drive_execution_price_when_available(self):
        buy = self.ledger.submit_order(self._intent(PaperOrderSide.BUY, 50), now=self.now)

        buy_fill = self.ledger.fill_order(
            buy.id,
            self._quote(Decimal("300"), bid=Decimal("299.90"), ask=Decimal("300.10")),
            now=self.now,
        )
        sell = self.ledger.submit_order(self._intent(PaperOrderSide.SELL, 50), now=self.now)
        sell_fill = self.ledger.fill_order(
            sell.id,
            self._quote(Decimal("301"), bid=Decimal("300.90"), ask=Decimal("301.10")),
            now=self.now,
        )

        self.assertEqual(buy_fill.fill_price, Decimal("300.1000"))
        self.assertEqual(sell_fill.fill_price, Decimal("300.9000"))

    def test_full_sell_closes_position(self):
        buy = self.ledger.submit_order(self._intent(PaperOrderSide.BUY, 50), now=self.now)
        self.ledger.fill_order(buy.id, self._quote(Decimal("300")), now=self.now)
        sell = self.ledger.submit_order(self._intent(PaperOrderSide.SELL, 100), now=self.now)

        self.ledger.fill_order(sell.id, self._quote(Decimal("300")), now=self.now)

        self.assertFalse(self.ledger.position("EQNR.OL").is_open)

    def test_mark_to_market_returns_live_pnl_fields(self):
        buy = self.ledger.submit_order(self._intent(PaperOrderSide.BUY, 50), now=self.now)
        self.ledger.fill_order(buy.id, self._quote(Decimal("300")), now=self.now)

        valuation = self.ledger.valuation(
            quote=self._quote(Decimal("330"), observed_at=self.now + timedelta(seconds=30)),
            as_of=self.now + timedelta(seconds=45),
        )

        self.assertEqual(valuation.quote_freshness, QuoteFreshness.FRESH)
        self.assertEqual(valuation.last_price, Decimal("330.0000"))
        self.assertEqual(valuation.market_value, Decimal("55000.0001"))
        self.assertEqual(valuation.unrealized_pnl, Decimal("5000.0000"))
        self.assertEqual(valuation.unrealized_pnl_pct, Decimal("10.0000"))
        self.assertEqual(valuation.total_pnl, Decimal("4995.0000"))

    def test_stale_quote_is_flagged_for_dashboard(self):
        buy = self.ledger.submit_order(self._intent(PaperOrderSide.BUY, 50), now=self.now)
        self.ledger.fill_order(buy.id, self._quote(Decimal("300")), now=self.now)

        valuation = self.ledger.valuation(
            quote=self._quote(Decimal("330"), observed_at=self.now),
            as_of=self.now + timedelta(seconds=61),
        )

        self.assertEqual(valuation.quote_freshness, QuoteFreshness.STALE)

    def test_missing_quote_does_not_invent_unrealized_pnl(self):
        valuation = self.ledger.valuation(quote=None, as_of=self.now)

        self.assertEqual(valuation.quote_freshness, QuoteFreshness.MISSING)
        self.assertIsNone(valuation.last_price)
        self.assertEqual(valuation.unrealized_pnl, Decimal("0.0000"))

    def _intent(self, side: PaperOrderSide, aum_pct: int) -> PaperOrderIntent:
        return PaperOrderIntent(
            side=side,
            instrument="EQNR.OL",
            aum_pct=aum_pct,
            reason="test order",
            source_event_id="event-1",
        )

    def _quote(
        self,
        last_price: Decimal,
        *,
        bid: Decimal | None = None,
        ask: Decimal | None = None,
        observed_at: datetime | None = None,
    ) -> MarketQuote:
        return MarketQuote(
            instrument="EQNR.OL",
            last_price=last_price,
            bid=bid,
            ask=ask,
            currency="NOK",
            source="test",
            observed_at=observed_at or self.now,
        )


if __name__ == "__main__":
    unittest.main()
