from __future__ import annotations

import asyncio
import unittest

from qualstocks.domain import SourceCategory, SourceTier
from qualstocks.ingestion.idempotency import build_idempotency_key
from qualstocks.sources import (
    DEFAULT_SOURCE_REGISTRY,
    NORWEGIAN_CONFIRMATION_KEYWORDS,
    KeywordFilter,
    RssFeedNormalizer,
    build_e24_rss_adapter,
    build_norwegian_confirmation_rss_adapters,
    norwegian_source_access_notes,
)


E24_RSS_FIXTURE = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>E24 Bors og finans</title>
    <item>
      <title>Equinor stiger etter ny oljepris uro i Hormuzstredet</title>
      <link>https://e24.no/boers-og-finans/i/equinor-hormuz</link>
      <guid>e24-equinor-hormuz-1</guid>
      <pubDate>Mon, 27 Jul 2026 15:40:00 GMT</pubDate>
      <description>Oljeprisen reagerer etter meldinger om Iran og tankere.</description>
    </item>
    <item>
      <title>Teknologiselskap legger frem kvartalstall</title>
      <link>https://e24.no/teknologi/i/tech-1</link>
      <guid>e24-tech-1</guid>
      <pubDate>Mon, 27 Jul 2026 15:41:00 GMT</pubDate>
      <description>En norsk apputvikler leverer resultat.</description>
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


class NorwegianSourceAdapterTest(unittest.TestCase):
    def test_e24_rss_preserves_norwegian_confirmation_metadata(self):
        source_definition = DEFAULT_SOURCE_REGISTRY.require("e24")
        normalizer = RssFeedNormalizer(
            source_definition=source_definition,
            keyword_filter=KeywordFilter(NORWEGIAN_CONFIRMATION_KEYWORDS),
        )

        events = normalizer.normalize(E24_RSS_FIXTURE)

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.source_id, "e24")
        self.assertEqual(event.source_tier, SourceTier.CONFIRMATION)
        self.assertEqual(event.source_category, SourceCategory.NORWEGIAN_PRESS)
        self.assertEqual(event.language, "no")
        self.assertTrue(event.translation_required)
        self.assertEqual(event.raw_event_ref, "e24-equinor-hormuz-1")
        self.assertIn("Oljeprisen", event.payload["summary"])

    def test_e24_adapter_fetches_verified_bors_og_finans_rss_url(self):
        client = FakeTextFetchClient(E24_RSS_FIXTURE)
        adapter = build_e24_rss_adapter(fetch_client=client)

        async def collect():
            await adapter.start()
            events = [event async for event in adapter.events()]
            await adapter.stop()
            return events

        events = asyncio.run(collect())

        self.assertEqual(len(events), 1)
        self.assertEqual(client.urls, ["http://e24.no/rss/?seksjon=boers-og-finans"])

    def test_norwegian_builder_only_enables_verified_rss_sources(self):
        adapters = build_norwegian_confirmation_rss_adapters(
            fetch_client=FakeTextFetchClient(E24_RSS_FIXTURE)
        )

        self.assertEqual(
            tuple(adapter.source_definition.source_id for adapter in adapters),
            ("e24",),
        )

    def test_idempotency_key_is_stable_for_same_norwegian_guid_and_timestamp(self):
        source_definition = DEFAULT_SOURCE_REGISTRY.require("e24")
        normalizer = RssFeedNormalizer(
            source_definition=source_definition,
            keyword_filter=KeywordFilter(NORWEGIAN_CONFIRMATION_KEYWORDS),
        )

        first = normalizer.normalize(E24_RSS_FIXTURE)[0]
        second = normalizer.normalize(E24_RSS_FIXTURE)[0]

        self.assertEqual(build_idempotency_key(first), build_idempotency_key(second))

    def test_access_notes_document_sources_not_implemented_yet(self):
        notes = {note.source_id: note for note in norwegian_source_access_notes()}

        self.assertTrue(notes["e24"].implemented)
        self.assertFalse(notes["dn"].implemented)
        self.assertFalse(notes["euronext_newsweb"].implemented)
        self.assertFalse(notes["equinor_ir"].implemented)


if __name__ == "__main__":
    unittest.main()
