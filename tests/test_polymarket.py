from __future__ import annotations

import asyncio
import unittest

from qualstocks.domain import SourceCategory, SourceTier
from qualstocks.ingestion.idempotency import build_idempotency_key
from qualstocks.sources import (
    PolymarketAdapter,
    PolymarketEventNormalizer,
    PolymarketEventType,
    PolymarketMarket,
)


class FakePolymarketStreamClient:
    def __init__(self, raw_events, fail_once: bool = False):
        self.raw_events = tuple(raw_events)
        self.fail_once = fail_once
        self.calls = 0

    async def subscribe_market(self, token_ids, *, custom_feature_enabled):
        self.calls += 1
        self.last_token_ids = token_ids
        self.last_custom_feature_enabled = custom_feature_enabled
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("temporary websocket disconnect")
        for raw_event in self.raw_events:
            yield raw_event


class PolymarketNormalizerTest(unittest.TestCase):
    def setUp(self):
        self.normalizer = PolymarketEventNormalizer()
        self.market = PolymarketMarket(
            market_id="0xmarket",
            question="Will the Strait of Hormuz close this week?",
            slug="will-the-strait-of-hormuz-close-this-week",
            token_ids=("yes-token", "no-token"),
            outcomes=("Yes", "No"),
            tags=("Iran", "Oil"),
        )

    def test_new_market_relevant_keywords_emit_event(self):
        events = self.normalizer.normalize(
            {
                "topic": "market",
                "type": "new_market",
                "payload": {
                    "id": "123",
                    "market": "0xmarket",
                    "question": "Will the Strait of Hormuz close this week?",
                    "slug": "will-the-strait-of-hormuz-close-this-week",
                    "tokenIds": ["yes-token", "no-token"],
                    "outcomes": ["Yes", "No"],
                    "tags": ["Iran", "Oil"],
                    "timestamp": "1782753357257",
                },
            }
        )

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.source_id, "polymarket")
        self.assertEqual(event.source_tier, SourceTier.TRIGGER)
        self.assertEqual(event.source_category, SourceCategory.PREDICTION_MARKET)
        self.assertEqual(event.payload["polymarket_event_type"], PolymarketEventType.NEW_MARKET)
        self.assertEqual(event.payload["market_slug"], "will-the-strait-of-hormuz-close-this-week")

    def test_irrelevant_new_market_is_ignored(self):
        events = self.normalizer.normalize(
            {
                "topic": "market",
                "type": "new_market",
                "payload": {
                    "id": "123",
                    "question": "Will a football team win this weekend?",
                    "slug": "football-market",
                    "tokenIds": ["yes-token"],
                },
            }
        )

        self.assertEqual(events, ())

    def test_price_change_requires_threshold_after_baseline(self):
        first = self.normalizer.normalize(
            {
                "topic": "market",
                "type": "price_change",
                "payload": {
                    "market": "0xmarket",
                    "priceChanges": [
                        {"tokenId": "yes-token", "price": "0.31", "size": "20", "side": "BUY"}
                    ],
                    "timestamp": "1782753357257",
                },
            },
            market=self.market,
        )
        second = self.normalizer.normalize(
            {
                "topic": "market",
                "type": "price_change",
                "payload": {
                    "market": "0xmarket",
                    "priceChanges": [
                        {
                            "tokenId": "yes-token",
                            "price": "0.43",
                            "size": "20",
                            "side": "BUY",
                            "bestBid": "0.42",
                            "bestAsk": "0.44",
                        }
                    ],
                    "timestamp": "1782753358257",
                },
            },
            market=self.market,
        )

        self.assertEqual(first, ())
        self.assertEqual(len(second), 1)
        self.assertAlmostEqual(second[0].payload["probability"], 0.43)
        self.assertAlmostEqual(second[0].payload["previous_probability"], 0.31)
        self.assertAlmostEqual(second[0].payload["probability_delta"], 0.12)

    def test_price_change_above_probability_threshold_triggers_immediately(self):
        events = self.normalizer.normalize(
            {
                "topic": "market",
                "type": "price_change",
                "payload": {
                    "market": "0xmarket",
                    "priceChanges": [
                        {"tokenId": "yes-token", "price": "0.51", "size": "20", "side": "BUY"}
                    ],
                },
            },
            market=self.market,
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].payload["probability"], 0.51)

    def test_last_trade_price_triggers_on_trade_size(self):
        events = self.normalizer.normalize(
            {
                "topic": "market",
                "type": "last_trade_price",
                "payload": {
                    "market": "0xmarket",
                    "tokenId": "yes-token",
                    "price": "0.22",
                    "size": "250",
                    "side": "BUY",
                    "transactionHash": "0xabc",
                },
            },
            market=self.market,
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].payload["transaction_hash"], "0xabc")

    def test_best_bid_ask_midpoint_can_trigger(self):
        self.normalizer.normalize(
            {
                "topic": "market",
                "type": "best_bid_ask",
                "payload": {
                    "market": "0xmarket",
                    "tokenId": "yes-token",
                    "bestBid": "0.30",
                    "bestAsk": "0.32",
                },
            },
            market=self.market,
        )

        events = self.normalizer.normalize(
            {
                "topic": "market",
                "type": "best_bid_ask",
                "payload": {
                    "market": "0xmarket",
                    "tokenId": "yes-token",
                    "bestBid": "0.43",
                    "bestAsk": "0.45",
                },
            },
            market=self.market,
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].payload["probability"], 0.44)

    def test_market_resolved_event_is_normalized(self):
        events = self.normalizer.normalize(
            {
                "topic": "market",
                "type": "market_resolved",
                "payload": {
                    "id": "123",
                    "market": "0xmarket",
                    "winningTokenId": "yes-token",
                    "winningOutcome": "Yes",
                    "timestamp": "1782753357257",
                },
            },
            market=self.market,
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(
            events[0].payload["polymarket_event_type"],
            PolymarketEventType.MARKET_RESOLVED,
        )
        self.assertEqual(events[0].payload["winning_outcome"], "Yes")

    def test_idempotency_key_is_stable_for_same_raw_reference(self):
        raw_event = {
            "topic": "market",
            "type": "last_trade_price",
            "payload": {
                "market": "0xmarket",
                "tokenId": "yes-token",
                "price": "0.22",
                "size": "250",
                "side": "BUY",
                "timestamp": "1782753357257",
            },
        }

        first = self.normalizer.normalize(raw_event, market=self.market)[0]
        second = self.normalizer.normalize(raw_event, market=self.market)[0]

        self.assertEqual(build_idempotency_key(first), build_idempotency_key(second))

    def test_adapter_subscribes_with_custom_market_features(self):
        client = FakePolymarketStreamClient(
            [
                {
                    "topic": "market",
                    "type": "last_trade_price",
                    "payload": {
                        "market": "0xmarket",
                        "tokenId": "yes-token",
                        "price": "0.5",
                        "size": "250",
                        "side": "BUY",
                    },
                }
            ]
        )
        adapter = PolymarketAdapter(
            token_ids=("yes-token",),
            markets_by_token_id={"yes-token": self.market},
            stream_client=client,
        )

        async def collect():
            await adapter.start()
            events = [event async for event in adapter.events()]
            await adapter.stop()
            return events

        events = asyncio.run(collect())

        self.assertEqual(len(events), 1)
        self.assertEqual(client.last_token_ids, ("yes-token",))
        self.assertTrue(client.last_custom_feature_enabled)

    def test_adapter_reconnects_after_stream_error(self):
        client = FakePolymarketStreamClient(
            [
                {
                    "topic": "market",
                    "type": "last_trade_price",
                    "payload": {
                        "market": "0xmarket",
                        "tokenId": "yes-token",
                        "price": "0.5",
                        "size": "250",
                        "side": "BUY",
                    },
                }
            ],
            fail_once=True,
        )
        adapter = PolymarketAdapter(
            token_ids=("yes-token",),
            markets_by_token_id={"yes-token": self.market},
            stream_client=client,
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
