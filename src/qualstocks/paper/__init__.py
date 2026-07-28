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
from qualstocks.paper.quotes import (
    HttpxJsonFetchClient,
    JsonFetchClient,
    NullQuoteProvider,
    QuoteProvider,
    QuoteProviderConfig,
    YahooChartQuoteProvider,
    build_quote_provider,
)

__all__ = [
    "BacktestCase",
    "ExitAnchor",
    "ExitBacktestConfig",
    "ExitBacktestResult",
    "ExitVariantResult",
    "HttpxJsonFetchClient",
    "JsonFetchClient",
    "MarketQuote",
    "NorwegianConfirmationStatus",
    "NullQuoteProvider",
    "PaperFill",
    "PaperLedger",
    "PaperLedgerConfig",
    "PaperOrder",
    "PaperOrderStatus",
    "PaperPosition",
    "PricePoint",
    "QuoteProvider",
    "QuoteProviderConfig",
    "PortfolioValuation",
    "QuoteFreshness",
    "YahooChartQuoteProvider",
    "build_quote_provider",
    "run_exit_backtest",
]
