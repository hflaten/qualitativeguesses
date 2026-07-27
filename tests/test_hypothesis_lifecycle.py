from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from qualstocks.domain import (
    ActiveHypothesis,
    Direction,
    EventClassification,
    HypothesisState,
    SourceCategory,
    SourceClass,
    SourceEvent,
    SourceTier,
)
from qualstocks.strategy import (
    HypothesisLifecycleConfig,
    HypothesisLifecycleEngine,
    HypothesisTransitionAction,
    PaperOrderSide,
    norwegian_confirmation_source,
)


class HypothesisLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.engine = HypothesisLifecycleEngine()
        self.now = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)

    def test_first_trigger_opens_active_hypothesis_and_initial_order(self):
        event = self._event(source_id="centcom", event_id="event-1")
        classification = self._classification(event, confidence=0.82)

        decision = self.engine.apply_event(
            active_hypothesis=None,
            event=event,
            classification=classification,
            now=self.now,
        )

        self.assertEqual(decision.action, HypothesisTransitionAction.OPEN_ACTIVE)
        self.assertIsNotNone(decision.hypothesis)
        self.assertEqual(decision.hypothesis.state, HypothesisState.ACTIVE)
        self.assertEqual(decision.hypothesis.source_event_ids, ("event-1",))
        self.assertEqual(len(decision.paper_order_intents), 1)
        order = decision.paper_order_intents[0]
        self.assertEqual(order.side, PaperOrderSide.BUY)
        self.assertEqual(order.instrument, "EQNR.OL")
        self.assertEqual(order.aum_pct, 50)

    def test_low_confidence_trigger_is_ignored(self):
        event = self._event(source_id="centcom", event_id="event-1")
        classification = self._classification(event, confidence=0.4)

        decision = self.engine.apply_event(
            active_hypothesis=None,
            event=event,
            classification=classification,
            now=self.now,
        )

        self.assertEqual(decision.action, HypothesisTransitionAction.IGNORE)
        self.assertIsNone(decision.hypothesis)

    def test_second_independent_signal_reinforces_and_creates_second_order(self):
        active = self._hypothesis(source_event_ids=("event-1",))
        event = self._event(source_id="polymarket", event_id="event-2")
        classification = self._classification(event, confidence=0.7, reinforcement=True)

        decision = self.engine.apply_event(
            active_hypothesis=active,
            event=event,
            classification=classification,
            now=self.now,
        )

        self.assertEqual(decision.action, HypothesisTransitionAction.REINFORCE)
        self.assertEqual(decision.hypothesis.state, HypothesisState.REINFORCED)
        self.assertEqual(decision.hypothesis.source_event_ids, ("event-1", "event-2"))
        self.assertEqual(decision.paper_order_intents[0].aum_pct, 50)

    def test_norwegian_confirmation_anchors_exit_timers(self):
        active = self._hypothesis(source_event_ids=("event-1",))
        event = self._event(
            source_id="e24",
            event_id="event-3",
            source_class=SourceClass.NORWEGIAN_CONFIRMATION,
            source_category=SourceCategory.NORWEGIAN_PRESS,
            first_seen_at=self.now + timedelta(minutes=12),
        )
        classification = self._classification(event, reinforcement=True)

        decision = self.engine.apply_event(
            active_hypothesis=active,
            event=event,
            classification=classification,
            now=self.now + timedelta(minutes=12),
        )

        self.assertEqual(decision.action, HypothesisTransitionAction.CONFIRM_NORWEGIAN)
        self.assertEqual(
            decision.hypothesis.state,
            HypothesisState.CONFIRMED_BY_NORWEGIAN_SOURCE,
        )
        self.assertEqual(decision.hypothesis.norwegian_confirmation_at, event.first_seen_at)
        self.assertEqual(
            [planned.scheduled_for for planned in decision.planned_exits],
            [
                event.first_seen_at + timedelta(minutes=30),
                event.first_seen_at + timedelta(minutes=40),
                event.first_seen_at + timedelta(minutes=50),
            ],
        )

    def test_scheduled_exit_fires_on_first_due_window(self):
        active = self._hypothesis(
            state=HypothesisState.CONFIRMED_BY_NORWEGIAN_SOURCE,
            norwegian_confirmation_at=self.now,
        )

        decision = self.engine.evaluate_timers(
            active_hypothesis=active,
            now=self.now + timedelta(minutes=31),
        )

        self.assertEqual(decision.action, HypothesisTransitionAction.SCHEDULED_EXIT)
        self.assertEqual(decision.hypothesis.state, HypothesisState.EXITING)
        self.assertEqual(decision.paper_order_intents[0].side, PaperOrderSide.SELL)
        self.assertEqual(decision.planned_exits[0].window_minutes, 30)

    def test_fallback_exit_fires_without_norwegian_confirmation(self):
        active = self._hypothesis(created_at=self.now)

        decision = self.engine.evaluate_timers(
            active_hypothesis=active,
            now=self.now + timedelta(minutes=91),
        )

        self.assertEqual(decision.action, HypothesisTransitionAction.FALLBACK_EXIT)
        self.assertEqual(decision.hypothesis.state, HypothesisState.EXITING)
        self.assertEqual(decision.paper_order_intents[0].side, PaperOrderSide.SELL)

    def test_contradiction_closes_hypothesis_and_creates_exit_intent(self):
        active = self._hypothesis(source_event_ids=("event-1",))
        event = self._event(source_id="state_department", event_id="event-4")
        classification = self._classification(
            event,
            direction=Direction.BEARISH_EQUINOR,
            confidence=0.8,
            contradiction=True,
        )

        decision = self.engine.apply_event(
            active_hypothesis=active,
            event=event,
            classification=classification,
            now=self.now,
        )

        self.assertEqual(decision.action, HypothesisTransitionAction.CONTRADICT)
        self.assertEqual(decision.hypothesis.state, HypothesisState.CONTRADICTED)
        self.assertEqual(decision.paper_order_intents[0].side, PaperOrderSide.SELL)

    def test_norwegian_confirmation_source_definition(self):
        norwegian_press = self._event(
            source_id="dn",
            event_id="event-5",
            source_class=SourceClass.OFFICIAL_ACTOR,
            source_category=SourceCategory.NORWEGIAN_PRESS,
        )
        exchange = self._event(
            source_id="euronext",
            event_id="event-6",
            source_class=SourceClass.EQUINOR_OR_EXCHANGE,
            source_category=SourceCategory.NORWEGIAN_MARKET,
        )

        self.assertTrue(norwegian_confirmation_source(norwegian_press))
        self.assertTrue(norwegian_confirmation_source(exchange))

    def test_config_rejects_allocations_above_full_aum(self):
        with self.assertRaises(ValueError):
            HypothesisLifecycleConfig(initial_aum_pct=75, reinforcement_aum_pct=50)

    def _event(
        self,
        *,
        source_id: str,
        event_id: str,
        source_class: SourceClass = SourceClass.OFFICIAL_ACTOR,
        source_category: SourceCategory = SourceCategory.OFFICIAL_US,
        first_seen_at: datetime | None = None,
    ) -> SourceEvent:
        return SourceEvent(
            source=source_id,
            source_class=source_class,
            title="Regional escalation update",
            url="https://example.invalid/update",
            payload={},
            source_id=source_id,
            source_tier=SourceTier.TRIGGER,
            source_category=source_category,
            first_seen_at=first_seen_at or self.now,
            id=event_id,
        )

    def _classification(
        self,
        event: SourceEvent,
        *,
        direction: Direction = Direction.BULLISH_EQUINOR,
        confidence: float = 0.8,
        reinforcement: bool = False,
        contradiction: bool = False,
    ) -> EventClassification:
        return EventClassification(
            event_id=event.id,
            relevant_to_equinor=True,
            direction=direction,
            confidence=confidence,
            event_type="us_iran_escalation",
            reasoning_summary="Escalation raises oil supply risk.",
            is_reinforcement=reinforcement,
            is_contradiction=contradiction,
        )

    def _hypothesis(
        self,
        *,
        state: HypothesisState = HypothesisState.ACTIVE,
        source_event_ids: tuple[str, ...] = ("event-1",),
        created_at: datetime | None = None,
        norwegian_confirmation_at: datetime | None = None,
    ) -> ActiveHypothesis:
        return ActiveHypothesis(
            thesis="Escalation raises oil supply risk.",
            direction=Direction.BULLISH_EQUINOR,
            confidence=0.8,
            state=state,
            source_event_ids=source_event_ids,
            created_at=created_at or self.now,
            norwegian_confirmation_at=norwegian_confirmation_at,
        )


if __name__ == "__main__":
    unittest.main()
