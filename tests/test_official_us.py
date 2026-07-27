from __future__ import annotations

import asyncio
import unittest

from qualstocks.domain import SourceCategory, SourceTier
from qualstocks.ingestion.idempotency import build_idempotency_key
from qualstocks.sources import (
    DEFAULT_SOURCE_REGISTRY,
    KeywordFilter,
    RssFeedNormalizer,
    build_centcom_rss_adapter,
    build_dod_rss_adapter,
    build_official_us_rss_adapters,
)


RSS_FIXTURE = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>Official Feed</title>
    <item>
      <title>CENTCOM statement on Strait of Hormuz tanker incident</title>
      <link>https://example.invalid/centcom/hormuz</link>
      <guid>centcom-hormuz-1</guid>
      <pubDate>Mon, 27 Jul 2026 15:30:00 GMT</pubDate>
      <description>U.S. forces are monitoring a tanker incident near Hormuz.</description>
    </item>
    <item>
      <title>Community volunteer day announced</title>
      <link>https://example.invalid/community</link>
      <guid>community-1</guid>
      <pubDate>Mon, 27 Jul 2026 15:31:00 GMT</pubDate>
      <description>Unrelated local community item.</description>
    </item>
  </channel>
</rss>
"""


class FakeTextFetchClient:
    def __init__(self, text: str):
        self.text = text
        self.urls: list[str] = []

    async def get_text(self, url: str) -> str:
        self.urls.append(url)
        return self.text


class OfficialUsAdapterTest(unittest.TestCase):
    def test_rss_normalizer_filters_and_preserves_source_metadata(self):
        source_definition = DEFAULT_SOURCE_REGISTRY.require("centcom_rss")
        normalizer = RssFeedNormalizer(
            source_definition=source_definition,
            keyword_filter=KeywordFilter(("hormuz", "iran")),
        )

        events = normalizer.normalize(RSS_FIXTURE)

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.source_id, "centcom_rss")
        self.assertEqual(event.source_tier, SourceTier.TRIGGER)
        self.assertEqual(event.source_category, SourceCategory.OFFICIAL_US)
        self.assertEqual(event.raw_event_ref, "centcom-hormuz-1")
        self.assertEqual(event.payload["guid"], "centcom-hormuz-1")
        self.assertEqual(event.source_timestamp.year, 2026)

    def test_rss_event_idempotency_uses_canonical_guid_and_published_at(self):
        source_definition = DEFAULT_SOURCE_REGISTRY.require("dod_rss")
        normalizer = RssFeedNormalizer(
            source_definition=source_definition,
            keyword_filter=KeywordFilter(("hormuz",)),
        )

        first = normalizer.normalize(RSS_FIXTURE)[0]
        second = normalizer.normalize(RSS_FIXTURE)[0]

        self.assertEqual(build_idempotency_key(first), build_idempotency_key(second))

    def test_dod_adapter_fetches_source_url_and_yields_filtered_events(self):
        client = FakeTextFetchClient(RSS_FIXTURE)
        adapter = build_dod_rss_adapter(fetch_client=client)

        async def collect():
            await adapter.start()
            events = [event async for event in adapter.events()]
            await adapter.stop()
            return events

        events = asyncio.run(collect())

        self.assertEqual(len(events), 1)
        self.assertEqual(client.urls, ["https://www.defense.gov/news/rss"])
        self.assertEqual(events[0].source_id, "dod_rss")

    def test_centcom_adapter_uses_centcom_source_definition(self):
        client = FakeTextFetchClient(RSS_FIXTURE)
        adapter = build_centcom_rss_adapter(fetch_client=client)

        async def collect():
            await adapter.start()
            events = [event async for event in adapter.events()]
            await adapter.stop()
            return events

        events = asyncio.run(collect())

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].source_id, "centcom_rss")
        self.assertEqual(events[0].reliability_score, 0.92)

    def test_official_us_builder_returns_dod_and_centcom_adapters(self):
        client = FakeTextFetchClient(RSS_FIXTURE)
        adapters = build_official_us_rss_adapters(fetch_client=client)

        self.assertEqual(tuple(adapter.source_definition.source_id for adapter in adapters), (
            "dod_rss",
            "centcom_rss",
        ))


if __name__ == "__main__":
    unittest.main()
