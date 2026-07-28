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
from qualstocks.paper.ledger import (
    MarketQuote,
    PaperFill,
    PaperLedger,
    PaperLedgerConfig,
    PaperOrder,
    PaperOrderStatus,
    PaperPosition,
    PortfolioValuation,
    QuoteFreshness,
)

__all__ = [
    "BacktestCase",
    "ExitAnchor",
    "ExitBacktestConfig",
    "ExitBacktestResult",
    "ExitVariantResult",
    "MarketQuote",
    "NorwegianConfirmationStatus",
    "PaperFill",
    "PaperLedger",
    "PaperLedgerConfig",
    "PaperOrder",
    "PaperOrderStatus",
    "PaperPosition",
    "PricePoint",
    "PortfolioValuation",
    "QuoteFreshness",
    "run_exit_backtest",
]
