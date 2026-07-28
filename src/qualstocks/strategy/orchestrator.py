from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum

from qualstocks.domain import ActiveHypothesis, EventClassification, SourceEvent
from qualstocks.paper.ledger import (
    MarketQuote,
    PaperFill,
    PaperLedger,
    PaperOrder,
    PortfolioValuation,
)
from qualstocks.strategy.lifecycle import (
    HypothesisLifecycleDecision,
    HypothesisLifecycleEngine,
    HypothesisTransitionAction,
)
from qualstocks.strategy.risk import (
    PortfolioRiskSnapshot,
    RiskGate,
    RiskGateDecision,
)


class StrEnum(str, Enum):
    pass


class OrchestratorAuditAction(StrEnum):
    CLASSIFICATION_CONSUMED = "classification_consumed"
    HYPOTHESIS_TRANSITION = "hypothesis_transition"
    PAPER_ORDER_APPROVED = "paper_order_approved"
    PAPER_ORDER_REJECTED = "paper_order_rejected"
    PAPER_FILL_CREATED = "paper_fill_created"
    PAPER_VALUATION_UPDATED = "paper_valuation_updated"
    HYPOTHESIS_RESET = "hypothesis_reset"
    TIMER_IGNORED = "timer_ignored"


@dataclass(frozen=True)
class OrchestratorAuditEvent:
    action: str
    summary: str
    created_at: datetime
    event_id: str | None = None
    hypothesis_id: str | None = None
    order_id: str | None = None
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class OrchestratorState:
    active_hypothesis: ActiveHypothesis | None = None
    ledger: PaperLedger = field(default_factory=PaperLedger)
    last_valuation: PortfolioValuation | None = None
    audit_events: tuple[OrchestratorAuditEvent, ...] = ()


@dataclass(frozen=True)
class OrchestratorResult:
    state: OrchestratorState
    lifecycle_decision: HypothesisLifecycleDecision
    risk_decisions: tuple[RiskGateDecision, ...] = ()
    orders: tuple[PaperOrder, ...] = ()
    fills: tuple[PaperFill, ...] = ()
    valuation: PortfolioValuation | None = None
    audit_events: tuple[OrchestratorAuditEvent, ...] = ()


@dataclass(frozen=True)
class StrategyOrchestrator:
    lifecycle: HypothesisLifecycleEngine = field(default_factory=HypothesisLifecycleEngine)
    risk_gate: RiskGate = field(default_factory=RiskGate)

    def handle_classification(
        self,
        state: OrchestratorState,
        *,
        event: SourceEvent,
        classification: EventClassification,
        quote: MarketQuote | None,
        now: datetime | None = None,
    ) -> OrchestratorResult:
        timestamp = now or datetime.now(timezone.utc)
        lifecycle_decision = self.lifecycle.apply_event(
            active_hypothesis=state.active_hypothesis,
            event=event,
            classification=classification,
            now=timestamp,
        )
        return self._apply_lifecycle_decision(
            state,
            lifecycle_decision=lifecycle_decision,
            event_id=event.id,
            quote=quote,
            now=timestamp,
        )

    def handle_timer(
        self,
        state: OrchestratorState,
        *,
        quote: MarketQuote | None,
        now: datetime | None = None,
    ) -> OrchestratorResult:
        timestamp = now or datetime.now(timezone.utc)
        if state.active_hypothesis is None:
            lifecycle_decision = HypothesisLifecycleDecision(
                action=HypothesisTransitionAction.IGNORE,
                reason="No active hypothesis for timer evaluation.",
                hypothesis=None,
            )
            audit = (
                OrchestratorAuditEvent(
                    action=OrchestratorAuditAction.TIMER_IGNORED.value,
                    summary=lifecycle_decision.reason,
                    created_at=timestamp,
                ),
            )
            return OrchestratorResult(
                state=replace(state, audit_events=state.audit_events + audit),
                lifecycle_decision=lifecycle_decision,
                audit_events=audit,
            )

        lifecycle_decision = self.lifecycle.evaluate_timers(
            active_hypothesis=state.active_hypothesis,
            now=timestamp,
        )
        return self._apply_lifecycle_decision(
            state,
            lifecycle_decision=lifecycle_decision,
            event_id=None,
            quote=quote,
            now=timestamp,
        )

    def _apply_lifecycle_decision(
        self,
        state: OrchestratorState,
        *,
        lifecycle_decision: HypothesisLifecycleDecision,
        event_id: str | None,
        quote: MarketQuote | None,
        now: datetime,
    ) -> OrchestratorResult:
        audit_events: list[OrchestratorAuditEvent] = []
        orders: list[PaperOrder] = []
        fills: list[PaperFill] = []
        risk_decisions: list[RiskGateDecision] = []
        ledger = state.ledger
        current_hypothesis = lifecycle_decision.hypothesis

        audit_events.append(
            OrchestratorAuditEvent(
                action=OrchestratorAuditAction.HYPOTHESIS_TRANSITION.value,
                summary=lifecycle_decision.reason,
                created_at=now,
                event_id=event_id,
                hypothesis_id=current_hypothesis.id if current_hypothesis else None,
                payload={
                    "lifecycle_action": lifecycle_decision.action.value,
                    "audit_actions": list(lifecycle_decision.audit_actions),
                    "effective_confidence": lifecycle_decision.effective_confidence,
                    "source_weight": (
                        lifecycle_decision.source_weight.as_dict()
                        if lifecycle_decision.source_weight
                        else None
                    ),
                },
            )
        )

        for intent in lifecycle_decision.paper_order_intents:
            order = ledger.submit_order(intent, now=now)
            orders.append(order)
            decision = self.risk_gate.evaluate_order(
                order_intent=intent,
                snapshot=_risk_snapshot(ledger, intent.instrument, state.active_hypothesis),
                active_hypothesis=state.active_hypothesis,
                reinforcement=lifecycle_decision.action == HypothesisTransitionAction.REINFORCE,
                independent_source_confirmation=_independent_confirmation(
                    current_hypothesis,
                    intent.source_event_id,
                ),
                materially_new_information=True,
            )
            risk_decisions.append(decision)
            if not decision.approved:
                rejected = ledger.reject_order(order.id, reason=decision.reason, now=now)
                orders[-1] = rejected
                audit_events.append(_risk_audit(decision, rejected, now, current_hypothesis))
                continue

            approved = ledger.approve_order(order.id, now=now)
            orders[-1] = approved
            audit_events.append(_risk_audit(decision, approved, now, current_hypothesis))
            if quote is None:
                audit_events.append(
                    OrchestratorAuditEvent(
                        action=OrchestratorAuditAction.PAPER_ORDER_REJECTED.value,
                        summary="Approved order was not filled because quote is missing.",
                        created_at=now,
                        event_id=intent.source_event_id,
                        hypothesis_id=current_hypothesis.id if current_hypothesis else None,
                        order_id=approved.id,
                    )
                )
                continue

            fill = ledger.fill_order(approved.id, quote, now=now)
            fills.append(fill)
            orders[-1] = ledger.orders[-1]
            audit_events.append(
                OrchestratorAuditEvent(
                    action=OrchestratorAuditAction.PAPER_FILL_CREATED.value,
                    summary=(
                        f"Filled {fill.side.value} paper order for {fill.quantity} "
                        f"{fill.instrument} at {fill.fill_price}."
                    ),
                    created_at=now,
                    event_id=intent.source_event_id,
                    hypothesis_id=current_hypothesis.id if current_hypothesis else None,
                    order_id=approved.id,
                    payload={
                        "fill_id": fill.id,
                        "notional": str(fill.notional),
                        "fees": str(fill.fees),
                    },
                )
            )

        valuation = ledger.valuation(quote=quote, as_of=now)
        audit_events.append(
            OrchestratorAuditEvent(
                action=OrchestratorAuditAction.PAPER_VALUATION_UPDATED.value,
                summary="Paper valuation updated from latest quote state.",
                created_at=now,
                hypothesis_id=current_hypothesis.id if current_hypothesis else None,
                payload={
                    "total_pnl": str(valuation.total_pnl),
                    "unrealized_pnl": str(valuation.unrealized_pnl),
                    "quote_freshness": valuation.quote_freshness.value,
                },
            )
        )

        if fills and not ledger.position(self.lifecycle.config.instrument).is_open:
            current_hypothesis = None
            audit_events.append(
                OrchestratorAuditEvent(
                    action=OrchestratorAuditAction.HYPOTHESIS_RESET.value,
                    summary="Paper position is closed; active hypothesis reset.",
                    created_at=now,
                    event_id=event_id,
                )
            )
        if lifecycle_decision.action == HypothesisTransitionAction.OPEN_ACTIVE and not fills:
            current_hypothesis = None
            audit_events.append(
                OrchestratorAuditEvent(
                    action=OrchestratorAuditAction.HYPOTHESIS_RESET.value,
                    summary="Initial paper order did not fill; active hypothesis reset.",
                    created_at=now,
                    event_id=event_id,
                )
            )

        next_state = OrchestratorState(
            active_hypothesis=current_hypothesis,
            ledger=ledger,
            last_valuation=valuation,
            audit_events=state.audit_events + tuple(audit_events),
        )
        return OrchestratorResult(
            state=next_state,
            lifecycle_decision=lifecycle_decision,
            risk_decisions=tuple(risk_decisions),
            orders=tuple(orders),
            fills=tuple(fills),
            valuation=valuation,
            audit_events=tuple(audit_events),
        )


def _risk_snapshot(
    ledger: PaperLedger,
    instrument: str,
    active_hypothesis: ActiveHypothesis | None,
) -> PortfolioRiskSnapshot:
    position = ledger.position(instrument)
    exposure_pct = _pct(
        position.quantity * position.average_entry_price,
        ledger.config.initial_cash,
    )
    daily_loss_pct = _pct(
        abs(min(position.realized_pnl, Decimal("0"))),
        ledger.config.initial_cash,
    )
    return PortfolioRiskSnapshot(
        single_name_exposure_pct=exposure_pct,
        event_exposure_pct=exposure_pct,
        daily_realized_loss_pct=daily_loss_pct,
        open_hypotheses=1 if active_hypothesis is not None else 0,
    )


def _independent_confirmation(
    hypothesis: ActiveHypothesis | None,
    source_event_id: str | None,
) -> bool:
    if hypothesis is None or source_event_id is None:
        return False
    return source_event_id not in hypothesis.source_event_ids


def _risk_audit(
    decision: RiskGateDecision,
    order: PaperOrder,
    now: datetime,
    hypothesis: ActiveHypothesis | None,
) -> OrchestratorAuditEvent:
    return OrchestratorAuditEvent(
        action=(
            OrchestratorAuditAction.PAPER_ORDER_APPROVED.value
            if decision.approved
            else OrchestratorAuditAction.PAPER_ORDER_REJECTED.value
        ),
        summary=decision.reason,
        created_at=now,
        event_id=order.source_event_id,
        hypothesis_id=hypothesis.id if hypothesis else None,
        order_id=order.id,
        payload=decision.audit_payload,
    )


def _pct(numerator: Decimal, denominator: Decimal) -> int:
    if denominator == 0:
        return 0
    return int(
        (numerator / denominator * Decimal("100")).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )
