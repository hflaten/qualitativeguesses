from __future__ import annotations

import unittest

from qualstocks.research import (
    build_predictive_power_rows,
    load_predictive_power_dataset,
    predictive_power_rows_as_dicts,
    predictive_power_rows_to_csv,
    rank_sources,
)


EVENTS_CSV = """case_id,event_id,source_id,source_name,source_class,source_category,source_tier,event_timestamp,source_timestamp,first_seen_at,headline,body,topic_classification,equinor_relevance,oil_impact_channel,direction,confidence
case-1,event-1,truth-social,Truth Social,official_actor,official_us,trigger,2026-07-27T12:00:00Z,2026-07-27T12:00:10Z,2026-07-27T12:00:20Z,US warns Iran over Hormuz,,us_iran_war,0.92,hormuz_closure,long,0.84
case-1,event-2,e24,E24,norwegian_confirmation,norwegian_press,confirmation,2026-07-27T12:03:00Z,2026-07-27T12:03:30Z,2026-07-27T12:04:30Z,Oljeprisen stiger etter Hormuz-varsel,,us_iran_war,0.88,hormuz_closure,long,0.81
case-2,event-3,kalshi,Kalshi,prediction_market,prediction_market,trigger,2026-07-27T13:00:00Z,2026-07-27T13:00:00Z,2026-07-27T13:01:00Z,Hormuz closure odds jump,,us_iran_war,0.71,hormuz_closure,long,0.7
"""


EQNR_PRICES_CSV = """timestamp,mid,bid,ask
2026-07-27T12:00:00Z,300.0,299.95,300.05
2026-07-27T12:01:00Z,301.0,300.95,301.05
2026-07-27T12:05:00Z,303.0,302.95,303.05
2026-07-27T12:10:30Z,306.0,305.95,306.05
2026-07-27T12:30:30Z,312.0,311.95,312.05
2026-07-27T12:40:30Z,315.0,314.95,315.05
2026-07-27T12:50:30Z,318.0,317.95,318.05
2026-07-27T13:01:00Z,320.0,319.95,320.05
"""


BRENT_CSV = """timestamp,value
2026-07-27T12:00:00Z,88.0
2026-07-27T12:05:00Z,89.0
2026-07-27T12:50:00Z,91.0
"""


USD_NOK_CSV = """timestamp,value
2026-07-27T12:00:00Z,10.50
2026-07-27T12:05:00Z,10.55
2026-07-27T12:50:00Z,10.60
"""


class PredictivePowerDatasetTest(unittest.TestCase):
    def test_loads_research_events_and_control_series(self):
        dataset = load_predictive_power_dataset(
            events_csv=EVENTS_CSV,
            eqnr_prices_csv=EQNR_PRICES_CSV,
            brent_csv=BRENT_CSV,
            usd_nok_csv=USD_NOK_CSV,
        )

        self.assertEqual(len(dataset.events), 3)
        self.assertEqual(dataset.events[0].source_id, "truth-social")
        self.assertEqual(dataset.events[0].oil_impact_channel, "hormuz_closure")
        self.assertEqual(dataset.events[0].source_latency_seconds, 10.0)
        self.assertEqual(dataset.eqnr_prices[0].mid, 300.0)
        self.assertEqual(dataset.brent_points[0].value, 88.0)
        self.assertEqual(dataset.usd_nok_points[0].value, 10.50)

    def test_builds_response_windows_with_timestamp_alignment_and_controls(self):
        dataset = load_predictive_power_dataset(
            events_csv=EVENTS_CSV,
            eqnr_prices_csv=EQNR_PRICES_CSV,
            brent_csv=BRENT_CSV,
            usd_nok_csv=USD_NOK_CSV,
        )

        rows = build_predictive_power_rows(dataset, windows_minutes=(1, 5, 50))
        first = rows[0]

        self.assertEqual(len(rows), 9)
        self.assertEqual(first.event_id, "event-1")
        self.assertEqual(first.window_minutes, 1)
        self.assertEqual(first.source_rank_in_case, 1)
        self.assertEqual(first.source_lead_lag_seconds, 0.0)
        self.assertEqual(first.entry_price, 301.0)
        self.assertEqual(first.entry_price_at.isoformat(), "2026-07-27T12:01:00+00:00")
        self.assertEqual(first.exit_price, 303.0)
        self.assertAlmostEqual(first.eqnr_return_pct, 0.6644518272425249)
        self.assertAlmostEqual(first.post_cost_directional_return_pct, 0.5644518272425249)
        self.assertEqual(first.brent_at_entry, 88.0)
        self.assertEqual(first.brent_at_exit, 88.0)
        self.assertEqual(first.usd_nok_at_entry, 10.50)
        self.assertEqual(first.usd_nok_at_exit, 10.50)

        confirmation_row = next(row for row in rows if row.event_id == "event-2")
        self.assertEqual(confirmation_row.source_rank_in_case, 2)
        self.assertEqual(confirmation_row.source_lead_lag_seconds, 250.0)

    def test_missing_forward_price_is_flagged_without_rejecting_dataset(self):
        dataset = load_predictive_power_dataset(
            events_csv=EVENTS_CSV,
            eqnr_prices_csv=EQNR_PRICES_CSV,
        )

        rows = build_predictive_power_rows(dataset, windows_minutes=(50,))
        missing = next(row for row in rows if row.event_id == "event-3")

        self.assertEqual(missing.entry_price, 320.0)
        self.assertIsNone(missing.exit_price)
        self.assertEqual(missing.missing_data_reason, "missing_exit_price")
        self.assertIsNone(missing.post_cost_directional_return_pct)

    def test_missing_required_event_field_is_rejected(self):
        bad_events_csv = """case_id,event_id,source_id,source_name
case-1,event-1,truth-social,Truth Social
"""

        with self.assertRaisesRegex(ValueError, "source_class is required"):
            load_predictive_power_dataset(
                events_csv=bad_events_csv,
                eqnr_prices_csv=EQNR_PRICES_CSV,
            )

    def test_ranks_sources_by_speed_uniqueness_directionality_and_outcome(self):
        dataset = load_predictive_power_dataset(
            events_csv=EVENTS_CSV,
            eqnr_prices_csv=EQNR_PRICES_CSV,
        )
        rows = build_predictive_power_rows(dataset, windows_minutes=(1, 5))

        rankings = rank_sources(rows)

        self.assertEqual(rankings[0].source_id, "truth-social")
        self.assertEqual(rankings[0].first_source_count, 2)
        self.assertGreater(rankings[0].hit_rate, 0)
        self.assertGreater(rankings[0].ranking_score, rankings[1].ranking_score)

    def test_machine_readable_outputs_include_schema_fields(self):
        dataset = load_predictive_power_dataset(
            events_csv=EVENTS_CSV,
            eqnr_prices_csv=EQNR_PRICES_CSV,
        )
        rows = build_predictive_power_rows(dataset, windows_minutes=(1,))

        dicts = predictive_power_rows_as_dicts(rows)
        csv_text = predictive_power_rows_to_csv(rows)

        self.assertEqual(dicts[0]["event_id"], "event-1")
        self.assertEqual(dicts[0]["first_seen_at"], "2026-07-27T12:00:20Z")
        self.assertIn("source_latency_seconds,source_lead_lag_seconds", csv_text)
        self.assertIn("oil_impact_channel", csv_text)


if __name__ == "__main__":
    unittest.main()
