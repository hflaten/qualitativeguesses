import unittest

from qualstocks.domain import ActiveHypothesis, Direction, HypothesisState


class DomainTest(unittest.TestCase):
    def test_active_hypothesis_can_accept_reinforcement(self):
        hypothesis = ActiveHypothesis(
            thesis="Escalation raises oil supply risk",
            direction=Direction.BULLISH_EQUINOR,
            confidence=0.8,
            state=HypothesisState.ACTIVE,
            source_event_ids=("event-1",),
        )

        self.assertTrue(hypothesis.can_accept_reinforcement())

    def test_exited_hypothesis_cannot_accept_reinforcement(self):
        hypothesis = ActiveHypothesis(
            thesis="Escalation raises oil supply risk",
            direction=Direction.BULLISH_EQUINOR,
            confidence=0.8,
            state=HypothesisState.EXITED,
            source_event_ids=("event-1",),
        )

        self.assertFalse(hypothesis.can_accept_reinforcement())


if __name__ == "__main__":
    unittest.main()

