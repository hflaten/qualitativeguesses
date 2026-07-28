from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from qualstocks.domain import EventClassification, SourceEvent
from qualstocks.ingestion import PaperTradingRepository, PersistenceResult
from qualstocks.paper import MarketQuote, PaperLedger
from qualstocks.strategy.lifecycle import (
    HypothesisLifecycleConfig,
    HypothesisLifecycleEngine,
    HypothesisTransitionAction,
)
from qualstocks.strategy.orchestrator import (
    OrchestratorResult,
    OrchestratorState,
    StrategyOrchestrator,
)
from qualstocks.settings import Settings
from qualstocks.strategy.risk import RiskGate, RiskGateConfig, TradingMode


@dataclass(frozen=True)
class StrategyClassificationResult:
    orchestrator_result: OrchestratorResult
    persistence_results: tuple[PersistenceResult, ...]


@dataclass(frozen=True)
class PaperStrategyService:
    repository: PaperTradingRepository
    orchestrator: StrategyOrchestrator
    paper_trading_only: bool = True

    def handle_completed_classification(
        self,
        *,
        event: SourceEvent,
        classification: EventClassification,
        quote: MarketQuote | None,
        now: datetime | None = None,
    ) -> StrategyClassificationResult:
        if not self.paper_trading_only:
            raise RuntimeError("strategy worker refuses non-paper trading mode")

        timestamp = now or datetime.now(timezone.utc)
        state = OrchestratorState(
            active_hypothesis=self.repository.active_hypothesis(),
            ledger=PaperLedger(),
        )
        result = self.orchestrator.handle_classification(
            state,
            event=event,
            classification=classification,
            quote=quote,
            now=timestamp,
        )
        persistence_results = self._persist_result(event, classification, result)
        return StrategyClassificationResult(
            orchestrator_result=result,
            persistence_results=tuple(persistence_results),
        )

    def _persist_result(
        self,
        event: SourceEvent,
        classification: EventClassification,
        result: OrchestratorResult,
    ) -> list[PersistenceResult]:
        persistence_results: list[PersistenceResult] = []
        hypothesis = result.state.active_hypothesis
        if (
            hypothesis is not None
            and result.lifecycle_decision.action != HypothesisTransitionAction.IGNORE
        ):
            persistence_results.append(self.repository.persist_hypothesis(hypothesis))

        hypothesis_id = hypothesis.id if hypothesis is not None else None
        for index, decision in enumerate(result.risk_decisions):
            order_id = result.orders[index].id if index < len(result.orders) else None
            persistence_results.append(
                self.repository.persist_risk_decision(
                    decision,
                    idempotency_key=_risk_key(event, classification, index),
                    hypothesis_id=hypothesis_id,
                    event_id=event.id,
                    order_id=order_id,
                )
            )
        if hypothesis_id is not None and result.orders:
            for order in result.orders:
                persistence_results.append(
                    self.repository.persist_paper_order(
                        order,
                        hypothesis_id=hypothesis_id,
                        idempotency_key=_order_key(hypothesis_id, order.source_event_id, order.id),
                    )
                )
            for fill in result.fills:
                persistence_results.append(
                    self.repository.persist_paper_fill(
                        fill,
                        idempotency_key=_fill_key(hypothesis_id, fill.order_id, fill.id),
                    )
                )
            position = result.state.ledger.position(self.orchestrator.lifecycle.config.instrument)
            persistence_results.append(
                self.repository.persist_position_snapshot(
                    position,
                    hypothesis_id=hypothesis_id,
                    opened_at=hypothesis.created_at,
                    updated_at=result.valuation.quote_observed_at if result.valuation else None,
                )
            )
            if result.valuation is not None:
                persistence_results.append(
                    self.repository.persist_valuation_snapshot(
                        result.valuation,
                        hypothesis_id=hypothesis_id,
                        idempotency_key=_valuation_key(hypothesis_id, event.id),
                    )
                )

        persistence_results.extend(
            self.repository.persist_orchestrator_audit_events(
                result.audit_events,
                idempotency_prefix=_audit_prefix(event, classification),
            )
        )
        return persistence_results


def build_paper_strategy_service(
    settings: Settings,
    repository: PaperTradingRepository,
) -> PaperStrategyService:
    lifecycle_config = HypothesisLifecycleConfig(
        instrument=settings.quote_instrument,
        initial_aum_pct=settings.tranche_one_aum_pct,
        reinforcement_aum_pct=settings.tranche_two_aum_pct,
        exit_windows_minutes=settings.exit_windows_minutes,
    )
    risk_config = RiskGateConfig(
        mode=TradingMode.PAPER,
        deployment_environment=settings.app_env,
        live_trading_enabled=settings.live_trading_enabled,
        max_single_name_exposure_pct=settings.risk_max_single_name_exposure_pct,
        max_event_exposure_pct=settings.risk_max_event_exposure_pct,
        max_daily_loss_pct=settings.risk_max_daily_loss_pct,
        max_open_hypotheses=settings.max_open_hypotheses,
        live_max_order_aum_pct=settings.risk_live_max_order_aum_pct,
    )
    return PaperStrategyService(
        repository=repository,
        orchestrator=StrategyOrchestrator(
            lifecycle=HypothesisLifecycleEngine(config=lifecycle_config),
            risk_gate=RiskGate(risk_config),
        ),
        paper_trading_only=settings.paper_trading_only,
    )


def _risk_key(event: SourceEvent, classification: EventClassification, index: int) -> str:
    return f"risk:{event.id}:{classification.event_type}:{index}"


def _order_key(hypothesis_id: str, event_id: str | None, order_id: str) -> str:
    return f"order:{hypothesis_id}:{event_id or 'timer'}:{order_id}"


def _fill_key(hypothesis_id: str, order_id: str, fill_id: str) -> str:
    return f"fill:{hypothesis_id}:{order_id}:{fill_id}"


def _valuation_key(hypothesis_id: str, event_id: str) -> str:
    return f"valuation:{hypothesis_id}:{event_id}"


def _audit_prefix(event: SourceEvent, classification: EventClassification) -> str:
    return f"strategy:{event.id}:{classification.event_type}"
