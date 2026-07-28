from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Protocol

from qualstocks.domain import ActiveHypothesis, Direction, EventClassification, HypothesisState
from qualstocks.paper import PaperFill, PaperOrder, PaperPosition, PortfolioValuation
from qualstocks.strategy import RiskGateDecision
from qualstocks.strategy.orchestrator import OrchestratorAuditEvent


class StrEnum(str, Enum):
    pass


class PersistenceStatus(StrEnum):
    CREATED = "created"
    DUPLICATE = "duplicate"
    UPDATED = "updated"


@dataclass(frozen=True)
class PersistenceResult:
    status: PersistenceStatus
    row: dict[str, object]

    @property
    def created(self) -> bool:
        return self.status == PersistenceStatus.CREATED


class TradingDatabaseClient(Protocol):
    def insert_hypothesis(self, values: dict[str, object]) -> dict[str, object] | None:
        """Insert a hypothesis row, or return None on duplicate."""

    def fetch_hypothesis(self, hypothesis_id: str) -> dict[str, object] | None:
        """Fetch a persisted hypothesis by id."""

    def fetch_active_hypothesis(self) -> dict[str, object] | None:
        """Fetch the latest open hypothesis if one exists."""

    def insert_event_classification(self, values: dict[str, object]) -> dict[str, object] | None:
        """Insert a classification row, or return None on duplicate."""

    def fetch_event_classification(self, event_id: str, model: str) -> dict[str, object] | None:
        """Fetch an existing classification by event and model."""

    def insert_risk_decision(self, values: dict[str, object]) -> dict[str, object] | None:
        """Insert a risk decision row, or return None on duplicate."""

    def fetch_risk_decision_by_key(self, idempotency_key: str) -> dict[str, object] | None:
        """Fetch an existing risk decision by idempotency key."""

    def insert_paper_order(self, values: dict[str, object]) -> dict[str, object] | None:
        """Insert a paper order, or return None on duplicate."""

    def fetch_paper_order_by_key(self, idempotency_key: str) -> dict[str, object] | None:
        """Fetch an existing paper order by idempotency key."""

    def insert_paper_fill(self, values: dict[str, object]) -> dict[str, object] | None:
        """Insert a paper fill, or return None on duplicate."""

    def fetch_paper_fill_by_key(self, idempotency_key: str) -> dict[str, object] | None:
        """Fetch an existing paper fill by idempotency key."""

    def upsert_position_snapshot(self, values: dict[str, object]) -> dict[str, object]:
        """Upsert the latest position snapshot for a hypothesis and instrument."""

    def insert_valuation_snapshot(self, values: dict[str, object]) -> dict[str, object]:
        """Insert a paper portfolio valuation snapshot."""

    def fetch_dashboard_read_model(self, hypothesis_id: str | None = None) -> dict[str, object]:
        """Fetch latest persisted paper-trading state for dashboard rendering."""

    def insert_audit_event(self, values: dict[str, object]) -> dict[str, object] | None:
        """Insert an audit event, or return None on duplicate."""

    def fetch_audit_event_by_key(self, idempotency_key: str) -> dict[str, object] | None:
        """Fetch an audit event by idempotency key."""


@dataclass(frozen=True)
class PaperTradingRepository:
    client: TradingDatabaseClient

    def persist_hypothesis(self, hypothesis: ActiveHypothesis) -> PersistenceResult:
        row = self.client.insert_hypothesis(_hypothesis_values(hypothesis))
        status = PersistenceStatus.CREATED
        if row is None:
            row = self.client.fetch_hypothesis(hypothesis.id)
            status = PersistenceStatus.DUPLICATE
        return _result(row, status, "hypothesis")

    def active_hypothesis(self) -> ActiveHypothesis | None:
        row = self.client.fetch_active_hypothesis()
        if row is None:
            return None
        return _hypothesis_from_row(row)

    def persist_event_classification(
        self,
        classification: EventClassification,
        *,
        model: str,
        raw_response: dict[str, object] | None = None,
    ) -> PersistenceResult:
        row = self.client.insert_event_classification(
            _classification_values(classification, model, raw_response or {})
        )
        status = PersistenceStatus.CREATED
        if row is None:
            row = self.client.fetch_event_classification(classification.event_id, model)
            status = PersistenceStatus.DUPLICATE
        return _result(row, status, "event classification")

    def persist_risk_decision(
        self,
        decision: RiskGateDecision,
        *,
        idempotency_key: str,
        hypothesis_id: str | None = None,
        event_id: str | None = None,
        order_id: str | None = None,
    ) -> PersistenceResult:
        row = self.client.insert_risk_decision(
            _risk_decision_values(
                decision,
                idempotency_key=idempotency_key,
                hypothesis_id=hypothesis_id,
                event_id=event_id,
                order_id=order_id,
            )
        )
        status = PersistenceStatus.CREATED
        if row is None:
            row = self.client.fetch_risk_decision_by_key(idempotency_key)
            status = PersistenceStatus.DUPLICATE
        return _result(row, status, "risk decision")

    def persist_paper_order(
        self,
        order: PaperOrder,
        *,
        hypothesis_id: str,
        idempotency_key: str,
    ) -> PersistenceResult:
        row = self.client.insert_paper_order(
            _paper_order_values(
                order,
                hypothesis_id=hypothesis_id,
                idempotency_key=idempotency_key,
            )
        )
        status = PersistenceStatus.CREATED
        if row is None:
            row = self.client.fetch_paper_order_by_key(idempotency_key)
            status = PersistenceStatus.DUPLICATE
        return _result(row, status, "paper order")

    def persist_paper_fill(
        self,
        fill: PaperFill,
        *,
        idempotency_key: str,
    ) -> PersistenceResult:
        row = self.client.insert_paper_fill(_paper_fill_values(fill, idempotency_key))
        status = PersistenceStatus.CREATED
        if row is None:
            row = self.client.fetch_paper_fill_by_key(idempotency_key)
            status = PersistenceStatus.DUPLICATE
        return _result(row, status, "paper fill")

    def persist_position_snapshot(
        self,
        position: PaperPosition,
        *,
        hypothesis_id: str,
        opened_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> PersistenceResult:
        row = self.client.upsert_position_snapshot(
            _position_values(
                position,
                hypothesis_id=hypothesis_id,
                opened_at=opened_at,
                updated_at=updated_at,
            )
        )
        return _result(row, PersistenceStatus.UPDATED, "position snapshot")

    def persist_valuation_snapshot(
        self,
        valuation: PortfolioValuation,
        *,
        hypothesis_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> PersistenceResult:
        row = self.client.insert_valuation_snapshot(
            _valuation_values(
                valuation,
                hypothesis_id=hypothesis_id,
                idempotency_key=idempotency_key,
            )
        )
        return _result(row, PersistenceStatus.CREATED, "valuation snapshot")

    def dashboard_read_model(self, hypothesis_id: str | None = None) -> dict[str, object]:
        return self.client.fetch_dashboard_read_model(hypothesis_id)

    def persist_orchestrator_audit_event(
        self,
        event: OrchestratorAuditEvent,
        *,
        idempotency_key: str,
    ) -> PersistenceResult:
        row = self.client.insert_audit_event(
            _audit_event_values(event, idempotency_key=idempotency_key)
        )
        status = PersistenceStatus.CREATED
        if row is None:
            row = self.client.fetch_audit_event_by_key(idempotency_key)
            status = PersistenceStatus.DUPLICATE
        return _result(row, status, "audit event")

    def persist_orchestrator_audit_events(
        self,
        events: tuple[OrchestratorAuditEvent, ...],
        *,
        idempotency_prefix: str,
    ) -> tuple[PersistenceResult, ...]:
        return tuple(
            self.persist_orchestrator_audit_event(
                event,
                idempotency_key=_audit_event_key(idempotency_prefix, event, index),
            )
            for index, event in enumerate(events)
        )


def _hypothesis_values(hypothesis: ActiveHypothesis) -> dict[str, object]:
    return {
        "id": hypothesis.id,
        "state": hypothesis.state.value,
        "thesis": hypothesis.thesis,
        "direction": hypothesis.direction.value,
        "confidence": Decimal(str(hypothesis.confidence)),
        "source_event_ids": list(hypothesis.source_event_ids),
        "norwegian_confirmation_at": hypothesis.norwegian_confirmation_at,
        "created_at": hypothesis.created_at,
        "updated_at": hypothesis.created_at,
    }


def _hypothesis_from_row(row: dict[str, object]) -> ActiveHypothesis:
    source_event_ids = row.get("source_event_ids") or ()
    if isinstance(source_event_ids, list):
        source_event_ids = tuple(str(value) for value in source_event_ids)
    elif not isinstance(source_event_ids, tuple):
        source_event_ids = ()
    return ActiveHypothesis(
        id=str(row["id"]),
        state=HypothesisState(str(row["state"])),
        thesis=str(row["thesis"]),
        direction=Direction(str(row["direction"])),
        confidence=float(row["confidence"]),
        source_event_ids=source_event_ids,
        norwegian_confirmation_at=(
            row["norwegian_confirmation_at"]
            if isinstance(row.get("norwegian_confirmation_at"), datetime)
            else None
        ),
        created_at=(
            row["created_at"]
            if isinstance(row.get("created_at"), datetime)
            else datetime.now(timezone.utc)
        ),
    )


def _classification_values(
    classification: EventClassification,
    model: str,
    raw_response: dict[str, object],
) -> dict[str, object]:
    return {
        "event_id": classification.event_id,
        "model": model,
        "relevant_to_equinor": classification.relevant_to_equinor,
        "direction": classification.direction.value,
        "confidence": Decimal(str(classification.confidence)),
        "event_type": classification.event_type,
        "reasoning_summary": classification.reasoning_summary,
        "is_reinforcement": classification.is_reinforcement,
        "is_contradiction": classification.is_contradiction,
        "raw_response": _json(raw_response),
    }


def _risk_decision_values(
    decision: RiskGateDecision,
    *,
    idempotency_key: str,
    hypothesis_id: str | None,
    event_id: str | None,
    order_id: str | None,
) -> dict[str, object]:
    return {
        "hypothesis_id": hypothesis_id,
        "event_id": event_id,
        "order_id": order_id,
        "idempotency_key": idempotency_key,
        "status": decision.status.value,
        "reason": decision.reason,
        "audit_action": decision.audit_action,
        "payload": _json(decision.audit_payload),
    }


def _paper_order_values(
    order: PaperOrder,
    *,
    hypothesis_id: str,
    idempotency_key: str,
) -> dict[str, object]:
    return {
        "id": order.id,
        "hypothesis_id": hypothesis_id,
        "side": order.side.value,
        "instrument": order.instrument,
        "aum_pct": Decimal(order.aum_pct),
        "status": order.status.value,
        "reason": order.reason,
        "source_event_id": order.source_event_id,
        "idempotency_key": idempotency_key,
        "reject_reason": order.reject_reason,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
    }


def _paper_fill_values(fill: PaperFill, idempotency_key: str) -> dict[str, object]:
    return {
        "id": fill.id,
        "order_id": fill.order_id,
        "side": fill.side.value,
        "instrument": fill.instrument,
        "fill_price": fill.fill_price,
        "quantity": fill.quantity,
        "notional": fill.notional,
        "fees": fill.fees,
        "idempotency_key": idempotency_key,
        "filled_at": fill.filled_at,
    }


def _position_values(
    position: PaperPosition,
    *,
    hypothesis_id: str,
    opened_at: datetime | None,
    updated_at: datetime | None,
) -> dict[str, object]:
    timestamp = updated_at or datetime.now(timezone.utc)
    return {
        "hypothesis_id": hypothesis_id,
        "instrument": position.instrument,
        "quantity": position.quantity,
        "average_entry_price": position.average_entry_price,
        "realized_pnl": position.realized_pnl,
        "unrealized_pnl": Decimal("0"),
        "opened_at": opened_at or timestamp,
        "closed_at": timestamp if not position.is_open else None,
        "updated_at": timestamp,
    }


def _valuation_values(
    valuation: PortfolioValuation,
    *,
    hypothesis_id: str | None,
    idempotency_key: str | None,
) -> dict[str, object]:
    return {
        "hypothesis_id": hypothesis_id,
        "idempotency_key": idempotency_key,
        "instrument": valuation.instrument,
        "quantity": valuation.quantity,
        "average_entry_price": valuation.average_entry_price,
        "cash": valuation.cash,
        "starting_aum": valuation.starting_aum,
        "equity": valuation.equity,
        "last_price": valuation.last_price,
        "market_value": valuation.market_value,
        "realized_pnl": valuation.realized_pnl,
        "unrealized_pnl": valuation.unrealized_pnl,
        "unrealized_pnl_pct": valuation.unrealized_pnl_pct,
        "total_pnl": valuation.total_pnl,
        "total_pnl_pct": valuation.total_pnl_pct,
        "quote_freshness": valuation.quote_freshness.value,
        "quote_source": valuation.quote_source,
        "quote_observed_at": valuation.quote_observed_at,
        "payload": _json(asdict(valuation)),
    }


def _audit_event_values(
    event: OrchestratorAuditEvent,
    *,
    idempotency_key: str,
) -> dict[str, object]:
    return {
        "hypothesis_id": event.hypothesis_id,
        "event_id": event.event_id,
        "order_id": event.order_id,
        "action": event.action,
        "actor": "system",
        "summary": event.summary,
        "payload": _json(event.payload),
        "idempotency_key": idempotency_key,
        "created_at": event.created_at,
    }


def _audit_event_key(
    prefix: str,
    event: OrchestratorAuditEvent,
    index: int,
) -> str:
    entity = event.event_id or event.order_id or event.hypothesis_id or "system"
    return f"{prefix}:{index}:{event.action}:{entity}"


def _result(
    row: dict[str, object] | None,
    status: PersistenceStatus,
    label: str,
) -> PersistenceResult:
    if row is None:
        raise RuntimeError(f"{label} persistence returned no row")
    return PersistenceResult(status=status, row=row)


def _json(value: dict[str, object]) -> str:
    return json.dumps(value, default=str, sort_keys=True)
