from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import Enum

from qualstocks.domain import (
    ActiveHypothesis,
    Direction,
    EventClassification,
    HypothesisState,
    SourceCategory,
    SourceClass,
    SourceEvent,
    SourceTier,
)


class StrEnum(str, Enum):
    pass


class PaperOrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class HypothesisTransitionAction(StrEnum):
    IGNORE = "ignore"
    OPEN_ACTIVE = "open_active"
    REINFORCE = "reinforce"
    CONFIRM_NORWEGIAN = "confirm_norwegian"
    CONTRADICT = "contradict"
    FALLBACK_EXIT = "fallback_exit"
    SCHEDULED_EXIT = "scheduled_exit"


@dataclass(frozen=True)
class PaperOrderIntent:
    side: PaperOrderSide
    instrument: str
    aum_pct: int
    reason: str
    source_event_id: str | None = None


@dataclass(frozen=True)
class PlannedExit:
    window_minutes: int
    anchor: str
    scheduled_for: datetime
    status: str = "scheduled"


@dataclass(frozen=True)
class HypothesisLifecycleConfig:
    instrument: str = "EQNR.OL"
    initial_aum_pct: int = 50
    reinforcement_aum_pct: int = 50
    exit_windows_minutes: tuple[int, ...] = (30, 40, 50)
    fallback_exit_minutes: int = 90
    min_open_confidence: float = 0.65

    def __post_init__(self) -> None:
        if self.initial_aum_pct <= 0 or self.initial_aum_pct > 100:
            raise ValueError("initial_aum_pct must be between 1 and 100")
        if self.reinforcement_aum_pct <= 0 or self.reinforcement_aum_pct > 100:
            raise ValueError("reinforcement_aum_pct must be between 1 and 100")
        if self.initial_aum_pct + self.reinforcement_aum_pct > 100:
            raise ValueError("configured staged allocation cannot exceed 100 pct AUM")
        if not self.exit_windows_minutes:
            raise ValueError("at least one exit window is required")
        if any(window <= 0 for window in self.exit_windows_minutes):
            raise ValueError("exit windows must be positive")
        if self.fallback_exit_minutes <= 0:
            raise ValueError("fallback_exit_minutes must be positive")
        if not 0 <= self.min_open_confidence <= 1:
            raise ValueError("min_open_confidence must be between 0 and 1")


@dataclass(frozen=True)
class HypothesisLifecycleDecision:
    action: HypothesisTransitionAction
    reason: str
    hypothesis: ActiveHypothesis | None
    paper_order_intents: tuple[PaperOrderIntent, ...] = ()
    planned_exits: tuple[PlannedExit, ...] = ()
    audit_actions: tuple[str, ...] = ()


@dataclass(frozen=True)
class HypothesisLifecycleEngine:
    config: HypothesisLifecycleConfig = field(default_factory=HypothesisLifecycleConfig)

    def apply_event(
        self,
        *,
        active_hypothesis: ActiveHypothesis | None,
        event: SourceEvent,
        classification: EventClassification,
        now: datetime | None = None,
    ) -> HypothesisLifecycleDecision:
        decision_time = now or datetime.now(timezone.utc)
        if active_hypothesis is not None:
            contradiction = self._contradicts(active_hypothesis, classification)
            if contradiction:
                return self._contradict(
                    hypothesis=active_hypothesis,
                    event=event,
                    reason=contradiction,
                )
            if norwegian_confirmation_source(event):
                return self._confirm_norwegian(
                    hypothesis=active_hypothesis,
                    event=event,
                    anchor_time=event.first_seen_at,
                )
            if self._reinforces(active_hypothesis, event, classification):
                return self._reinforce(hypothesis=active_hypothesis, event=event)
            return HypothesisLifecycleDecision(
                action=HypothesisTransitionAction.IGNORE,
                reason="Event does not change the active hypothesis.",
                hypothesis=active_hypothesis,
            )

        if not self._can_open_hypothesis(event, classification):
            return HypothesisLifecycleDecision(
                action=HypothesisTransitionAction.IGNORE,
                reason="Event is not a qualifying first signal.",
                hypothesis=None,
            )
        hypothesis = ActiveHypothesis(
            thesis=_thesis_for(classification),
            direction=classification.direction,
            confidence=classification.confidence,
            state=HypothesisState.ACTIVE,
            source_event_ids=(event.id,),
            created_at=decision_time,
        )
        return HypothesisLifecycleDecision(
            action=HypothesisTransitionAction.OPEN_ACTIVE,
            reason="First qualifying trigger opens the paper-trading hypothesis.",
            hypothesis=hypothesis,
            paper_order_intents=(
                PaperOrderIntent(
                    side=PaperOrderSide.BUY,
                    instrument=self.config.instrument,
                    aum_pct=self.config.initial_aum_pct,
                    reason="Initial staged allocation after first qualifying signal.",
                    source_event_id=event.id,
                ),
            ),
            audit_actions=("hypothesis_opened", "paper_order_intent_created"),
        )

    def evaluate_timers(
        self,
        *,
        active_hypothesis: ActiveHypothesis,
        now: datetime | None = None,
    ) -> HypothesisLifecycleDecision:
        decision_time = now or datetime.now(timezone.utc)
        if active_hypothesis.norwegian_confirmation_at is not None:
            for planned_exit in self.planned_exits(active_hypothesis):
                if decision_time >= planned_exit.scheduled_for:
                    exiting = replace(active_hypothesis, state=HypothesisState.EXITING)
                    return HypothesisLifecycleDecision(
                        action=HypothesisTransitionAction.SCHEDULED_EXIT,
                        reason=(
                            f"{planned_exit.window_minutes}-minute exit window reached "
                            "after Norwegian confirmation."
                        ),
                        hypothesis=exiting,
                        paper_order_intents=(self._sell_intent(None, "Scheduled exit timer."),),
                        planned_exits=(planned_exit,),
                        audit_actions=("scheduled_exit_due", "paper_exit_intent_created"),
                    )
            return HypothesisLifecycleDecision(
                action=HypothesisTransitionAction.IGNORE,
                reason="No exit timer is due yet.",
                hypothesis=active_hypothesis,
                planned_exits=self.planned_exits(active_hypothesis),
            )

        fallback_at = active_hypothesis.created_at + timedelta(
            minutes=self.config.fallback_exit_minutes
        )
        if decision_time >= fallback_at:
            exiting = replace(active_hypothesis, state=HypothesisState.EXITING)
            return HypothesisLifecycleDecision(
                action=HypothesisTransitionAction.FALLBACK_EXIT,
                reason="Fallback exit reached before Norwegian confirmation arrived.",
                hypothesis=exiting,
                paper_order_intents=(self._sell_intent(None, "Fallback exit timer."),),
                audit_actions=("fallback_exit_due", "paper_exit_intent_created"),
            )
        return HypothesisLifecycleDecision(
            action=HypothesisTransitionAction.IGNORE,
            reason="Waiting for Norwegian confirmation or fallback exit.",
            hypothesis=active_hypothesis,
        )

    def planned_exits(self, hypothesis: ActiveHypothesis) -> tuple[PlannedExit, ...]:
        if hypothesis.norwegian_confirmation_at is None:
            return ()
        anchor = hypothesis.norwegian_confirmation_at
        return tuple(
            PlannedExit(
                window_minutes=window,
                anchor="norwegian_confirmation",
                scheduled_for=anchor + timedelta(minutes=window),
            )
            for window in self.config.exit_windows_minutes
        )

    def _can_open_hypothesis(
        self,
        event: SourceEvent,
        classification: EventClassification,
    ) -> bool:
        return (
            event.source_tier == SourceTier.TRIGGER
            and classification.relevant_to_equinor
            and classification.direction != Direction.UNCLEAR
            and classification.confidence >= self.config.min_open_confidence
        )

    def _reinforces(
        self,
        hypothesis: ActiveHypothesis,
        event: SourceEvent,
        classification: EventClassification,
    ) -> bool:
        return (
            hypothesis.can_accept_reinforcement()
            and event.id not in hypothesis.source_event_ids
            and event.source_tier in {SourceTier.TRIGGER, SourceTier.CONFIRMATION}
            and classification.relevant_to_equinor
            and classification.direction == hypothesis.direction
            and (classification.is_reinforcement or classification.confidence >= 0.6)
        )

    def _contradicts(
        self,
        hypothesis: ActiveHypothesis,
        classification: EventClassification,
    ) -> str | None:
        if classification.is_contradiction:
            return "Classification explicitly contradicts the active thesis."
        if (
            classification.relevant_to_equinor
            and classification.direction != Direction.UNCLEAR
            and classification.direction != hypothesis.direction
            and classification.confidence >= 0.65
        ):
            return "New evidence points in the opposite Equinor direction."
        return None

    def _reinforce(
        self,
        *,
        hypothesis: ActiveHypothesis,
        event: SourceEvent,
    ) -> HypothesisLifecycleDecision:
        reinforced = replace(
            hypothesis,
            state=HypothesisState.REINFORCED,
            source_event_ids=hypothesis.source_event_ids + (event.id,),
        )
        return HypothesisLifecycleDecision(
            action=HypothesisTransitionAction.REINFORCE,
            reason="Independent signal reinforces the active hypothesis.",
            hypothesis=reinforced,
            paper_order_intents=(
                PaperOrderIntent(
                    side=PaperOrderSide.BUY,
                    instrument=self.config.instrument,
                    aum_pct=self.config.reinforcement_aum_pct,
                    reason="Second staged allocation after independent reinforcement.",
                    source_event_id=event.id,
                ),
            ),
            audit_actions=("hypothesis_reinforced", "paper_order_intent_created"),
        )

    def _confirm_norwegian(
        self,
        *,
        hypothesis: ActiveHypothesis,
        event: SourceEvent,
        anchor_time: datetime,
    ) -> HypothesisLifecycleDecision:
        confirmed = replace(
            hypothesis,
            state=HypothesisState.CONFIRMED_BY_NORWEGIAN_SOURCE,
            norwegian_confirmation_at=anchor_time,
            source_event_ids=(
                hypothesis.source_event_ids
                if event.id in hypothesis.source_event_ids
                else hypothesis.source_event_ids + (event.id,)
            ),
        )
        planned_exits = self.planned_exits(confirmed)
        return HypothesisLifecycleDecision(
            action=HypothesisTransitionAction.CONFIRM_NORWEGIAN,
            reason="Norwegian market-facing source anchors the exit timers.",
            hypothesis=confirmed,
            planned_exits=planned_exits,
            audit_actions=("norwegian_confirmation_recorded", "exit_timers_scheduled"),
        )

    def _contradict(
        self,
        *,
        hypothesis: ActiveHypothesis,
        event: SourceEvent,
        reason: str,
    ) -> HypothesisLifecycleDecision:
        contradicted = replace(
            hypothesis,
            state=HypothesisState.CONTRADICTED,
            source_event_ids=(
                hypothesis.source_event_ids
                if event.id in hypothesis.source_event_ids
                else hypothesis.source_event_ids + (event.id,)
            ),
        )
        return HypothesisLifecycleDecision(
            action=HypothesisTransitionAction.CONTRADICT,
            reason=reason,
            hypothesis=contradicted,
            paper_order_intents=(self._sell_intent(event.id, "Contradiction exit."),),
            audit_actions=("hypothesis_contradicted", "paper_exit_intent_created"),
        )

    def _sell_intent(self, source_event_id: str | None, reason: str) -> PaperOrderIntent:
        return PaperOrderIntent(
            side=PaperOrderSide.SELL,
            instrument=self.config.instrument,
            aum_pct=self.config.initial_aum_pct + self.config.reinforcement_aum_pct,
            reason=reason,
            source_event_id=source_event_id,
        )


def norwegian_confirmation_source(event: SourceEvent) -> bool:
    return event.source_class in {
        SourceClass.NORWEGIAN_CONFIRMATION,
        SourceClass.EQUINOR_OR_EXCHANGE,
    } or event.source_category in {
        SourceCategory.NORWEGIAN_MARKET,
        SourceCategory.NORWEGIAN_PRESS,
    }


def _thesis_for(classification: EventClassification) -> str:
    if classification.reasoning_summary:
        return classification.reasoning_summary
    if classification.direction == Direction.BULLISH_EQUINOR:
        return "US-Iran escalation increases oil supply risk, likely positive for Equinor."
    if classification.direction == Direction.BEARISH_EQUINOR:
        return "US-Iran de-escalation reduces oil supply risk, likely negative for Equinor."
    return "Event may affect Equinor, but direction is unclear."
