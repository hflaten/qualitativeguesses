from __future__ import annotations

import unittest

from qualstocks.execution import (
    BrokerSubmissionStatus,
    LiveBrokerAdapter,
    PaperExecutionAdapter,
    RiskApprovedOrder,
    assert_live_broker_preconditions,
    enabled_execution_adapter,
)
from qualstocks.strategy import (
    PaperOrderIntent,
    PaperOrderSide,
    RiskDecisionStatus,
    RiskGate,
    RiskGateConfig,
    TradingMode,
)


class ExecutionBrokerTest(unittest.TestCase):
    def test_risk_approved_order_requires_approved_matching_decision(self):
        intent = self._intent()
        decision = RiskGate().evaluate_order(
            order_intent=intent,
            snapshot=self._empty_snapshot(),
            active_hypothesis=None,
            materially_new_information=True,
        )

        approved = RiskApprovedOrder(intent=intent, risk_decision=decision)

        self.assertEqual(approved.intent, intent)
        self.assertEqual(approved.risk_decision.status, RiskDecisionStatus.APPROVED)

    def test_risk_rejected_order_cannot_cross_execution_boundary(self):
        intent = self._intent(aum_pct=101)
        decision = RiskGate().evaluate_order(
            order_intent=intent,
            snapshot=self._empty_snapshot(),
            active_hypothesis=None,
            materially_new_information=True,
        )

        with self.assertRaises(ValueError):
            RiskApprovedOrder(intent=intent, risk_decision=decision)

    def test_paper_adapter_is_enabled_execution_implementation(self):
        adapter = enabled_execution_adapter()

        self.assertIsInstance(adapter, PaperExecutionAdapter)
        self.assertEqual(adapter.broker, "paper")

    def test_paper_adapter_separates_submission_ack_cancel_and_reconcile(self):
        adapter = PaperExecutionAdapter()
        approved = self._approved_order()

        submission = adapter.submit_order(approved)
        acknowledgement = adapter.acknowledge_submission(submission)
        cancellation = adapter.cancel_order(
            client_order_id=approved.client_order_id,
            reason="operator pause",
        )
        reconciliation = adapter.reconcile()

        self.assertEqual(submission.status, BrokerSubmissionStatus.SUBMITTED)
        self.assertTrue(acknowledgement.accepted)
        self.assertEqual(acknowledgement.status, BrokerSubmissionStatus.ACKNOWLEDGED)
        self.assertTrue(cancellation.accepted)
        self.assertEqual(reconciliation.open_order_ids, ())

    def test_live_adapter_defaults_deny_construction_and_submission(self):
        with self.assertRaisesRegex(RuntimeError, "mode must be live"):
            LiveBrokerAdapter(broker="future-broker")

    def test_live_adapter_requires_all_risk_preconditions(self):
        config = RiskGateConfig(
            mode=TradingMode.LIVE,
            deployment_environment="production",
            live_environment_name="production",
            live_trading_enabled=True,
            live_trading_acknowledged=True,
            kill_switch_enabled=False,
        )

        assert_live_broker_preconditions(config)
        adapter = LiveBrokerAdapter(broker="future-broker", risk_config=config)

        with self.assertRaises(NotImplementedError):
            adapter.submit_order(self._approved_order())

    def _approved_order(self) -> RiskApprovedOrder:
        intent = self._intent()
        decision = RiskGate().evaluate_order(
            order_intent=intent,
            snapshot=self._empty_snapshot(),
            active_hypothesis=None,
            materially_new_information=True,
        )
        return RiskApprovedOrder(intent=intent, risk_decision=decision)

    def _intent(self, *, aum_pct: int = 50) -> PaperOrderIntent:
        return PaperOrderIntent(
            side=PaperOrderSide.BUY,
            instrument="EQNR.OL",
            aum_pct=aum_pct,
            reason="test order",
            source_event_id="event-1",
        )

    def _empty_snapshot(self):
        from qualstocks.strategy import PortfolioRiskSnapshot

        return PortfolioRiskSnapshot()


if __name__ == "__main__":
    unittest.main()
