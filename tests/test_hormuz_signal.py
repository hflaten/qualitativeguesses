from __future__ import annotations

import unittest

from qualstocks.domain import SourceClass
from qualstocks.signals import HormuzClosureSignal, HormuzClosureState
from qualstocks.sources import DEFAULT_SOURCE_REGISTRY, WebhookAdapter


def event(source_id: str, title: str, payload: dict[str, object] | None = None):
    source_definition = DEFAULT_SOURCE_REGISTRY.require(source_id)
    adapter = WebhookAdapter(
        source_definition.name,
        source_definition.source_class,
        source_definition=source_definition,
    )
    return adapter._record_event(
        title=title,
        url=f"https://example.invalid/{source_id}",
        payload=payload or {},
    )


class HormuzClosureSignalTest(unittest.TestCase):
    def test_unknown_without_hormuz_signal(self):
        assessment = HormuzClosureSignal().assess(
            (
                event(
                    "centcom_rss",
                    "Statement on unrelated regional military exercise",
                ),
            )
        )

        self.assertEqual(assessment.state, HormuzClosureState.UNKNOWN)
        self.assertFalse(assessment.is_actionable)

    def test_ukmto_hormuz_attack_is_actionable_degraded_signal(self):
        assessment = HormuzClosureSignal().assess(
            (
                event(
                    "ukmto",
                    "UKMTO warning: incident near Strait of Hormuz after vessel attack",
                ),
            )
        )

        self.assertEqual(assessment.state, HormuzClosureState.EFFECTIVELY_CLOSED)
        self.assertTrue(assessment.is_actionable)
        self.assertIn("oil", assessment.oil_price_transmission.lower())

    def test_official_closure_statement_confirms_closure(self):
        assessment = HormuzClosureSignal().assess(
            (
                event(
                    "irna",
                    "Iran says Strait of Hormuz is closed to tanker navigation",
                ),
            )
        )

        self.assertEqual(assessment.state, HormuzClosureState.CONFIRMED_CLOSED)
        self.assertTrue(assessment.opens_or_strengthens_hypothesis)

    def test_ais_transit_collapse_is_effectively_closed(self):
        assessment = HormuzClosureSignal().assess(
            (
                event(
                    "marinetraffic",
                    "AIS update for Strait of Hormuz tanker traffic",
                    {"transit_drop_pct": -0.76},
                ),
            )
        )

        self.assertEqual(assessment.state, HormuzClosureState.EFFECTIVELY_CLOSED)
        self.assertTrue(assessment.is_actionable)

    def test_prediction_market_probability_reprices_to_degraded(self):
        assessment = HormuzClosureSignal().assess(
            (
                event(
                    "polymarket",
                    "Will the Strait of Hormuz close this week?",
                    {"probability": 0.48, "probability_delta": 0.22},
                ),
            )
        )

        self.assertEqual(assessment.state, HormuzClosureState.DEGRADED)
        self.assertTrue(assessment.is_actionable)

    def test_oil_price_move_alone_is_not_actionable(self):
        source_definition = DEFAULT_SOURCE_REGISTRY.require("brent_wti")
        adapter = WebhookAdapter(
            source_definition.name,
            SourceClass.MARKET_CONTROL,
            source_definition=source_definition,
        )
        oil_event = adapter._record_event(
            title="Brent jumps during volatile session",
            url="https://example.invalid/brent",
            payload={"brent_move_pct": 5.2},
        )

        assessment = HormuzClosureSignal().assess((oil_event,))

        self.assertEqual(assessment.state, HormuzClosureState.DEGRADED)
        self.assertFalse(assessment.is_actionable)

    def test_reopening_report_suppresses_closure_thesis(self):
        assessment = HormuzClosureSignal().assess(
            (
                event(
                    "centcom_rss",
                    "Strait of Hormuz navigation resumed after earlier disruption",
                ),
            )
        )

        self.assertEqual(assessment.state, HormuzClosureState.REOPENED)
        self.assertFalse(assessment.is_actionable)


if __name__ == "__main__":
    unittest.main()
