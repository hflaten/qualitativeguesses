from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from qualstocks.domain import Direction, SourceCategory, SourceClass, SourceTier
from qualstocks.ingestion import RawAdapterEvent, SourceEventStatus
from qualstocks.paper import (
    PaperLedgerConfig,
    PaperTradingScenario,
    PaperTradingScenarioRunner,
    ScenarioClassification,
    ScenarioSourceStep,
    ScenarioTimerStep,
    quote,
)


class PaperTradingScenarioTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc)
        self.runner = PaperTradingScenarioRunner()

    def test_happy_path_opens_reinforces_confirms_and_exits(self):
        scenario = PaperTradingScenario(
            ledger_config=self._ledger_config(),
            steps=(
                ScenarioSourceStep(
                    raw_event=self._raw_event("centcom-1"),
                    classification=ScenarioClassification(),
                    quote=quote(price="300", observed_at=self.now),
                    now=self.now,
                ),
                ScenarioSourceStep(
                    raw_event=self._raw_event("polymarket-1", source="polymarket"),
                    classification=ScenarioClassification(is_reinforcement=True),
                    quote=quote(price="310", observed_at=self.now + timedelta(minutes=2)),
                    now=self.now + timedelta(minutes=2),
                ),
                ScenarioSourceStep(
                    raw_event=self._raw_event(
                        "e24-1",
                        source="e24",
                        source_class=SourceClass.NORWEGIAN_CONFIRMATION,
                        source_category=SourceCategory.NORWEGIAN_PRESS,
                        source_tier=SourceTier.CONFIRMATION,
                    ),
                    classification=ScenarioClassification(is_reinforcement=True),
                    quote=quote(price="315", observed_at=self.now + timedelta(minutes=12)),
                    now=self.now + timedelta(minutes=12),
                ),
                ScenarioTimerStep(
                    quote=quote(price="330", observed_at=self.now + timedelta(minutes=45)),
                    now=self.now + timedelta(minutes=45),
                ),
            ),
        )

        result = self.runner.run(scenario)

        self.assertEqual(result.created_ingestion_count, 3)
        self.assertIsNone(result.state.active_hypothesis)
        self.assertFalse(result.state.ledger.position("EQNR.OL").is_open)
        self.assertGreater(result.state.last_valuation.total_pnl, Decimal("0"))
        self.assertEqual(result.dashboard_status["system_state"], "listening")
        self.assertIsNone(result.dashboard_status["paper_position"])
        self.assertGreater(len(result.dashboard_status["audit_timeline"]), 0)

    def test_duplicate_raw_event_is_not_classified_or_traded_twice(self):
        raw_event = self._raw_event("centcom-1", idempotency_key="provider:centcom:1")
        scenario = PaperTradingScenario(
            ledger_config=self._ledger_config(),
            steps=(
                ScenarioSourceStep(
                    raw_event=raw_event,
                    classification=ScenarioClassification(),
                    quote=quote(price="300", observed_at=self.now),
                    now=self.now,
                ),
                ScenarioSourceStep(
                    raw_event=raw_event,
                    classification=ScenarioClassification(),
                    quote=quote(price="301", observed_at=self.now + timedelta(seconds=5)),
                    now=self.now + timedelta(seconds=5),
                ),
            ),
        )

        result = self.runner.run(scenario)

        self.assertEqual(
            [ingestion.status for ingestion in result.ingestion_results],
            [SourceEventStatus.CREATED, SourceEventStatus.DUPLICATE],
        )
        self.assertEqual(len(result.orchestrator_results), 1)
        self.assertEqual(len(result.state.ledger.fills), 1)

    def test_contradiction_exits_and_resets_hypothesis(self):
        scenario = PaperTradingScenario(
            ledger_config=self._ledger_config(),
            steps=(
                ScenarioSourceStep(
                    raw_event=self._raw_event("centcom-1"),
                    classification=ScenarioClassification(),
                    quote=quote(price="300", observed_at=self.now),
                    now=self.now,
                ),
                ScenarioSourceStep(
                    raw_event=self._raw_event("state-dept-1", source="state_department"),
                    classification=ScenarioClassification(
                        direction=Direction.BEARISH_EQUINOR,
                        is_contradiction=True,
                    ),
                    quote=quote(price="320", observed_at=self.now + timedelta(minutes=8)),
                    now=self.now + timedelta(minutes=8),
                ),
            ),
        )

        result = self.runner.run(scenario)

        self.assertIsNone(result.state.active_hypothesis)
        self.assertFalse(result.state.ledger.position("EQNR.OL").is_open)
        self.assertEqual(len(result.state.ledger.fills), 2)
        self.assertGreater(result.state.last_valuation.total_pnl, Decimal("0"))

    def test_one_active_hypothesis_ignores_unrelated_second_opener(self):
        scenario = PaperTradingScenario(
            ledger_config=self._ledger_config(),
            steps=(
                ScenarioSourceStep(
                    raw_event=self._raw_event("centcom-1"),
                    classification=ScenarioClassification(),
                    quote=quote(price="300", observed_at=self.now),
                    now=self.now,
                ),
                ScenarioSourceStep(
                    raw_event=self._raw_event("kalshi-1", source="kalshi"),
                    classification=ScenarioClassification(
                        direction=Direction.BEARISH_EQUINOR,
                        confidence=0.4,
                    ),
                    quote=quote(price="299", observed_at=self.now + timedelta(minutes=1)),
                    now=self.now + timedelta(minutes=1),
                ),
            ),
        )

        result = self.runner.run(scenario)

        self.assertIsNotNone(result.state.active_hypothesis)
        self.assertEqual(len(result.state.active_hypothesis.source_event_ids), 1)
        self.assertEqual(len(result.state.ledger.fills), 1)

    def _raw_event(
        self,
        raw_event_ref: str,
        *,
        source: str = "centcom",
        source_class: SourceClass = SourceClass.OFFICIAL_ACTOR,
        source_category: SourceCategory = SourceCategory.OFFICIAL_US,
        source_tier: SourceTier = SourceTier.TRIGGER,
        idempotency_key: str | None = None,
    ) -> RawAdapterEvent:
        return RawAdapterEvent(
            source=source,
            source_id=source,
            source_class=source_class,
            source_category=source_category,
            source_tier=source_tier,
            instrument="EQNR.OL",
            payload={"headline": "Regional escalation update"},
            provenance={
                "url": f"https://example.invalid/{raw_event_ref}",
                "raw_event_ref": raw_event_ref,
            },
            source_timestamp=self.now,
            first_seen_at=self.now,
            idempotency_key=idempotency_key,
        )

    def _ledger_config(self) -> PaperLedgerConfig:
        return PaperLedgerConfig(
            initial_cash=Decimal("100000"),
            fees_bps=Decimal("1"),
            slippage_bps=Decimal("0"),
        )


if __name__ == "__main__":
    unittest.main()
