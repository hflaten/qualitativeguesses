from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from qualstocks.domain import Direction, EventClassification, SourceClass, SourceEvent, SourceTier
from qualstocks.ingestion import PaperTradingRepository
from qualstocks.paper import MarketQuote
from qualstocks.strategy.lifecycle import HypothesisLifecycleConfig, HypothesisLifecycleEngine
from qualstocks.strategy.orchestrator import StrategyOrchestrator
from qualstocks.strategy.worker import PaperStrategyService


class FakeStrategyDatabaseClient:
    def __init__(self):
        self.hypotheses = {}
        self.classifications = {}
        self.risk_decisions = {}
        self.paper_orders = {}
        self.paper_fills = {}
        self.position_snapshot = None
        self.valuation_snapshots = []
        self.audit_events = {}

    def insert_hypothesis(self, values):
        hypothesis_id = values["id"]
        if hypothesis_id in self.hypotheses:
            return None
        row = {**values}
        self.hypotheses[hypothesis_id] = row
        return row

    def fetch_hypothesis(self, hypothesis_id):
        return self.hypotheses.get(hypothesis_id)

    def fetch_active_hypothesis(self):
        for row in self.hypotheses.values():
            if row["state"] in {
                "candidate",
                "active",
                "reinforced",
                "confirmed_by_norwegian_source",
            }:
                return row
        return None

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
            "active_hypothesis": self.fetch_active_hypothesis(),
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


class PaperStrategyServiceTest(unittest.TestCase):
    def setUp(self):
        self.client = FakeStrategyDatabaseClient()
        self.repository = PaperTradingRepository(self.client)
        lifecycle = HypothesisLifecycleEngine(
            HypothesisLifecycleConfig(initial_aum_pct=40, reinforcement_aum_pct=50)
        )
        self.service = PaperStrategyService(
            repository=self.repository,
            orchestrator=StrategyOrchestrator(lifecycle=lifecycle),
        )
        self.event = SourceEvent(
            id=str(uuid4()),
            source="CENTCOM RSS",
            source_class=SourceClass.OFFICIAL_ACTOR,
            title="Strait of Hormuz escalation",
            url="https://example.invalid/centcom",
            payload={},
            source_id="centcom_rss",
            source_tier=SourceTier.TRIGGER,
        )

    def test_relevant_classification_creates_hypothesis_and_first_tranche_order(self):
        result = self.service.handle_completed_classification(
            event=self.event,
            classification=self._classification(),
            quote=self._quote(),
            now=_now(),
        )

        self.assertIsNotNone(result.orchestrator_result.state.active_hypothesis)
        self.assertEqual(len(self.client.hypotheses), 1)
        self.assertEqual(len(self.client.paper_orders), 1)
        order = next(iter(self.client.paper_orders.values()))
        self.assertEqual(order["aum_pct"], Decimal("40"))
        self.assertEqual(order["status"], "filled")
        self.assertEqual(len(self.client.paper_fills), 1)
        self.assertEqual(len(self.client.risk_decisions), 1)
        self.assertGreaterEqual(len(self.client.audit_events), 3)

    def test_duplicate_classification_does_not_create_second_hypothesis_or_order(self):
        self.service.handle_completed_classification(
            event=self.event,
            classification=self._classification(),
            quote=self._quote(),
            now=_now(),
        )
        self.service.handle_completed_classification(
            event=self.event,
            classification=self._classification(),
            quote=self._quote(),
            now=_now(),
        )

        self.assertEqual(len(self.client.hypotheses), 1)
        self.assertEqual(len(self.client.paper_orders), 1)
        self.assertEqual(len(self.client.paper_fills), 1)

    def test_irrelevant_classification_is_ignored(self):
        self.service.handle_completed_classification(
            event=self.event,
            classification=self._classification(relevant=False),
            quote=self._quote(),
            now=_now(),
        )

        self.assertEqual(self.client.hypotheses, {})
        self.assertEqual(self.client.paper_orders, {})
        self.assertEqual(self.client.paper_fills, {})
        self.assertGreaterEqual(len(self.client.audit_events), 1)

    def test_service_refuses_non_paper_mode(self):
        service = PaperStrategyService(
            repository=self.repository,
            orchestrator=StrategyOrchestrator(),
            paper_trading_only=False,
        )

        with self.assertRaisesRegex(RuntimeError, "refuses non-paper"):
            service.handle_completed_classification(
                event=self.event,
                classification=self._classification(),
                quote=self._quote(),
                now=_now(),
            )

        self.assertEqual(self.client.hypotheses, {})
        self.assertEqual(self.client.paper_orders, {})

    def _classification(self, *, relevant: bool = True) -> EventClassification:
        return EventClassification(
            event_id=self.event.id,
            relevant_to_equinor=relevant,
            direction=Direction.BULLISH_EQUINOR,
            confidence=0.82,
            event_type="official_escalation",
            reasoning_summary="Escalation can lift oil prices and Equinor.",
        )

    def _quote(self) -> MarketQuote:
        return MarketQuote(
            instrument="EQNR.OL",
            last_price=Decimal("300"),
            currency="NOK",
            source="test",
            observed_at=_now(),
        )


def _now() -> datetime:
    return datetime(2026, 7, 28, 14, 0, tzinfo=timezone.utc)


if __name__ == "__main__":
    unittest.main()
