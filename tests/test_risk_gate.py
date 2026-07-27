from __future__ import annotations

import unittest

from qualstocks.domain import ActiveHypothesis, Direction, HypothesisState
from qualstocks.strategy import (
    PaperOrderIntent,
    PaperOrderSide,
    PortfolioRiskSnapshot,
    RiskDecisionStatus,
    RiskGate,
    RiskGateConfig,
    TradingMode,
)


class RiskGateTest(unittest.TestCase):
    def test_paper_mode_approves_default_50_pct_initial_order(self):
        gate = RiskGate()
        decision = gate.evaluate_order(
            order_intent=self._buy(50),
            snapshot=PortfolioRiskSnapshot(),
            active_hypothesis=None,
        )

        self.assertTrue(decision.approved)
        self.assertEqual(decision.status, RiskDecisionStatus.APPROVED)
        self.assertEqual(decision.audit_action, "risk_decision_approved")
        self.assertEqual(decision.audit_payload["source_event_id"], "event-1")

    def test_live_mode_rejects_when_live_trading_disabled(self):
        gate = RiskGate(RiskGateConfig(mode=TradingMode.LIVE))
        decision = gate.evaluate_order(
            order_intent=self._buy(5),
            snapshot=PortfolioRiskSnapshot(),
            active_hypothesis=None,
        )

        self.assertFalse(decision.approved)
        self.assertEqual(decision.status, RiskDecisionStatus.REJECTED)
        self.assertEqual(decision.reason, "Live trading is disabled by default.")

    def test_live_mode_rejects_order_above_small_live_default(self):
        gate = RiskGate(
            RiskGateConfig(
                mode=TradingMode.LIVE,
                live_trading_enabled=True,
                live_max_order_aum_pct=5,
            )
        )
        decision = gate.evaluate_order(
            order_intent=self._buy(50),
            snapshot=PortfolioRiskSnapshot(),
            active_hypothesis=None,
        )

        self.assertFalse(decision.approved)
        self.assertEqual(decision.reason, "Live order exceeds live-mode max order size.")

    def test_rejects_single_name_exposure_breach(self):
        gate = RiskGate(RiskGateConfig(max_single_name_exposure_pct=60))
        decision = gate.evaluate_order(
            order_intent=self._buy(50),
            snapshot=PortfolioRiskSnapshot(single_name_exposure_pct=20),
            active_hypothesis=self._hypothesis(),
        )

        self.assertFalse(decision.approved)
        self.assertEqual(decision.reason, "Order would exceed max single-name exposure.")

    def test_rejects_event_exposure_breach(self):
        gate = RiskGate(RiskGateConfig(max_event_exposure_pct=70))
        decision = gate.evaluate_order(
            order_intent=self._buy(50),
            snapshot=PortfolioRiskSnapshot(event_exposure_pct=30),
            active_hypothesis=self._hypothesis(),
        )

        self.assertFalse(decision.approved)
        self.assertEqual(decision.reason, "Order would exceed max event exposure.")

    def test_rejects_after_daily_loss_limit(self):
        gate = RiskGate(RiskGateConfig(max_daily_loss_pct=5))
        decision = gate.evaluate_order(
            order_intent=self._buy(10),
            snapshot=PortfolioRiskSnapshot(daily_realized_loss_pct=5),
            active_hypothesis=self._hypothesis(),
        )

        self.assertFalse(decision.approved)
        self.assertEqual(decision.reason, "Daily loss limit has been reached.")

    def test_rejects_when_max_open_hypotheses_reached(self):
        gate = RiskGate(RiskGateConfig(max_open_hypotheses=1))
        decision = gate.evaluate_order(
            order_intent=self._buy(10),
            snapshot=PortfolioRiskSnapshot(open_hypotheses=1),
            active_hypothesis=None,
        )

        self.assertFalse(decision.approved)
        self.assertEqual(decision.reason, "Max open hypotheses limit has been reached.")

    def test_reinforcement_requires_independent_or_material_information(self):
        gate = RiskGate()
        rejected = gate.evaluate_order(
            order_intent=self._buy(50, source_event_id="event-2"),
            snapshot=PortfolioRiskSnapshot(single_name_exposure_pct=50, event_exposure_pct=50),
            active_hypothesis=self._hypothesis(),
            reinforcement=True,
        )
        approved = gate.evaluate_order(
            order_intent=self._buy(50, source_event_id="event-2"),
            snapshot=PortfolioRiskSnapshot(single_name_exposure_pct=50, event_exposure_pct=50),
            active_hypothesis=self._hypothesis(),
            reinforcement=True,
            independent_source_confirmation=True,
        )

        self.assertFalse(rejected.approved)
        self.assertEqual(
            rejected.reason,
            "Reinforcement requires independent source confirmation or new information.",
        )
        self.assertTrue(approved.approved)

    def test_forced_liquidation_rejects_buys_and_approves_sells(self):
        gate = RiskGate()
        buy = gate.evaluate_order(
            order_intent=self._buy(10),
            snapshot=PortfolioRiskSnapshot(forced_liquidation_required=True),
            active_hypothesis=self._hypothesis(),
        )
        sell = gate.evaluate_order(
            order_intent=PaperOrderIntent(
                side=PaperOrderSide.SELL,
                instrument="EQNR.OL",
                aum_pct=100,
                reason="Forced liquidation.",
                source_event_id="event-3",
            ),
            snapshot=PortfolioRiskSnapshot(forced_liquidation_required=True),
            active_hypothesis=self._hypothesis(),
        )

        self.assertFalse(buy.approved)
        self.assertEqual(buy.reason, "Forced liquidation is active; new buy intents are rejected.")
        self.assertTrue(sell.approved)
        self.assertEqual(sell.status, RiskDecisionStatus.FORCED_LIQUIDATION)

    def test_config_rejects_zero_open_hypotheses_limit(self):
        with self.assertRaises(ValueError):
            RiskGateConfig(max_open_hypotheses=0)

    def _buy(self, aum_pct: int, *, source_event_id: str = "event-1") -> PaperOrderIntent:
        return PaperOrderIntent(
            side=PaperOrderSide.BUY,
            instrument="EQNR.OL",
            aum_pct=aum_pct,
            reason="Test buy.",
            source_event_id=source_event_id,
        )

    def _hypothesis(self) -> ActiveHypothesis:
        return ActiveHypothesis(
            thesis="Escalation raises oil supply risk.",
            direction=Direction.BULLISH_EQUINOR,
            confidence=0.8,
            state=HypothesisState.ACTIVE,
            source_event_ids=("event-1",),
        )


if __name__ == "__main__":
    unittest.main()
