import asyncio
import unittest

from qualstocks.domain import SourceClass
from qualstocks.sources import (
    AdapterHealthStatus,
    AdapterKind,
    FallbackPollingAdapter,
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


if __name__ == "__main__":
    unittest.main()

