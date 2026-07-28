from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from qualstocks.domain import Direction, EventClassification
from qualstocks.ingestion import PaperTradingRepository, PersistenceStatus
from qualstocks.paper import MarketQuote, PaperLedger, PaperLedgerConfig
from qualstocks.strategy import (
    PaperOrderIntent,
    PaperOrderSide,
    PortfolioRiskSnapshot,
    RiskGate,
)
from qualstocks.strategy.orchestrator import OrchestratorAuditEvent


class FakeTradingDatabaseClient:
    def __init__(self):
        self.classifications = {}
        self.risk_decisions = {}
        self.paper_orders = {}
        self.paper_fills = {}
        self.position_snapshot = None
        self.valuation_snapshots = []
        self.audit_events = {}

    def insert_event_classification(self, values):
        key = (values["event_id"], values["model"])
        if key in self.classifications:
            return None
        row = {"id": str(uuid4()), "created_at": _now(), **values}
        self.classifications[key] = row
        return row

    def fetch_event_classification(self, event_id, model):
        return self.classifications.get((event_id, model))

    def insert_risk_decision(self, values):
        key = values["idempotency_key"]
        if key in self.risk_decisions:
            return None
        row = {"id": str(uuid4()), "created_at": _now(), **values}
        self.risk_decisions[key] = row
        return row

    def fetch_risk_decision_by_key(self, idempotency_key):
        return self.risk_decisions.get(idempotency_key)

    def insert_paper_order(self, values):
        key = values["idempotency_key"]
        if key in self.paper_orders:
            return None
        row = {"created_at": values["created_at"], **values}
        self.paper_orders[key] = row
        return row

    def fetch_paper_order_by_key(self, idempotency_key):
        return self.paper_orders.get(idempotency_key)

    def insert_paper_fill(self, values):
        key = values["idempotency_key"]
        if key in self.paper_fills:
            return None
        row = {"filled_at": values["filled_at"], **values}
        self.paper_fills[key] = row
        return row

    def fetch_paper_fill_by_key(self, idempotency_key):
        return self.paper_fills.get(idempotency_key)

    def upsert_position_snapshot(self, values):
        self.position_snapshot = {"id": str(uuid4()), **values}
        return self.position_snapshot

    def insert_valuation_snapshot(self, values):
        row = {"id": str(uuid4()), "created_at": _now(), **values}
        self.valuation_snapshots.append(row)
        return row

    def fetch_dashboard_read_model(self, hypothesis_id=None):
        return {
            "position": self.position_snapshot,
            "valuation": self.valuation_snapshots[-1] if self.valuation_snapshots else None,
            "audit_timeline": list(self.audit_events.values()),
        }

    def insert_audit_event(self, values):
        key = values["idempotency_key"]
        if key in self.audit_events:
            return None
        row = {"id": str(uuid4()), **values}
        self.audit_events[key] = row
        return row

    def fetch_audit_event_by_key(self, idempotency_key):
        return self.audit_events.get(idempotency_key)


class TradingPersistenceTest(unittest.TestCase):
    def setUp(self):
        self.client = FakeTradingDatabaseClient()
        self.repository = PaperTradingRepository(self.client)
        self.now = _now()
        self.hypothesis_id = str(uuid4())
        self.event_id = str(uuid4())

    def test_classification_persistence_is_duplicate_safe(self):
        classification = self._classification()

        first = self.repository.persist_event_classification(
            classification,
            model="gpt-5-mini",
            raw_response={"confidence": 0.9},
        )
        second = self.repository.persist_event_classification(
            classification,
            model="gpt-5-mini",
            raw_response={"confidence": 0.9},
        )

        self.assertEqual(first.status, PersistenceStatus.CREATED)
        self.assertEqual(second.status, PersistenceStatus.DUPLICATE)
        self.assertEqual(len(self.client.classifications), 1)
        stored = next(iter(self.client.classifications.values()))
        self.assertEqual(stored["direction"], "bullish_equinor")
        self.assertEqual(json.loads(stored["raw_response"])["confidence"], 0.9)

    def test_risk_decision_persistence_preserves_evidence_payload(self):
        intent = self._intent()
        decision = RiskGate().evaluate_order(
            order_intent=intent,
            snapshot=PortfolioRiskSnapshot(),
            active_hypothesis=None,
            materially_new_information=True,
        )

        result = self.repository.persist_risk_decision(
            decision,
            idempotency_key="risk:event-1:order-1",
            hypothesis_id=self.hypothesis_id,
            event_id=self.event_id,
        )

        self.assertEqual(result.status, PersistenceStatus.CREATED)
        stored = self.client.risk_decisions["risk:event-1:order-1"]
        self.assertEqual(stored["status"], "approved")
        self.assertEqual(stored["audit_action"], "risk_decision_approved")
        self.assertEqual(json.loads(stored["payload"])["source_event_id"], self.event_id)

    def test_paper_order_and_fill_persistence_are_replay_safe(self):
        ledger = self._filled_ledger()
        order = ledger.orders[0]
        fill = ledger.fills[0]

        first_order = self.repository.persist_paper_order(
            order,
            hypothesis_id=self.hypothesis_id,
            idempotency_key="order:event-1:tranche-1",
        )
        second_order = self.repository.persist_paper_order(
            order,
            hypothesis_id=self.hypothesis_id,
            idempotency_key="order:event-1:tranche-1",
        )
        first_fill = self.repository.persist_paper_fill(
            fill,
            idempotency_key="fill:event-1:tranche-1",
        )
        second_fill = self.repository.persist_paper_fill(
            fill,
            idempotency_key="fill:event-1:tranche-1",
        )

        self.assertEqual(first_order.status, PersistenceStatus.CREATED)
        self.assertEqual(second_order.status, PersistenceStatus.DUPLICATE)
        self.assertEqual(first_fill.status, PersistenceStatus.CREATED)
        self.assertEqual(second_fill.status, PersistenceStatus.DUPLICATE)
        self.assertEqual(len(self.client.paper_orders), 1)
        self.assertEqual(len(self.client.paper_fills), 1)

    def test_position_and_valuation_snapshots_power_dashboard_read_model(self):
        ledger = self._filled_ledger()
        valuation = ledger.valuation(
            quote=self._quote(Decimal("330")),
            as_of=self.now,
        )

        position_result = self.repository.persist_position_snapshot(
            ledger.position("EQNR.OL"),
            hypothesis_id=self.hypothesis_id,
            opened_at=self.now,
            updated_at=self.now,
        )
        valuation_result = self.repository.persist_valuation_snapshot(
            valuation,
            hypothesis_id=self.hypothesis_id,
            idempotency_key="valuation:event-1:latest",
        )
        read_model = self.repository.dashboard_read_model(self.hypothesis_id)

        self.assertEqual(position_result.status, PersistenceStatus.UPDATED)
        self.assertEqual(valuation_result.status, PersistenceStatus.CREATED)
        self.assertEqual(read_model["position"]["instrument"], "EQNR.OL")
        self.assertEqual(read_model["valuation"]["last_price"], Decimal("330.0000"))
        self.assertEqual(read_model["valuation"]["quote_freshness"], "fresh")

    def test_orchestrator_audit_event_persistence_is_replay_safe(self):
        event = OrchestratorAuditEvent(
            action="hypothesis_transition",
            summary="First qualifying trigger opens the paper-trading hypothesis.",
            created_at=self.now,
            event_id=self.event_id,
            hypothesis_id=self.hypothesis_id,
            payload={
                "effective_confidence": 0.82,
                "source_weight": {"source_id": "centcom_rss", "defaulted": False},
            },
        )

        first = self.repository.persist_orchestrator_audit_event(
            event,
            idempotency_key="audit:hypothesis:event-1",
        )
        second = self.repository.persist_orchestrator_audit_event(
            event,
            idempotency_key="audit:hypothesis:event-1",
        )
        stored = self.client.audit_events["audit:hypothesis:event-1"]

        self.assertEqual(first.status, PersistenceStatus.CREATED)
        self.assertEqual(second.status, PersistenceStatus.DUPLICATE)
        self.assertEqual(len(self.client.audit_events), 1)
        self.assertEqual(stored["action"], "hypothesis_transition")
        payload = json.loads(stored["payload"])
        self.assertEqual(payload["effective_confidence"], 0.82)
        self.assertEqual(payload["source_weight"]["source_id"], "centcom_rss")

    def test_batch_audit_persistence_builds_stable_idempotency_keys(self):
        events = (
            OrchestratorAuditEvent(
                action="risk_decision_approved",
                summary="Risk approved.",
                created_at=self.now,
                event_id=self.event_id,
                order_id=str(uuid4()),
                payload={"status": "approved"},
            ),
            OrchestratorAuditEvent(
                action="paper_fill_created",
                summary="Paper fill created.",
                created_at=self.now,
                event_id=self.event_id,
                order_id=str(uuid4()),
                payload={"fill_id": "fill-1"},
            ),
        )

        first = self.repository.persist_orchestrator_audit_events(
            events,
            idempotency_prefix="scenario-1",
        )
        second = self.repository.persist_orchestrator_audit_events(
            events,
            idempotency_prefix="scenario-1",
        )

        self.assertEqual([result.status for result in first], [PersistenceStatus.CREATED] * 2)
        self.assertEqual([result.status for result in second], [PersistenceStatus.DUPLICATE] * 2)
        self.assertEqual(len(self.client.audit_events), 2)

    def _classification(self) -> EventClassification:
        return EventClassification(
            event_id=self.event_id,
            relevant_to_equinor=True,
            direction=Direction.BULLISH_EQUINOR,
            confidence=0.9,
            event_type="official_escalation",
            reasoning_summary="Escalation can raise Equinor via oil prices.",
        )

    def _intent(self) -> PaperOrderIntent:
        return PaperOrderIntent(
            side=PaperOrderSide.BUY,
            instrument="EQNR.OL",
            aum_pct=50,
            reason="test order",
            source_event_id=self.event_id,
        )

    def _filled_ledger(self) -> PaperLedger:
        ledger = PaperLedger(
            PaperLedgerConfig(
                initial_cash=Decimal("100000"),
                fees_bps=Decimal("1"),
                slippage_bps=Decimal("0"),
            )
        )
        order = ledger.submit_order(self._intent(), now=self.now)
        ledger.approve_order(order.id, now=self.now)
        ledger.fill_order(order.id, self._quote(Decimal("300")), now=self.now)
        return ledger

    def _quote(self, last_price: Decimal) -> MarketQuote:
        return MarketQuote(
            instrument="EQNR.OL",
            last_price=last_price,
            currency="NOK",
            source="test",
            observed_at=self.now,
        )


def _now() -> datetime:
    return datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc)


if __name__ == "__main__":
    unittest.main()
