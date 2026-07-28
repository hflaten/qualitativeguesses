from __future__ import annotations

import unittest

from qualstocks.paper import (
    ExitAnchor,
    NorwegianConfirmationStatus,
    load_historical_backtest_dataset,
    summarize_exit_backtests,
    summary_rows_as_dicts,
    summary_rows_to_csv,
)


EVENT_CASES_CSV = (
    "case_id,first_official_signal_at,first_source_ingested_at,"
    "norwegian_confirmation_at,order_entry_at,aum_pct,direction\n"
    """
case-1,2026-07-27T12:00:00Z,2026-07-27T12:01:00Z,2026-07-27T12:14:00Z,2026-07-27T12:02:00Z,50,long
case-2,2026-07-27T13:00:00Z,2026-07-27T13:01:00Z,,2026-07-27T13:03:00Z,25,long
case-3,2026-07-27T14:00:00Z,2026-07-27T14:01:00Z,2026-07-27T15:45:00Z,2026-07-27T14:03:00Z,25,long
"""
)


EQNR_PRICES_CSV = """case_id,timestamp,mid,bid,ask
case-1,2026-07-27T12:00:00Z,300.0,299.95,300.05
case-1,2026-07-27T12:05:00Z,301.0,300.95,301.05
case-1,2026-07-27T12:45:00Z,306.0,305.95,306.05
case-1,2026-07-27T12:55:00Z,307.0,306.95,307.05
case-1,2026-07-27T13:05:00Z,308.0,307.95,308.05
case-2,2026-07-27T13:00:00Z,310.0,309.95,310.05
case-2,2026-07-27T13:05:00Z,311.0,310.95,311.05
case-2,2026-07-27T13:35:00Z,312.0,311.95,312.05
case-2,2026-07-27T13:45:00Z,311.5,311.45,311.55
case-2,2026-07-27T13:55:00Z,313.0,312.95,313.05
case-3,2026-07-27T14:00:00Z,315.0,314.95,315.05
case-3,2026-07-27T14:05:00Z,316.0,315.95,316.05
case-3,2026-07-27T14:35:00Z,317.0,316.95,317.05
case-3,2026-07-27T14:45:00Z,317.5,317.45,317.55
case-3,2026-07-27T14:55:00Z,318.0,317.95,318.05
case-3,2026-07-27T16:15:00Z,319.0,318.95,319.05
case-3,2026-07-27T16:25:00Z,319.5,319.45,319.55
case-3,2026-07-27T16:35:00Z,320.0,319.95,320.05
"""


BRENT_CSV = """timestamp,value
2026-07-27T12:00:00Z,88.5
2026-07-27T12:45:00Z,89.2
2026-07-27T13:05:00Z,89.7
"""


USD_NOK_CSV = """timestamp,value
2026-07-27T12:00:00Z,10.55
2026-07-27T12:45:00Z,10.61
2026-07-27T13:05:00Z,10.59
"""


class BacktestDatasetTest(unittest.TestCase):
    def test_loads_event_cases_prices_and_control_series(self):
        dataset = load_historical_backtest_dataset(
            event_cases_csv=EVENT_CASES_CSV,
            eqnr_prices_csv=EQNR_PRICES_CSV,
            brent_csv=BRENT_CSV,
            usd_nok_csv=USD_NOK_CSV,
        )

        self.assertEqual(dataset.case_ids(), ("case-1", "case-2", "case-3"))
        self.assertEqual(len(dataset.cases[0].price_points), 5)
        self.assertEqual(dataset.cases[0].aum_pct, 50)
        self.assertIsNone(dataset.cases[1].norwegian_confirmation_at)
        self.assertEqual(dataset.brent_points[0].value, 88.5)
        self.assertEqual(dataset.usd_nok_points[0].value, 10.55)

    def test_summary_rows_include_all_anchor_variants_and_controls(self):
        dataset = load_historical_backtest_dataset(
            event_cases_csv=EVENT_CASES_CSV,
            eqnr_prices_csv=EQNR_PRICES_CSV,
            brent_csv=BRENT_CSV,
            usd_nok_csv=USD_NOK_CSV,
        )

        rows = summarize_exit_backtests(dataset)

        self.assertEqual(len(rows), 24)
        first = rows[0]
        self.assertEqual(first.case_id, "case-1")
        self.assertEqual(first.anchor, ExitAnchor.NORWEGIAN_CONFIRMATION.value)
        self.assertEqual(first.norwegian_confirmation_status, "available")
        self.assertEqual(first.brent_at_entry, 88.5)
        self.assertEqual(first.brent_at_exit, 89.2)
        self.assertEqual(first.usd_nok_at_entry, 10.55)
        self.assertEqual(first.usd_nok_at_exit, 10.61)
        self.assertLess(first.paper_pnl_aum_pct, first.net_pnl_pct)

    def test_missing_norwegian_confirmation_is_flagged_in_summary(self):
        dataset = load_historical_backtest_dataset(
            event_cases_csv=EVENT_CASES_CSV,
            eqnr_prices_csv=EQNR_PRICES_CSV,
        )

        missing_rows = [
            row for row in summarize_exit_backtests(dataset) if row.case_id == "case-2"
        ]

        self.assertEqual(len(missing_rows), 6)
        self.assertEqual(
            {row.norwegian_confirmation_status for row in missing_rows},
            {NorwegianConfirmationStatus.MISSING.value},
        )
        self.assertNotIn(
            ExitAnchor.NORWEGIAN_CONFIRMATION.value,
            {row.anchor for row in missing_rows},
        )

    def test_late_norwegian_confirmation_is_flagged_in_summary(self):
        dataset = load_historical_backtest_dataset(
            event_cases_csv=EVENT_CASES_CSV,
            eqnr_prices_csv=EQNR_PRICES_CSV,
        )

        late_rows = [
            row for row in summarize_exit_backtests(dataset) if row.case_id == "case-3"
        ]

        self.assertEqual(len(late_rows), 9)
        self.assertEqual(
            {row.norwegian_confirmation_status for row in late_rows},
            {NorwegianConfirmationStatus.LATE.value},
        )
        self.assertIn(
            ExitAnchor.NORWEGIAN_CONFIRMATION.value,
            {row.anchor for row in late_rows},
        )

    def test_summary_output_is_machine_readable(self):
        dataset = load_historical_backtest_dataset(
            event_cases_csv=EVENT_CASES_CSV,
            eqnr_prices_csv=EQNR_PRICES_CSV,
        )
        rows = summarize_exit_backtests(dataset)

        dicts = summary_rows_as_dicts(rows)
        csv_text = summary_rows_to_csv(rows)

        self.assertEqual(dicts[0]["case_id"], "case-1")
        self.assertEqual(dicts[0]["first_official_signal_at"], "2026-07-27T12:00:00Z")
        self.assertIn("case_id,norwegian_confirmation_status,anchor", csv_text)
        self.assertIn("norwegian_confirmation", csv_text)

    def test_missing_required_event_field_is_rejected(self):
        bad_cases_csv = """case_id,first_source_ingested_at,order_entry_at
case-1,2026-07-27T12:01:00Z,2026-07-27T12:02:00Z
"""

        with self.assertRaisesRegex(ValueError, "first_official_signal_at is required"):
            load_historical_backtest_dataset(
                event_cases_csv=bad_cases_csv,
                eqnr_prices_csv=EQNR_PRICES_CSV,
            )

    def test_missing_price_series_for_case_is_rejected(self):
        missing_price_csv = """case_id,timestamp,mid
other-case,2026-07-27T12:00:00Z,300.0
"""

        with self.assertRaisesRegex(ValueError, "missing EQNR price points"):
            load_historical_backtest_dataset(
                event_cases_csv=EVENT_CASES_CSV,
                eqnr_prices_csv=missing_price_csv,
            )


if __name__ == "__main__":
    unittest.main()
