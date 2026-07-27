"""Paper-trading simulation and backtest primitives."""

from qualstocks.paper.backtest import (
    BacktestCase,
    ExitAnchor,
    ExitBacktestConfig,
    ExitBacktestResult,
    ExitVariantResult,
    NorwegianConfirmationStatus,
    PricePoint,
    run_exit_backtest,
)

__all__ = [
    "BacktestCase",
    "ExitAnchor",
    "ExitBacktestConfig",
    "ExitBacktestResult",
    "ExitVariantResult",
    "NorwegianConfirmationStatus",
    "PricePoint",
    "run_exit_backtest",
]
