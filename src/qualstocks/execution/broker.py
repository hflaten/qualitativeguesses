from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Mapping, Protocol
from uuid import uuid4

from qualstocks.strategy import (
    PaperOrderIntent,
    PaperOrderSide,
    RiskDecisionStatus,
    RiskGateConfig,
    RiskGateDecision,
    TradingMode,
)


class StrEnum(str, Enum):
    pass


class BrokerSubmissionStatus(StrEnum):
    CREATED = "created"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class RiskApprovedOrder:
    intent: PaperOrderIntent
    risk_decision: RiskGateDecision
    client_order_id: str = field(default_factory=lambda: str(uuid4()))
    approved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.risk_decision.status != RiskDecisionStatus.APPROVED:
            raise ValueError("broker order requires an approved risk decision")
        if self.risk_decision.order_intent != self.intent:
            raise ValueError("risk decision must approve the same order intent")


@dataclass(frozen=True)
class BrokerSubmission:
    approved_order: RiskApprovedOrder
    broker: str
    status: BrokerSubmissionStatus
    submitted_at: datetime
    payload: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class BrokerAcknowledgement:
    client_order_id: str
    broker: str
    accepted: bool
    status: BrokerSubmissionStatus
    acknowledged_at: datetime
    broker_order_id: str | None = None
    reject_reason: str | None = None
    payload: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class BrokerExecutionFill:
    broker_order_id: str
    instrument: str
    side: PaperOrderSide
    fill_price: Decimal
    quantity: Decimal
    filled_at: datetime
    broker_fill_id: str | None = None
    fees: Decimal = Decimal("0")
    payload: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class BrokerCancellation:
    client_order_id: str
    broker: str
    accepted: bool
    cancelled_at: datetime
    broker_order_id: str | None = None
    reason: str | None = None
    payload: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class BrokerReconciliation:
    broker: str
    reconciled_at: datetime
    open_order_ids: tuple[str, ...]
    open_position_quantity: Decimal
    cash: Decimal | None = None
    payload: Mapping[str, object] = field(default_factory=dict)


class BrokerAdapter(Protocol):
    broker: str

    def submit_order(self, order: RiskApprovedOrder) -> BrokerSubmission:
        """Submit a risk-approved order to the execution venue."""

    def acknowledge_submission(
        self,
        submission: BrokerSubmission,
    ) -> BrokerAcknowledgement:
        """Return the broker acknowledgement for a submitted order."""

    def cancel_order(
        self,
        *,
        client_order_id: str,
        reason: str,
    ) -> BrokerCancellation:
        """Request cancellation for an outstanding broker order."""

    def reconcile(self) -> BrokerReconciliation:
        """Fetch broker-side open orders, positions, and cash for reconciliation."""


@dataclass(frozen=True)
class PaperExecutionAdapter:
    broker: str = "paper"

    def submit_order(self, order: RiskApprovedOrder) -> BrokerSubmission:
        return BrokerSubmission(
            approved_order=order,
            broker=self.broker,
            status=BrokerSubmissionStatus.SUBMITTED,
            submitted_at=datetime.now(timezone.utc),
            payload={"execution_mode": "paper"},
        )

    def acknowledge_submission(
        self,
        submission: BrokerSubmission,
    ) -> BrokerAcknowledgement:
        return BrokerAcknowledgement(
            client_order_id=submission.approved_order.client_order_id,
            broker=self.broker,
            accepted=True,
            status=BrokerSubmissionStatus.ACKNOWLEDGED,
            acknowledged_at=datetime.now(timezone.utc),
            broker_order_id=submission.approved_order.client_order_id,
            payload={"execution_mode": "paper"},
        )

    def cancel_order(
        self,
        *,
        client_order_id: str,
        reason: str,
    ) -> BrokerCancellation:
        return BrokerCancellation(
            client_order_id=client_order_id,
            broker=self.broker,
            accepted=True,
            cancelled_at=datetime.now(timezone.utc),
            reason=reason,
            payload={"execution_mode": "paper"},
        )

    def reconcile(self) -> BrokerReconciliation:
        return BrokerReconciliation(
            broker=self.broker,
            reconciled_at=datetime.now(timezone.utc),
            open_order_ids=(),
            open_position_quantity=Decimal("0"),
            payload={"execution_mode": "paper"},
        )


@dataclass(frozen=True)
class LiveBrokerAdapter:
    broker: str
    risk_config: RiskGateConfig

    def __init__(
        self,
        *,
        broker: str,
        risk_config: RiskGateConfig = RiskGateConfig(),
    ) -> None:
        assert_live_broker_preconditions(risk_config)
        object.__setattr__(self, "broker", broker)
        object.__setattr__(self, "risk_config", risk_config)

    def submit_order(self, order: RiskApprovedOrder) -> BrokerSubmission:
        raise NotImplementedError("live broker submission requires broker selection")

    def acknowledge_submission(
        self,
        submission: BrokerSubmission,
    ) -> BrokerAcknowledgement:
        raise NotImplementedError("live broker acknowledgement requires broker selection")

    def cancel_order(
        self,
        *,
        client_order_id: str,
        reason: str,
    ) -> BrokerCancellation:
        raise NotImplementedError("live broker cancellation requires broker selection")

    def reconcile(self) -> BrokerReconciliation:
        raise NotImplementedError("live broker reconciliation requires broker selection")


def enabled_execution_adapter() -> PaperExecutionAdapter:
    return PaperExecutionAdapter()


def assert_live_broker_preconditions(config: RiskGateConfig) -> None:
    failures: list[str] = []
    if config.mode != TradingMode.LIVE:
        failures.append("mode must be live")
    if not config.live_trading_enabled:
        failures.append("live trading must be enabled")
    if not config.live_trading_acknowledged:
        failures.append("live trading must be manually acknowledged")
    if config.deployment_environment != config.live_environment_name:
        failures.append("deployment environment must match live environment")
    if config.kill_switch_enabled:
        failures.append("kill switch must be disabled")
    if failures:
        raise RuntimeError("live broker adapter denied: " + "; ".join(failures))
