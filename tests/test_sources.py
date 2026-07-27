import asyncio
import unittest

from qualstocks.domain import SourceClass
from qualstocks.sources import (
    AdapterHealthStatus,
    AdapterKind,
    DEFAULT_SOURCE_REGISTRY,
    FallbackPollingAdapter,
    SourceDefinition,
    SourceRegistry,
    StreamingApiAdapter,
    WebSocketAdapter,
    WebhookAdapter,
)


class SourceAdapterTest(unittest.TestCase):
    def test_websocket_adapter_health_lifecycle(self):
        adapter = WebSocketAdapter("Polymarket", SourceClass.PREDICTION_MARKET)

        self.assertEqual(adapter.health().status, AdapterHealthStatus.UNKNOWN)

        asyncio.run(adapter.start())

        health = adapter.health()
        self.assertEqual(health.kind, AdapterKind.WEBSOCKET)
        self.assertEqual(health.status, AdapterHealthStatus.HEALTHY)
        self.assertTrue(health.is_usable)

        asyncio.run(adapter.stop())

        self.assertEqual(adapter.health().status, AdapterHealthStatus.UNKNOWN)

    def test_adapter_records_normalized_source_event(self):
        adapter = WebhookAdapter("CENTCOM", SourceClass.OFFICIAL_ACTOR)

        event = adapter._record_event(
            title="Statement on regional military activity",
            url="https://example.invalid/centcom",
            payload={"severity": "high"},
        )

        self.assertEqual(event.source, "CENTCOM")
        self.assertEqual(event.source_class, SourceClass.OFFICIAL_ACTOR)
        self.assertEqual(event.title, "Statement on regional military activity")
        self.assertEqual(event.payload["severity"], "high")
        self.assertIsNotNone(adapter.health().last_event_at)

    def test_error_marks_started_adapter_degraded(self):
        adapter = StreamingApiAdapter("GDELT", SourceClass.OSINT)
        asyncio.run(adapter.start())

        adapter._record_error("rate limited")

        health = adapter.health()
        self.assertEqual(health.status, AdapterHealthStatus.DEGRADED)
        self.assertTrue(health.is_usable)
        self.assertEqual(health.last_error, "rate limited")

    def test_error_marks_stopped_adapter_down(self):
        adapter = FallbackPollingAdapter("E24", SourceClass.NORWEGIAN_CONFIRMATION)

        adapter._record_error("timeout")

        health = adapter.health()
        self.assertEqual(health.status, AdapterHealthStatus.DOWN)
        self.assertFalse(health.is_usable)

    def test_default_registry_classifies_v1_source_universe(self):
        polymarket = DEFAULT_SOURCE_REGISTRY.require("polymarket")
        euronext = DEFAULT_SOURCE_REGISTRY.require("euronext_newsweb")
        marinetraffic = DEFAULT_SOURCE_REGISTRY.require("marinetraffic")
        ukmto = DEFAULT_SOURCE_REGISTRY.require("ukmto")

        self.assertTrue(polymarket.is_trigger_grade)
        self.assertTrue(ukmto.is_trigger_grade)
        self.assertTrue(euronext.is_confirmation_source)
        self.assertTrue(marinetraffic.is_control_signal)
        self.assertEqual(polymarket.reliability_score, 0.82)

    def test_default_registry_contains_hormuz_closure_inputs(self):
        expected = {"ukmto", "marinetraffic", "vortexa", "brent_wti", "polymarket", "kalshi"}

        self.assertTrue(expected.issubset(set(DEFAULT_SOURCE_REGISTRY.ids())))

    def test_registry_rejects_duplicate_source_ids(self):
        source = DEFAULT_SOURCE_REGISTRY.require("polymarket")

        with self.assertRaises(ValueError):
            SourceRegistry((source, source))

    def test_adapter_applies_source_definition_to_event_and_health(self):
        source_definition = DEFAULT_SOURCE_REGISTRY.require("centcom_rss")
        adapter = WebhookAdapter(
            source_definition.name,
            source_definition.source_class,
            source_definition=source_definition,
        )

        event = adapter._record_event(
            title="Statement on regional military activity",
            url="https://example.invalid/centcom",
            payload={"severity": "high", "raw_event_ref": "rss-guid-1"},
        )
        health = adapter.health()

        self.assertEqual(health.source_id, "centcom_rss")
        self.assertEqual(event.source_id, "centcom_rss")
        self.assertEqual(event.source_tier, source_definition.tier)
        self.assertEqual(event.source_category, source_definition.category)
        self.assertEqual(event.reliability_score, source_definition.reliability_score)
        self.assertEqual(event.language, "en")
        self.assertFalse(event.translation_required)
        self.assertEqual(event.raw_event_ref, "rss-guid-1")

    def test_source_definition_validates_score_bounds(self):
        source = DEFAULT_SOURCE_REGISTRY.require("polymarket")

        with self.assertRaises(ValueError):
            SourceDefinition(
                source_id="bad_score",
                name="Bad Score",
                source_class=source.source_class,
                tier=source.tier,
                category=source.category,
                access_methods=source.access_methods,
                reliability_score=1.5,
                expected_latency_seconds=source.expected_latency_seconds,
                licensing_class=source.licensing_class,
                language=source.language,
            )


if __name__ == "__main__":
    unittest.main()
