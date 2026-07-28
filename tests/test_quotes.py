from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from decimal import Decimal

from qualstocks.paper import (
    NullQuoteProvider,
    QuoteProviderConfig,
    YahooChartQuoteProvider,
    build_quote_provider,
)


class FakeJsonClient:
    def __init__(self, payload: dict[str, object]):
        self.payload = payload
        self.urls: list[str] = []

    async def get_json(self, url: str) -> dict[str, object]:
        self.urls.append(url)
        return self.payload


class QuoteProviderTest(unittest.TestCase):
    def test_yahoo_provider_returns_market_quote_from_meta(self):
        client = FakeJsonClient(
            {
                "chart": {
                    "result": [
                        {
                            "meta": {
                                "regularMarketPrice": 301.25,
                                "regularMarketTime": 1785232800,
                                "currency": "NOK",
                                "bid": 301.2,
                                "ask": 301.3,
                            }
                        }
                    ],
                    "error": None,
                }
            }
        )
        provider = YahooChartQuoteProvider(fetch_client=client)

        quote = asyncio.run(provider.latest())

        self.assertIsNotNone(quote)
        assert quote is not None
        self.assertEqual(quote.instrument, "EQNR.OL")
        self.assertEqual(quote.last_price, Decimal("301.25"))
        self.assertEqual(quote.bid, Decimal("301.2"))
        self.assertEqual(quote.ask, Decimal("301.3"))
        self.assertEqual(quote.currency, "NOK")
        self.assertEqual(quote.source, "yahoo:EQNR.OL")
        self.assertEqual(
            quote.observed_at,
            datetime.fromtimestamp(1785232800, timezone.utc),
        )
        self.assertEqual(
            client.urls,
            ["https://query1.finance.yahoo.com/v8/finance/chart/EQNR.OL?interval=1m&range=1d"],
        )

    def test_yahoo_provider_falls_back_to_last_close_and_timestamp(self):
        client = FakeJsonClient(
            {
                "chart": {
                    "result": [
                        {
                            "meta": {"currency": "NOK"},
                            "timestamp": [1785232740, 1785232800],
                            "indicators": {
                                "quote": [
                                    {
                                        "close": [None, 299.4],
                                    }
                                ]
                            },
                        }
                    ],
                }
            }
        )
        provider = YahooChartQuoteProvider(fetch_client=client)

        quote = asyncio.run(provider.latest())

        self.assertIsNotNone(quote)
        assert quote is not None
        self.assertEqual(quote.last_price, Decimal("299.4"))
        self.assertEqual(
            quote.observed_at,
            datetime.fromtimestamp(1785232800, timezone.utc),
        )

    def test_yahoo_provider_returns_none_for_missing_price(self):
        provider = YahooChartQuoteProvider(fetch_client=FakeJsonClient({"chart": {"result": []}}))

        self.assertIsNone(asyncio.run(provider.latest()))

    def test_build_quote_provider_can_disable_live_quotes(self):
        provider = build_quote_provider(QuoteProviderConfig(source="disabled"))

        self.assertIsInstance(provider, NullQuoteProvider)
        self.assertIsNone(asyncio.run(provider.latest()))

    def test_build_quote_provider_rejects_unknown_source(self):
        with self.assertRaises(ValueError):
            build_quote_provider(QuoteProviderConfig(source="mystery-feed"))


if __name__ == "__main__":
    unittest.main()
