from __future__ import annotations

import asyncio
import unittest

from qualstocks.domain import SourceCategory, SourceTier
from qualstocks.ingestion.idempotency import build_idempotency_key
from qualstocks.sources import (
    KalshiAdapter,
    KalshiEnvironment,
    KalshiEventNormalizer,
    KalshiEventType,
    KalshiMarket,
)


class FakeKalshiSigner:
    def __init__(self):
        self.calls = []

    def authentication_headers(self, *, method, path, timestamp_ms=None):
        self.calls.append((method, path, timestamp_ms))
        return {
            "KALSHI-ACCESS-KEY": "key-id",
            "KALSHI-ACCESS-SIGNATURE": "signed",
            "KALSHI-ACCESS-TIMESTAMP": "1782753357257",
        }


class FakeKalshiStreamClient:
    def __init__(self, raw_events, fail_once: bool = False):
        self.raw_events = tuple(raw_events)
        self.fail_once = fail_once
        self.calls = 0

    async def subscribe(self, *, url, channels, market_tickers, auth_headers):
        self.calls += 1
        self.last_url = url
        self.last_channels = channels
        self.last_market_tickers = market_tickers
        self.last_auth_headers = auth_headers
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("temporary websocket disconnect")
        for raw_event in self.raw_events:
            yield raw_event


class KalshiNormalizerTest(unittest.TestCase):
    def setUp(self):
        self.normalizer = KalshiEventNormalizer()
        self.market = KalshiMarket(
            ticker="KXHORMUZ-26JUL-T",
            title="Will the Strait of Hormuz close this week?",
            subtitle="Oil shipping disruption",
            category="Geopolitics",
            tags=("Iran", "Oil"),
        )

    def test_ticker_baseline_then_delta_emits_event(self):
        first = self.normalizer.normalize(
            {
                "type": "ticker",
                "msg": {
                    "market_ticker": "KXHORMUZ-26JUL-T",
                    "yes_bid": 31,
                    "yes_ask": 33,
                    "ts": 1782753357257,
                },
            },
            market=self.market,
        )
        second = self.normalizer.normalize(
            {
                "type": "ticker",
                "msg": {
                    "market_ticker": "KXHORMUZ-26JUL-T",
                    "yes_bid": 43,
                    "yes_ask": 44,
                    "volume": 1000,
                    "ts": 1782753358257,
                },
            },
            market=self.market,
        )

        self.assertEqual(first, ())
        self.assertEqual(len(second), 1)
        event = second[0]
        self.assertEqual(event.source_id, "kalshi")
        self.assertEqual(event.source_tier, SourceTier.TRIGGER)
        self.assertEqual(event.source_category, SourceCategory.PREDICTION_MARKET)
        self.assertEqual(event.payload["kalshi_event_type"], KalshiEventType.TICKER.value)
        self.assertAlmostEqual(event.payload["probability"], 0.43)
        self.assertAlmostEqual(event.payload["previous_probability"], 0.31)
        self.assertAlmostEqual(event.payload["probability_delta"], 0.12)

    def test_ticker_above_probability_threshold_triggers_immediately(self):
        events = self.normalizer.normalize(
            {
                "type": "ticker",
                "msg": {
                    "market_ticker": "KXHORMUZ-26JUL-T",
                    "last_price": 52,
                    "ts": "1782753357257",
                },
            },
            market=self.market,
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].payload["probability"], 0.52)

    def test_trade_count_can_trigger_below_probability_threshold(self):
        events = self.normalizer.normalize(
            {
                "type": "trade",
                "msg": {
                    "market_ticker": "KXHORMUZ-26JUL-T",
                    "yes_price": 22,
                    "count": 250,
                    "taker_side": "yes",
                    "trade_id": "trade-123",
                    "ts": "2026-07-27T12:00:00Z",
                },
            },
            market=self.market,
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].payload["trade_id"], "trade-123")
        self.assertEqual(events[0].payload["count"], 250.0)

    def test_market_lifecycle_event_is_normalized(self):
        events = self.normalizer.normalize(
            {
                "type": "market_lifecycle_v2",
                "msg": {
                    "market_ticker": "KXHORMUZ-26JUL-T",
                    "event_ticker": "KXHORMUZ",
                    "status": "open",
                    "ts": 1782753357,
                },
            },
            market=self.market,
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(
            events[0].payload["kalshi_event_type"],
            KalshiEventType.MARKET_LIFECYCLE.value,
        )
        self.assertEqual(events[0].payload["status"], "open")

    def test_irrelevant_market_is_ignored(self):
        market = KalshiMarket(
            ticker="KXBASEBALL-26JUL-T",
            title="Will a baseball team win tonight?",
        )
        events = self.normalizer.normalize(
            {
                "type": "ticker",
                "msg": {"market_ticker": "KXBASEBALL-26JUL-T", "yes_bid": 80},
            },
            market=market,
        )

        self.assertEqual(events, ())

    def test_idempotency_key_is_stable_for_same_raw_reference(self):
        raw_event = {
            "type": "trade",
            "msg": {
                "market_ticker": "KXHORMUZ-26JUL-T",
                "yes_price": 22,
                "count": 250,
                "trade_id": "trade-123",
                "ts": 1782753357257,
            },
        }

        first = self.normalizer.normalize(raw_event, market=self.market)[0]
        second = self.normalizer.normalize(raw_event, market=self.market)[0]

        self.assertEqual(build_idempotency_key(first), build_idempotency_key(second))

    def test_adapter_sends_signed_subscription_context(self):
        client = FakeKalshiStreamClient(
            [
                {
                    "type": "trade",
                    "msg": {
                        "market_ticker": "KXHORMUZ-26JUL-T",
                        "yes_price": 50,
                        "count": 250,
                    },
                }
            ]
        )
        signer = FakeKalshiSigner()
        adapter = KalshiAdapter(
            market_tickers=("KXHORMUZ-26JUL-T",),
            markets_by_ticker={"KXHORMUZ-26JUL-T": self.market},
            stream_client=client,
            signer=signer,
            environment=KalshiEnvironment.PRODUCTION,
        )

        async def collect():
            await adapter.start()
            events = [event async for event in adapter.events()]
            await adapter.stop()
            return events

        events = asyncio.run(collect())

        self.assertEqual(len(events), 1)
        self.assertEqual(signer.calls, [("GET", "/trade-api/ws/v2", None)])
        self.assertEqual(
            client.last_url,
            "wss://external-api-ws.kalshi.com/trade-api/ws/v2",
        )
        self.assertIn(KalshiEventType.TICKER.value, client.last_channels)
        self.assertEqual(client.last_market_tickers, ("KXHORMUZ-26JUL-T",))
        self.assertEqual(client.last_auth_headers["KALSHI-ACCESS-KEY"], "key-id")

    def test_adapter_reconnects_after_stream_error(self):
        client = FakeKalshiStreamClient(
            [
                {
                    "type": "trade",
                    "msg": {
                        "market_ticker": "KXHORMUZ-26JUL-T",
                        "yes_price": 50,
                        "count": 250,
                    },
                }
            ],
            fail_once=True,
        )
        adapter = KalshiAdapter(
            market_tickers=("KXHORMUZ-26JUL-T",),
            markets_by_ticker={"KXHORMUZ-26JUL-T": self.market},
            stream_client=client,
            signer=FakeKalshiSigner(),
            reconnect_backoff_seconds=0,
        )

        async def collect():
            await adapter.start()
            events = [event async for event in adapter.events()]
            await adapter.stop()
            return events

        events = asyncio.run(collect())

        self.assertEqual(len(events), 1)
        self.assertEqual(client.calls, 2)


if __name__ == "__main__":
    unittest.main()
