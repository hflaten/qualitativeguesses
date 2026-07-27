from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from qualstocks.paper import (
    BacktestCase,
    ExitAnchor,
    ExitBacktestConfig,
    NorwegianConfirmationStatus,
    PricePoint,
    run_exit_backtest,
)


class ExitBacktestTest(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)
        self.prices = tuple(
            PricePoint(
                timestamp=self.start + timedelta(minutes=minute),
                mid=300 + minute * 0.1,
                bid=299.95 + minute * 0.1,
                ask=300.05 + minute * 0.1,
            )
            for minute in range(0, 121, 5)
        )

    def test_records_key_event_times(self):
        case = self._case(norwegian_confirmation_at=self.start + timedelta(minutes=14))

        result = run_exit_backtest(case)

        self.assertEqual(result.first_official_signal_at, self.start)
        self.assertEqual(result.first_source_ingested_at, self.start + timedelta(minutes=1))
        self.assertEqual(result.norwegian_confirmation_at, self.start + timedelta(minutes=14))
        self.assertEqual(result.order_entry_at, self.start + timedelta(minutes=2))

    def test_generates_30_40_50_exits_from_norwegian_anchor(self):
        confirmation_at = self.start + timedelta(minutes=14)
        result = run_exit_backtest(self._case(norwegian_confirmation_at=confirmation_at))
        variants = result.variants_for_anchor(ExitAnchor.NORWEGIAN_CONFIRMATION)

        self.assertEqual([variant.window_minutes for variant in variants], [30, 40, 50])
        self.assertEqual(
            [variant.target_exit_at for variant in variants],
            [
                confirmation_at + timedelta(minutes=30),
                confirmation_at + timedelta(minutes=40),
                confirmation_at + timedelta(minutes=50),
            ],
        )

    def test_compares_norwegian_anchor_against_first_seen_and_order_entry(self):
        result = run_exit_backtest(
            self._case(norwegian_confirmation_at=self.start + timedelta(minutes=14))
        )

        self.assertEqual(len(result.variants_for_anchor(ExitAnchor.NORWEGIAN_CONFIRMATION)), 3)
        self.assertEqual(len(result.variants_for_anchor(ExitAnchor.FIRST_SEEN_SIGNAL)), 3)
        self.assertEqual(len(result.variants_for_anchor(ExitAnchor.ORDER_ENTRY)), 3)

    def test_reports_execution_assumptions_and_net_pnl(self):
        result = run_exit_backtest(
            self._case(norwegian_confirmation_at=self.start + timedelta(minutes=14)),
            ExitBacktestConfig(slippage_bps=10),
        )
        variant = result.variants_for_anchor(ExitAnchor.ORDER_ENTRY)[0]

        self.assertEqual(variant.slippage_bps, 10)
        self.assertGreater(variant.spread_bps, 0)
        self.assertGreater(variant.peak_favorable_excursion_pct, 0)
        self.assertLessEqual(variant.max_drawdown_pct, 0)
        self.assertLess(variant.net_pnl_pct, variant.gross_pnl_pct)
        self.assertAlmostEqual(variant.paper_pnl_aum_pct, variant.net_pnl_pct)

    def test_missing_norwegian_confirmation_is_identified(self):
        result = run_exit_backtest(self._case(norwegian_confirmation_at=None))

        self.assertEqual(
            result.norwegian_confirmation_status,
            NorwegianConfirmationStatus.MISSING,
        )
        self.assertEqual(result.variants_for_anchor(ExitAnchor.NORWEGIAN_CONFIRMATION), ())
        self.assertEqual(len(result.variants), 6)

    def test_late_norwegian_confirmation_is_identified(self):
        result = run_exit_backtest(
            self._case(norwegian_confirmation_at=self.start + timedelta(minutes=100)),
            ExitBacktestConfig(fallback_confirmation_late_minutes=90),
        )

        self.assertEqual(result.norwegian_confirmation_status, NorwegianConfirmationStatus.LATE)

    def test_short_direction_reverses_pnl_math(self):
        result = run_exit_backtest(
            self._case(
                norwegian_confirmation_at=self.start + timedelta(minutes=14),
                direction="short",
            )
        )
        variant = result.variants_for_anchor(ExitAnchor.ORDER_ENTRY)[0]

        self.assertLess(variant.gross_pnl_pct, 0)
        self.assertGreaterEqual(variant.peak_favorable_excursion_pct, 0)
        self.assertLess(variant.max_drawdown_pct, 0)

    def test_requires_price_points(self):
        case = BacktestCase(
            case_id="empty",
            first_official_signal_at=self.start,
            first_source_ingested_at=self.start,
            norwegian_confirmation_at=None,
            order_entry_at=self.start,
            price_points=(),
        )

        with self.assertRaises(ValueError):
            run_exit_backtest(case)

    def _case(
        self,
        *,
        norwegian_confirmation_at,
        direction: str = "long",
    ) -> BacktestCase:
        return BacktestCase(
            case_id="case-1",
            first_official_signal_at=self.start,
            first_source_ingested_at=self.start + timedelta(minutes=1),
            norwegian_confirmation_at=norwegian_confirmation_at,
            order_entry_at=self.start + timedelta(minutes=2),
            price_points=self.prices,
            direction=direction,
        )


if __name__ == "__main__":
    unittest.main()
