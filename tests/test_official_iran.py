from __future__ import annotations

import asyncio
import unittest

from qualstocks.domain import SourceCategory, SourceTier
from qualstocks.ingestion.idempotency import build_idempotency_key
from qualstocks.sources import (
    DEFAULT_SOURCE_REGISTRY,
    IRAN_SIGNAL_KEYWORDS,
    KeywordFilter,
    RssFeedNormalizer,
    build_official_iran_rss_adapters,
    build_tasnim_rss_adapter,
    iran_source_access_notes,
)


PERSIAN_RSS_FIXTURE = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>Tasnim</title>
    <item>
      <title>ایران درباره تنگه هرمز و نفتکش‌ها هشدار داد</title>
      <link>https://www.tasnimnews.ir/fa/news/1</link>
      <guid>tasnim-fa-hormuz-1</guid>
      <pubDate>Mon, 27 Jul 2026 15:30:00 GMT</pubDate>
      <description>سپاه درباره امنیت خلیج فارس و تنگه هرمز بیانیه داد.</description>
    </item>
    <item>
      <title>گزارش ورزشی روز</title>
      <link>https://www.tasnimnews.ir/fa/news/2</link>
      <guid>tasnim-fa-sport-1</guid>
      <pubDate>Mon, 27 Jul 2026 15:31:00 GMT</pubDate>
      <description>خبر غیرمرتبط ورزشی.</description>
    </item>
  </channel>
</rss>
"""


ENGLISH_RSS_FIXTURE = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>Tasnim English</title>
    <item>
      <title>IRGC warns US over Strait of Hormuz navigation</title>
      <link>https://www.tasnimnews.ir/en/news/1</link>
      <guid>tasnim-en-hormuz-1</guid>
      <pubDate>Mon, 27 Jul 2026 15:35:00 GMT</pubDate>
      <description>Iran says tanker traffic may be affected by US actions.</description>
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


class OfficialIranAdapterTest(unittest.TestCase):
    def test_tasnim_persian_rss_preserves_translation_metadata(self):
        source_definition = DEFAULT_SOURCE_REGISTRY.require("tasnim")
        normalizer = RssFeedNormalizer(
            source_definition=source_definition,
            keyword_filter=KeywordFilter(IRAN_SIGNAL_KEYWORDS),
        )

        events = normalizer.normalize(PERSIAN_RSS_FIXTURE)

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.source_id, "tasnim")
        self.assertEqual(event.source_tier, SourceTier.TRIGGER)
        self.assertEqual(event.source_category, SourceCategory.OFFICIAL_IRAN)
        self.assertEqual(event.language, "fa")
        self.assertTrue(event.translation_required)
        self.assertEqual(event.raw_event_ref, "tasnim-fa-hormuz-1")

    def test_tasnim_english_fixture_matches_iran_keywords(self):
        source_definition = DEFAULT_SOURCE_REGISTRY.require("tasnim")
        normalizer = RssFeedNormalizer(
            source_definition=source_definition,
            keyword_filter=KeywordFilter(IRAN_SIGNAL_KEYWORDS),
        )

        events = normalizer.normalize(ENGLISH_RSS_FIXTURE)

        self.assertEqual(len(events), 1)
        self.assertIn("Hormuz", events[0].title)

    def test_tasnim_adapter_fetches_verified_official_rss_url(self):
        client = FakeTextFetchClient(PERSIAN_RSS_FIXTURE)
        adapter = build_tasnim_rss_adapter(fetch_client=client)

        async def collect():
            await adapter.start()
            events = [event async for event in adapter.events()]
            await adapter.stop()
            return events

        events = asyncio.run(collect())

        self.assertEqual(len(events), 1)
        self.assertEqual(client.urls, ["https://www.tasnimnews.ir/fa/rss"])

    def test_official_iran_builder_only_enables_verified_rss_sources(self):
        client = FakeTextFetchClient(PERSIAN_RSS_FIXTURE)
        adapters = build_official_iran_rss_adapters(fetch_client=client)

        self.assertEqual(tuple(adapter.source_definition.source_id for adapter in adapters), (
            "tasnim",
        ))

    def test_idempotency_key_is_stable_for_same_persian_guid_and_timestamp(self):
        source_definition = DEFAULT_SOURCE_REGISTRY.require("tasnim")
        normalizer = RssFeedNormalizer(
            source_definition=source_definition,
            keyword_filter=KeywordFilter(IRAN_SIGNAL_KEYWORDS),
        )

        first = normalizer.normalize(PERSIAN_RSS_FIXTURE)[0]
        second = normalizer.normalize(PERSIAN_RSS_FIXTURE)[0]

        self.assertEqual(build_idempotency_key(first), build_idempotency_key(second))

    def test_access_notes_document_sources_not_implemented_yet(self):
        notes = {note.source_id: note for note in iran_source_access_notes()}

        self.assertTrue(notes["tasnim"].implemented)
        self.assertFalse(notes["irna"].implemented)
        self.assertFalse(notes["iran_foreign_ministry"].implemented)
        self.assertFalse(notes["mehr"].implemented)
        self.assertFalse(notes["fars"].implemented)
        self.assertFalse(notes["presstv"].implemented)


if __name__ == "__main__":
    unittest.main()
