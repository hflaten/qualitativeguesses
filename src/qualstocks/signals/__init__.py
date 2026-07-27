"""Signal composites that convert source events into strategy-ready inputs."""

from qualstocks.signals.hormuz import (
    HormuzClosureAssessment,
    HormuzClosureSignal,
    HormuzClosureState,
)
from qualstocks.signals.control_policy import (
    ControlSignalDecision,
    ControlSignalEffect,
    decide_control_signal_effect,
)

__all__ = [
    "ControlSignalDecision",
    "ControlSignalEffect",
    "HormuzClosureAssessment",
    "HormuzClosureSignal",
    "HormuzClosureState",
    "decide_control_signal_effect",
]
