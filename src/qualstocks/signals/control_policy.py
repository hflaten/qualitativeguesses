from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from qualstocks.domain import ActiveHypothesis, SourceEvent, SourceTier


class StrEnum(str, Enum):
    pass


class ControlSignalEffect(StrEnum):
    ANNOTATE_ONLY = "annotate_only"
    STRENGTHEN_ACTIVE = "strengthen_active"
    WEAKEN_ACTIVE = "weaken_active"
    SUPPRESS_ACTIVE = "suppress_active"
    IGNORE = "ignore"


@dataclass(frozen=True)
class ControlSignalDecision:
    effect: ControlSignalEffect
    reason: str
    opens_new_hypothesis: bool = False


def decide_control_signal_effect(
    event: SourceEvent,
    active_hypothesis: ActiveHypothesis | None,
) -> ControlSignalDecision:
    if event.source_tier != SourceTier.CONTROL:
        return ControlSignalDecision(
            effect=ControlSignalEffect.IGNORE,
            reason="Event is not a control signal.",
        )

    action = event.payload.get("control_signal_action")
    if active_hypothesis is None:
        return ControlSignalDecision(
            effect=ControlSignalEffect.ANNOTATE_ONLY,
            reason="Control signal cannot open a new hypothesis by itself.",
            opens_new_hypothesis=False,
        )

    if action == "strengthen":
        return ControlSignalDecision(
            effect=ControlSignalEffect.STRENGTHEN_ACTIVE,
            reason="Control signal strengthens the active hypothesis.",
        )
    if action == "weaken":
        return ControlSignalDecision(
            effect=ControlSignalEffect.WEAKEN_ACTIVE,
            reason="Control signal weakens the active hypothesis.",
        )
    if action == "suppress":
        return ControlSignalDecision(
            effect=ControlSignalEffect.SUPPRESS_ACTIVE,
            reason="Control signal suppresses the active hypothesis.",
        )
    return ControlSignalDecision(
        effect=ControlSignalEffect.ANNOTATE_ONLY,
        reason="Control signal annotates the active hypothesis.",
    )
