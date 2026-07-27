from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from qualstocks.domain import ActiveHypothesis
from qualstocks.strategy.lifecycle import PaperOrderIntent, PaperOrderSide


class StrEnum(str, Enum):
    pass


class TradingMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


class RiskDecisionStatus(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    FORCED_LIQUIDATION = "forced_liquidation"


@dataclass(frozen=True)
class RiskGateConfig:
    mode: TradingMode = TradingMode.PAPER
    live_trading_enabled: bool = False
    max_single_name_exposure_pct: int = 100
    max_event_exposure_pct: int = 100
    max_daily_loss_pct: int = 5
    max_open_hypotheses: int = 1
    live_max_order_aum_pct: int = 5

    def __post_init__(self) -> None:
        for name, value in (
            ("max_single_name_exposure_pct", self.max_single_name_exposure_pct),
            ("max_event_exposure_pct", self.max_event_exposure_pct),
            ("max_daily_loss_pct", self.max_daily_loss_pct),
            ("max_open_hypotheses", self.max_open_hypotheses),
            ("live_max_order_aum_pct", self.live_max_order_aum_pct),
        ):
            if value < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.max_open_hypotheses < 1:
            raise ValueError("max_open_hypotheses must be at least 1")


@dataclass(frozen=True)
class PortfolioRiskSnapshot:
    single_name_exposure_pct: int = 0
    event_exposure_pct: int = 0
    daily_realized_loss_pct: int = 0
    open_hypotheses: int = 0
    forced_liquidation_required: bool = False


@dataclass(frozen=True)
class RiskGateDecision:
    status: RiskDecisionStatus
    reason: str
    order_intent: PaperOrderIntent
    audit_action: str
    audit_payload: dict[str, object]

    @property
    def approved(self) -> bool:
        return self.status in {
            RiskDecisionStatus.APPROVED,
            RiskDecisionStatus.FORCED_LIQUIDATION,
        }


@dataclass(frozen=True)
class RiskGate:
    config: RiskGateConfig = RiskGateConfig()

    def evaluate_order(
        self,
        *,
        order_intent: PaperOrderIntent,
        snapshot: PortfolioRiskSnapshot,
        active_hypothesis: ActiveHypothesis | None,
        reinforcement: bool = False,
        independent_source_confirmation: bool = False,
        materially_new_information: bool = False,
    ) -> RiskGateDecision:
        if order_intent.side == PaperOrderSide.SELL:
            if snapshot.forced_liquidation_required:
                return self._decision(
                    RiskDecisionStatus.FORCED_LIQUIDATION,
                    "Forced liquidation sell is approved.",
                    order_intent,
                )
            return self._decision(
                RiskDecisionStatus.APPROVED,
                "Sell intent is approved for paper risk reduction.",
                order_intent,
            )

        rejection = self._buy_rejection_reason(
            order_intent=order_intent,
            snapshot=snapshot,
            active_hypothesis=active_hypothesis,
            reinforcement=reinforcement,
            independent_source_confirmation=independent_source_confirmation,
            materially_new_information=materially_new_information,
        )
        if rejection is not None:
            return self._decision(RiskDecisionStatus.REJECTED, rejection, order_intent)
        return self._decision(
            RiskDecisionStatus.APPROVED,
            "Buy intent passes configured paper-trading risk limits.",
            order_intent,
        )

    def _buy_rejection_reason(
        self,
        *,
        order_intent: PaperOrderIntent,
        snapshot: PortfolioRiskSnapshot,
        active_hypothesis: ActiveHypothesis | None,
        reinforcement: bool,
        independent_source_confirmation: bool,
        materially_new_information: bool,
    ) -> str | None:
        if self.config.mode == TradingMode.LIVE and not self.config.live_trading_enabled:
            return "Live trading is disabled by default."
        if self.config.mode == TradingMode.LIVE:
            if order_intent.aum_pct > self.config.live_max_order_aum_pct:
                return "Live order exceeds live-mode max order size."
        if snapshot.forced_liquidation_required:
            return "Forced liquidation is active; new buy intents are rejected."
        if snapshot.daily_realized_loss_pct >= self.config.max_daily_loss_pct:
            return "Daily loss limit has been reached."
        max_open_reached = snapshot.open_hypotheses >= self.config.max_open_hypotheses
        if active_hypothesis is None and max_open_reached:
            return "Max open hypotheses limit has been reached."
        if reinforcement and not (
            independent_source_confirmation or materially_new_information
        ):
            return "Reinforcement requires independent source confirmation or new information."

        projected_single_name = snapshot.single_name_exposure_pct + order_intent.aum_pct
        if projected_single_name > self.config.max_single_name_exposure_pct:
            return "Order would exceed max single-name exposure."

        projected_event = snapshot.event_exposure_pct + order_intent.aum_pct
        if projected_event > self.config.max_event_exposure_pct:
            return "Order would exceed max event exposure."

        return None

    def _decision(
        self,
        status: RiskDecisionStatus,
        reason: str,
        order_intent: PaperOrderIntent,
    ) -> RiskGateDecision:
        audit_action = f"risk_decision_{status.value}"
        return RiskGateDecision(
            status=status,
            reason=reason,
            order_intent=order_intent,
            audit_action=audit_action,
            audit_payload={
                "status": status.value,
                "reason": reason,
                "side": order_intent.side.value,
                "instrument": order_intent.instrument,
                "aum_pct": order_intent.aum_pct,
                "source_event_id": order_intent.source_event_id,
                "order_reason": order_intent.reason,
            },
        )
