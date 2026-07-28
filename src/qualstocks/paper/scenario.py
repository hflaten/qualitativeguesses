from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Iterable, Union

from qualstocks.dashboard.status import build_dashboard_status
from qualstocks.domain import Direction, EventClassification
from qualstocks.ingestion import (
    InMemoryAnalysisQueue,
    InMemoryEventRepository,
    IngestionResult,
    IngestionService,
    RawAdapterEvent,
)
from qualstocks.paper.ledger import MarketQuote, PaperLedger, PaperLedgerConfig
from qualstocks.settings import Settings, load_settings
from qualstocks.strategy.orchestrator import OrchestratorResult
from qualstocks.strategy.orchestrator import OrchestratorState, StrategyOrchestrator


@dataclass(frozen=True)
class ScenarioClassification:
    relevant_to_equinor: bool = True
    direction: Direction = Direction.BULLISH_EQUINOR
    confidence: float = 0.82
    event_type: str = "us_iran_escalation"
    reasoning_summary: str = "Escalation raises oil supply risk."
    is_reinforcement: bool = False
    is_contradiction: bool = False

    def for_event(self, event_id: str) -> EventClassification:
        return EventClassification(
            event_id=event_id,
            relevant_to_equinor=self.relevant_to_equinor,
            direction=self.direction,
            confidence=self.confidence,
            event_type=self.event_type,
            reasoning_summary=self.reasoning_summary,
            is_reinforcement=self.is_reinforcement,
            is_contradiction=self.is_contradiction,
        )


@dataclass(frozen=True)
class ScenarioSourceStep:
    raw_event: RawAdapterEvent
    classification: ScenarioClassification
    quote: MarketQuote
    now: datetime


@dataclass(frozen=True)
class ScenarioTimerStep:
    quote: MarketQuote
    now: datetime


ScenarioStep = Union[ScenarioSourceStep, ScenarioTimerStep]


@dataclass(frozen=True)
class PaperTradingScenario:
    steps: tuple[ScenarioStep, ...]
    ledger_config: PaperLedgerConfig = PaperLedgerConfig()


@dataclass(frozen=True)
class PaperTradingScenarioResult:
    ingestion_results: tuple[IngestionResult, ...]
    orchestrator_results: tuple[OrchestratorResult, ...]
    state: OrchestratorState
    dashboard_status: dict[str, object]

    @property
    def created_ingestion_count(self) -> int:
        return sum(1 for result in self.ingestion_results if result.created)


@dataclass
class PaperTradingScenarioRunner:
    orchestrator: StrategyOrchestrator = field(default_factory=StrategyOrchestrator)
    settings: Settings | None = None

    def run(self, scenario: PaperTradingScenario) -> PaperTradingScenarioResult:
        repository = InMemoryEventRepository()
        queue = InMemoryAnalysisQueue()
        ingestion = IngestionService(repository=repository, analysis_queue=queue)
        state = OrchestratorState(
            ledger=PaperLedger(scenario.ledger_config),
        )
        ingestion_results: list[IngestionResult] = []
        orchestrator_results: list[OrchestratorResult] = []

        for step in scenario.steps:
            if isinstance(step, ScenarioTimerStep):
                timer_result = self.orchestrator.handle_timer(
                    state,
                    quote=step.quote,
                    now=step.now,
                )
                state = timer_result.state
                orchestrator_results.append(timer_result)
                continue

            ingestion_result = _run_async(ingestion.ingest_raw(step.raw_event))
            ingestion_results.append(ingestion_result)
            if not ingestion_result.created or ingestion_result.ingested_event is None:
                continue

            event = ingestion_result.ingested_event.event
            classification = step.classification.for_event(event.id)
            strategy_result = self.orchestrator.handle_classification(
                state,
                event=event,
                classification=classification,
                quote=step.quote,
                now=step.now,
            )
            state = strategy_result.state
            orchestrator_results.append(strategy_result)

        dashboard_status = build_dashboard_status(
            self.settings or load_settings(),
            read_model=_dashboard_read_model(state, self.orchestrator),
        )
        return PaperTradingScenarioResult(
            ingestion_results=tuple(ingestion_results),
            orchestrator_results=tuple(orchestrator_results),
            state=state,
            dashboard_status=dashboard_status,
        )


def _dashboard_read_model(
    state: OrchestratorState,
    orchestrator: StrategyOrchestrator,
) -> dict[str, object]:
    active_hypothesis = state.active_hypothesis
    position = state.ledger.position(orchestrator.lifecycle.config.instrument)
    planned_exits = (
        orchestrator.lifecycle.planned_exits(active_hypothesis)
        if active_hypothesis is not None
        else ()
    )
    return {
        "active_hypothesis": (
            None
            if active_hypothesis is None
            else {
                "id": active_hypothesis.id,
                "state": active_hypothesis.state.value,
                "created_at": active_hypothesis.created_at,
                "thesis": active_hypothesis.thesis,
                "direction": active_hypothesis.direction.value,
                "confidence": active_hypothesis.confidence,
                "evidence": list(active_hypothesis.source_event_ids),
                "norwegian_confirmation": {
                    "status": (
                        "confirmed"
                        if active_hypothesis.norwegian_confirmation_at is not None
                        else "waiting"
                    ),
                    "first_seen_at": active_hypothesis.norwegian_confirmation_at,
                },
            }
        ),
        "position": {
            "instrument": position.instrument,
            "quantity": position.quantity,
            "average_entry_price": position.average_entry_price,
            "realized_pnl": position.realized_pnl,
        },
        "valuation": _valuation_dict(state),
        "planned_exits": [
            {
                "window_minutes": exit.window_minutes,
                "anchor": exit.anchor,
                "scheduled_for": exit.scheduled_for,
                "status": exit.status,
            }
            for exit in planned_exits
        ],
        "risk_decisions": _risk_decision_dicts(state.audit_events),
        "audit_timeline": [
            {
                "timestamp": event.created_at,
                "type": event.action,
                "severity": "info",
                "source": event.payload.get("source"),
                "title": event.summary,
                "entity_id": event.event_id or event.order_id or event.hypothesis_id,
            }
            for event in state.audit_events
        ],
    }


def _valuation_dict(state: OrchestratorState) -> dict[str, object]:
    valuation = state.last_valuation
    if valuation is None:
        return {}
    return {
        "instrument": valuation.instrument,
        "quantity": valuation.quantity,
        "average_entry_price": valuation.average_entry_price,
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
    }


def _risk_decision_dicts(events: Iterable[object]) -> list[dict[str, object]]:
    rows = []
    for event in events:
        payload = getattr(event, "payload", {})
        if not isinstance(payload, dict) or "status" not in payload:
            continue
        rows.append(
            {
                "timestamp": getattr(event, "created_at", None),
                "status": payload.get("status"),
                "reason": payload.get("reason"),
                "side": payload.get("side"),
                "instrument": payload.get("instrument"),
                "aum_pct": payload.get("aum_pct"),
            }
        )
    return rows


def _run_async(awaitable: object) -> object:
    import asyncio

    return asyncio.run(awaitable)


def quote(
    *,
    price: str,
    observed_at: datetime,
    instrument: str = "EQNR.OL",
    source: str = "scenario",
) -> MarketQuote:
    return MarketQuote(
        instrument=instrument,
        last_price=Decimal(price),
        currency="NOK",
        source=source,
        observed_at=observed_at,
    )
