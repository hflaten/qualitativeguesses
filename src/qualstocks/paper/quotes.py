from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Protocol
from urllib.parse import urlencode

from qualstocks.paper.ledger import MarketQuote


@dataclass(frozen=True)
class QuoteProviderConfig:
    source: str = "yahoo"
    instrument: str = "EQNR.OL"
    yahoo_symbol: str = "EQNR.OL"
    stale_after_seconds: int = 60
    timeout_seconds: int = 10

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError("source is required")
        if not self.instrument:
            raise ValueError("instrument is required")
        if not self.yahoo_symbol:
            raise ValueError("yahoo_symbol is required")
        if self.stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


class JsonFetchClient(Protocol):
    async def get_json(self, url: str) -> dict[str, object]:
        """Return a decoded JSON response for the provider URL."""


class QuoteProvider(Protocol):
    async def latest(self) -> MarketQuote | None:
        """Return the latest quote, or None when the provider has no usable price."""


@dataclass(frozen=True)
class HttpxJsonFetchClient:
    timeout_seconds: int = 10

    async def get_json(self, url: str) -> dict[str, object]:
        import httpx

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()


@dataclass(frozen=True)
class NullQuoteProvider:
    async def latest(self) -> MarketQuote | None:
        return None


@dataclass(frozen=True)
class YahooChartQuoteProvider:
    config: QuoteProviderConfig = QuoteProviderConfig()
    fetch_client: JsonFetchClient | None = None

    async def latest(self) -> MarketQuote | None:
        client = self.fetch_client or HttpxJsonFetchClient(self.config.timeout_seconds)
        payload = await client.get_json(_yahoo_chart_url(self.config.yahoo_symbol))
        return _parse_yahoo_chart_quote(
            payload,
            instrument=self.config.instrument,
            source=f"yahoo:{self.config.yahoo_symbol}",
        )


def build_quote_provider(
    config: QuoteProviderConfig = QuoteProviderConfig(),
) -> QuoteProvider:
    if config.source.lower() in {"", "none", "disabled"}:
        return NullQuoteProvider()
    if config.source.lower() == "yahoo":
        return YahooChartQuoteProvider(config=config)
    raise ValueError(f"unsupported quote provider source: {config.source}")


def _yahoo_chart_url(symbol: str) -> str:
    query = urlencode({"interval": "1m", "range": "1d"})
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{query}"


def _parse_yahoo_chart_quote(
    payload: dict[str, object],
    *,
    instrument: str,
    source: str,
) -> MarketQuote | None:
    result = _first_result(payload)
    if result is None:
        return None

    meta = _dict(result.get("meta"))
    price = _decimal_or_none(meta.get("regularMarketPrice"))
    if price is None:
        price = _last_close(result)
    if price is None:
        return None

    timestamp = _int_or_none(meta.get("regularMarketTime"))
    if timestamp is None:
        timestamp = _last_timestamp(result)

    return MarketQuote(
        instrument=instrument,
        last_price=price,
        bid=_decimal_or_none(meta.get("bid")),
        ask=_decimal_or_none(meta.get("ask")),
        currency=str(meta.get("currency") or "NOK"),
        source=source,
        observed_at=_observed_at(timestamp),
    )


def _first_result(payload: dict[str, object]) -> dict[str, object] | None:
    chart = _dict(payload.get("chart"))
    results = chart.get("result")
    if not isinstance(results, list) or not results:
        return None
    return _dict(results[0])


def _last_close(result: dict[str, object]) -> Decimal | None:
    indicators = _dict(result.get("indicators"))
    quotes = indicators.get("quote")
    if not isinstance(quotes, list) or not quotes:
        return None
    quote = _dict(quotes[0])
    closes = quote.get("close")
    if not isinstance(closes, list):
        return None
    for value in reversed(closes):
        price = _decimal_or_none(value)
        if price is not None:
            return price
    return None


def _last_timestamp(result: dict[str, object]) -> int | None:
    timestamps = result.get("timestamp")
    if not isinstance(timestamps, list):
        return None
    for value in reversed(timestamps):
        timestamp = _int_or_none(value)
        if timestamp is not None:
            return timestamp
    return None


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _observed_at(timestamp: int | None) -> datetime:
    if timestamp is None:
        return datetime.now(timezone.utc)
    return datetime.fromtimestamp(timestamp, timezone.utc)
