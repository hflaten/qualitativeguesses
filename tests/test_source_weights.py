from __future__ import annotations

import unittest
from datetime import datetime, timezone

from qualstocks.domain import (
    Direction,
    EventClassification,
    SourceCategory,
    SourceClass,
    SourceEvent,
    SourceTier,
)
from qualstocks.research import SourceRanking
from qualstocks.strategy import (
    HypothesisLifecycleEngine,
    HypothesisTransitionAction,
    SourceWeightBook,
    source_weight_from_ranking,
)


class SourceWeightTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc)

    def test_top_ranked_trigger_source_can_open_with_weighted_confidence(self):
        engine = HypothesisLifecycleEngine(
            source_weights=SourceWeightBook.from_rankings((self._ranking("centcom"),))
        )
        event = self._event("event-1", source_id="centcom")

        decision = engine.apply_event(
            active_hypothesis=None,
            event=event,
            classification=self._classification(event, confidence=0.6),
            now=self.now,
        )

        self.assertEqual(decision.action, HypothesisTransitionAction.OPEN_ACTIVE)
        self.assertIsNotNone(decision.hypothesis)
        self.assertGreaterEqual(decision.effective_confidence, 0.65)
        self.assertFalse(decision.source_weight.defaulted)

    def test_confirmation_only_source_cannot_open_even_with_high_weight(self):
        engine = HypothesisLifecycleEngine(
            source_weights=SourceWeightBook.from_rankings((self._ranking("e24"),))
        )
        event = self._event(
            "event-1",
            source_id="e24",
            source_class=SourceClass.NORWEGIAN_CONFIRMATION,
            source_category=SourceCategory.NORWEGIAN_PRESS,
            source_tier=SourceTier.CONFIRMATION,
        )

        decision = engine.apply_event(
            active_hypothesis=None,
            event=event,
            classification=self._classification(event, confidence=0.95),
            now=self.now,
        )

        self.assertEqual(decision.action, HypothesisTransitionAction.IGNORE)
        self.assertIsNone(decision.hypothesis)
        self.assertFalse(decision.source_weight.defaulted)

    def test_missing_ranking_uses_conservative_default_weight(self):
        engine = HypothesisLifecycleEngine()
        event = self._event("event-1", source_id="new-trigger")

        decision = engine.apply_event(
            active_hypothesis=None,
            event=event,
            classification=self._classification(event, confidence=0.75),
            now=self.now,
        )

        self.assertEqual(decision.action, HypothesisTransitionAction.OPEN_ACTIVE)
        self.assertTrue(decision.source_weight.defaulted)
        self.assertEqual(decision.source_weight.confidence_multiplier, 0.9)
        self.assertAlmostEqual(decision.effective_confidence, 0.675)

    def test_weighted_contradiction_exits_active_hypothesis(self):
        engine = HypothesisLifecycleEngine(
            source_weights=SourceWeightBook.from_rankings((self._ranking("centcom"),))
        )
        opening_event = self._event("event-1", source_id="centcom")
        opened = engine.apply_event(
            active_hypothesis=None,
            event=opening_event,
            classification=self._classification(opening_event, confidence=0.75),
            now=self.now,
        )
        assert opened.hypothesis is not None
        contradiction_event = self._event("event-2", source_id="centcom")

        decision = engine.apply_event(
            active_hypothesis=opened.hypothesis,
            event=contradiction_event,
            classification=self._classification(
                contradiction_event,
                direction=Direction.BEARISH_EQUINOR,
                confidence=0.6,
                contradiction=True,
            ),
            now=self.now,
        )

        self.assertEqual(decision.action, HypothesisTransitionAction.CONTRADICT)
        self.assertGreaterEqual(decision.effective_confidence, 0.6)
        self.assertEqual(len(decision.paper_order_intents), 1)

    def test_source_weight_from_ranking_uses_all_ranking_components(self):
        weight = source_weight_from_ranking(self._ranking("centcom"))

        self.assertEqual(weight.source_id, "centcom")
        self.assertGreater(weight.speed_score, 0)
        self.assertGreater(weight.uniqueness_score, 0)
        self.assertGreater(weight.directionality_score, 0)
        self.assertGreater(weight.outcome_score, 0)
        self.assertGreater(weight.confidence_multiplier, 1)

    def _ranking(self, source_id: str) -> SourceRanking:
        return SourceRanking(
            source_id=source_id,
            source_name=source_id.upper(),
            observation_count=12,
            first_source_count=10,
            avg_latency_seconds=4,
            avg_lead_lag_seconds=0,
            avg_post_cost_directional_return_pct=1.8,
            hit_rate=0.83,
            uniqueness_score=0.83,
            ranking_score=3.1,
        )

    def _event(
        self,
        event_id: str,
        *,
        source_id: str,
        source_class: SourceClass = SourceClass.OFFICIAL_ACTOR,
        source_category: SourceCategory = SourceCategory.OFFICIAL_US,
        source_tier: SourceTier = SourceTier.TRIGGER,
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
            first_seen_at=self.now,
            id=event_id,
        )

    def _classification(
        self,
        event: SourceEvent,
        *,
        direction: Direction = Direction.BULLISH_EQUINOR,
        confidence: float,
        contradiction: bool = False,
    ) -> EventClassification:
        return EventClassification(
            event_id=event.id,
            relevant_to_equinor=True,
            direction=direction,
            confidence=confidence,
            event_type="us_iran_escalation",
            reasoning_summary="Escalation raises oil supply risk.",
            is_contradiction=contradiction,
        )


if __name__ == "__main__":
    unittest.main()
