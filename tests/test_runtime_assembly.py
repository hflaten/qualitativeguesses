from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import patch

from qualstocks.ingestion import build_runtime_assembly, build_source_adapters
from qualstocks.settings import load_settings
from qualstocks.watcher import run_watcher


RSS_FIXTURE = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>Runtime Feed</title>
    <item>
      <title>Statement on Strait of Hormuz tanker incident</title>
      <link>https://example.invalid/runtime/hormuz</link>
      <guid>runtime-hormuz-1</guid>
      <pubDate>Mon, 27 Jul 2026 15:30:00 GMT</pubDate>
      <description>Iran, US, and tanker risk near Hormuz.</description>
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


def settings_from_env(env: dict[str, str]):
    with patch.dict(os.environ, env, clear=True):
        return load_settings()


class RuntimeAssemblyTest(unittest.TestCase):
    def test_disabled_sources_create_no_adapters(self):
        settings = settings_from_env({})

        adapters = build_source_adapters(settings)

        self.assertEqual(adapters, ())

    def test_fixture_mode_adds_local_fixture_adapter(self):
        settings = settings_from_env({"SOURCE_FIXTURE_MODE_ENABLED": "true"})

        assembly = build_runtime_assembly(settings)

        self.assertEqual(assembly.adapter_source_ids, ("centcom_rss",))

    def test_official_source_flags_select_rss_adapters(self):
        settings = settings_from_env(
            {
                "SOURCE_OFFICIAL_US_RSS_ENABLED": "true",
                "SOURCE_OFFICIAL_IRAN_RSS_ENABLED": "true",
            }
        )

        assembly = build_runtime_assembly(settings, fetch_client=FakeTextFetchClient(RSS_FIXTURE))

        self.assertEqual(assembly.adapter_source_ids, ("dod_rss", "centcom_rss", "tasnim"))

    def test_runtime_run_once_ingests_fixture_event(self):
        settings = settings_from_env({"SOURCE_FIXTURE_MODE_ENABLED": "true"})
        assembly = build_runtime_assembly(settings)

        results = asyncio.run(assembly.runtime.run_once())

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].created)
        self.assertEqual(len(assembly.repository.events_by_key), 1)
        self.assertEqual(len(assembly.analysis_queue.jobs), 1)

    def test_run_watcher_drains_enabled_adapters_once(self):
        settings = settings_from_env(
            {
                "SOURCE_FIXTURE_MODE_ENABLED": "true",
                "SOURCE_OFFICIAL_US_RSS_ENABLED": "true",
            }
        )
        fetch_client = FakeTextFetchClient(RSS_FIXTURE)
        assembly = build_runtime_assembly(settings, fetch_client=fetch_client)

        asyncio.run(run_watcher(assembly))

        self.assertEqual(len(assembly.repository.events_by_key), 3)
        self.assertEqual(len(assembly.analysis_queue.jobs), 3)
        self.assertEqual(fetch_client.urls, [
            "https://www.defense.gov/news/rss",
            "https://www.centcom.mil/rss/",
        ])

    def test_run_watcher_with_no_adapters_returns_without_ingestion(self):
        settings = settings_from_env({})
        assembly = build_runtime_assembly(settings)

        asyncio.run(run_watcher(assembly))

        self.assertEqual(len(assembly.repository.events_by_key), 0)
        self.assertEqual(len(assembly.analysis_queue.jobs), 0)


if __name__ == "__main__":
    unittest.main()
