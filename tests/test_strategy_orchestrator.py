from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from qualstocks.domain import (
    Direction,
    EventClassification,
    HypothesisState,
    SourceCategory,
    SourceClass,
    SourceEvent,
    SourceTier,
)
from qualstocks.paper import MarketQuote, PaperLedger, PaperLedgerConfig
from qualstocks.strategy import (
    HypothesisTransitionAction,
    RiskGate,
    RiskGateConfig,
)
from qualstocks.strategy.orchestrator import (
    OrchestratorAuditAction,
    OrchestratorState,
    StrategyOrchestrator,
)


class StrategyOrchestratorTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc)
        self.orchestrator = StrategyOrchestrator()
        self.state = OrchestratorState(ledger=self._ledger())

    def test_open_flow_creates_first_tranche_fill_and_active_hypothesis(self):
        event = self._event("event-1")

        result = self.orchestrator.handle_classification(
            self.state,
            event=event,
            classification=self._classification(event),
            quote=self._quote(Decimal("300")),
            now=self.now,
        )

        self.assertEqual(result.lifecycle_decision.action, HypothesisTransitionAction.OPEN_ACTIVE)
        self.assertIsNotNone(result.state.active_hypothesis)
        self.assertEqual(len(result.risk_decisions), 1)
        self.assertTrue(result.risk_decisions[0].approved)
        self.assertEqual(len(result.fills), 1)
        self.assertEqual(result.state.ledger.position("EQNR.OL").quantity, Decimal("166.666667"))
        self.assertEqual(result.valuation.last_price, Decimal("300.0000"))

    def test_reinforce_flow_creates_second_tranche_fill(self):
        opened = self._open_state()
        event = self._event("event-2", source_id="polymarket")

        result = self.orchestrator.handle_classification(
            opened,
            event=event,
            classification=self._classification(event, reinforcement=True),
            quote=self._quote(Decimal("310")),
            now=self.now + timedelta(minutes=2),
        )

        self.assertEqual(result.lifecycle_decision.action, HypothesisTransitionAction.REINFORCE)
        self.assertEqual(len(result.fills), 1)
        self.assertEqual(result.state.active_hypothesis.state, HypothesisState.REINFORCED)
        self.assertGreater(result.state.ledger.position("EQNR.OL").quantity, Decimal("300"))

    def test_risk_rejection_prevents_initial_fill_and_resets_hypothesis(self):
        orchestrator = StrategyOrchestrator(
            risk_gate=RiskGate(RiskGateConfig(max_single_name_exposure_pct=40))
        )
        event = self._event("event-1")

        result = orchestrator.handle_classification(
            self.state,
            event=event,
            classification=self._classification(event),
            quote=self._quote(Decimal("300")),
            now=self.now,
        )

        self.assertEqual(result.lifecycle_decision.action, HypothesisTransitionAction.OPEN_ACTIVE)
        self.assertFalse(result.risk_decisions[0].approved)
        self.assertEqual(len(result.fills), 0)
        self.assertIsNone(result.state.active_hypothesis)
        self.assertEqual(result.state.ledger.position("EQNR.OL").quantity, Decimal("0"))

    def test_contradiction_exit_sells_position_and_resets_hypothesis(self):
        opened = self._open_state()
        event = self._event("event-3", source_id="state_department")

        result = self.orchestrator.handle_classification(
            opened,
            event=event,
            classification=self._classification(
                event,
                direction=Direction.BEARISH_EQUINOR,
                contradiction=True,
            ),
            quote=self._quote(Decimal("320")),
            now=self.now + timedelta(minutes=10),
        )

        self.assertEqual(result.lifecycle_decision.action, HypothesisTransitionAction.CONTRADICT)
        self.assertEqual(len(result.fills), 1)
        self.assertIsNone(result.state.active_hypothesis)
        self.assertFalse(result.state.ledger.position("EQNR.OL").is_open)
        self.assertIn(
            OrchestratorAuditAction.HYPOTHESIS_RESET.value,
            [event.action for event in result.audit_events],
        )

    def test_scheduled_exit_timer_sells_after_norwegian_anchor(self):
        confirmed = self._confirmed_state()

        result = self.orchestrator.handle_timer(
            confirmed,
            quote=self._quote(Decimal("330")),
            now=self.now + timedelta(minutes=45),
        )

        self.assertEqual(
            result.lifecycle_decision.action,
            HypothesisTransitionAction.SCHEDULED_EXIT,
        )
        self.assertEqual(result.lifecycle_decision.planned_exits[0].window_minutes, 30)
        self.assertEqual(len(result.fills), 1)
        self.assertIsNone(result.state.active_hypothesis)

    def test_fallback_exit_timer_sells_when_no_norwegian_anchor_arrives(self):
        opened = self._open_state()

        result = self.orchestrator.handle_timer(
            opened,
            quote=self._quote(Decimal("290")),
            now=self.now + timedelta(minutes=91),
        )

        self.assertEqual(result.lifecycle_decision.action, HypothesisTransitionAction.FALLBACK_EXIT)
        self.assertEqual(len(result.fills), 1)
        self.assertIsNone(result.state.active_hypothesis)

    def _open_state(self) -> OrchestratorState:
        event = self._event("event-1")
        result = self.orchestrator.handle_classification(
            self.state,
            event=event,
            classification=self._classification(event),
            quote=self._quote(Decimal("300")),
            now=self.now,
        )
        return result.state

    def _confirmed_state(self) -> OrchestratorState:
        opened = self._open_state()
        assert opened.active_hypothesis is not None
        norwegian_event = self._event(
            "event-2",
            source_id="e24",
            source_class=SourceClass.NORWEGIAN_CONFIRMATION,
            source_category=SourceCategory.NORWEGIAN_PRESS,
            source_tier=SourceTier.CONFIRMATION,
            first_seen_at=self.now + timedelta(minutes=12),
        )
        result = self.orchestrator.handle_classification(
            opened,
            event=norwegian_event,
            classification=self._classification(norwegian_event, reinforcement=True),
            quote=self._quote(Decimal("310")),
            now=self.now + timedelta(minutes=12),
        )
        return result.state

    def _ledger(self) -> PaperLedger:
        return PaperLedger(
            PaperLedgerConfig(
                initial_cash=Decimal("100000"),
                fees_bps=Decimal("1"),
                slippage_bps=Decimal("0"),
            )
        )

    def _event(
        self,
        event_id: str,
        *,
        source_id: str = "centcom",
        source_class: SourceClass = SourceClass.OFFICIAL_ACTOR,
        source_category: SourceCategory = SourceCategory.OFFICIAL_US,
        source_tier: SourceTier = SourceTier.TRIGGER,
        first_seen_at: datetime | None = None,
    ) -> SourceEvent:
        return SourceEvent(
            source=source_id,
            source_class=source_class,
            title="Regional escalation update",
            url="https://example.invalid/update",
            payload={},
            source_id=source_id,
            source_tier=source_tier,
            source_category=source_category,
            first_seen_at=first_seen_at or self.now,
            id=event_id,
        )

    def _classification(
        self,
        event: SourceEvent,
        *,
        direction: Direction = Direction.BULLISH_EQUINOR,
        reinforcement: bool = False,
        contradiction: bool = False,
    ) -> EventClassification:
        return EventClassification(
            event_id=event.id,
            relevant_to_equinor=True,
            direction=direction,
            confidence=0.82,
            event_type="us_iran_escalation",
            reasoning_summary="Escalation raises oil supply risk.",
            is_reinforcement=reinforcement,
            is_contradiction=contradiction,
        )

    def _quote(self, last_price: Decimal) -> MarketQuote:
        return MarketQuote(
            instrument="EQNR.OL",
            last_price=last_price,
            currency="NOK",
            source="test",
            observed_at=self.now,
        )


if __name__ == "__main__":
    unittest.main()
