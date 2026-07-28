from __future__ import annotations

import unittest

from qualstocks.domain import SourceCategory, SourceTier
from qualstocks.sources import (
    DEFAULT_SOURCE_REGISTRY,
    AdapterKind,
    ApMediaEventNormalizer,
    ApMediaLicensedFeedAdapter,
    LsegReutersEventNormalizer,
    LsegReutersLicensedFeedAdapter,
)


class LicensedFeedAdapterTest(unittest.TestCase):
    def test_lseg_reuters_payload_normalizes_to_raw_adapter_event(self):
        event = LsegReutersEventNormalizer().normalize(
            {
                "storyId": "urn:newsml:reuters.com:20260728:nL1N2ABCD",
                "headline": "Oil jumps as Hormuz risk rises",
                "body": "Shipping risk around the Strait of Hormuz increased.",
                "versionCreated": "2026-07-28T10:00:03Z",
                "uri": "reuters://news/20260728/nL1N2ABCD",
                "topics": ["OIL", "MIDEAST"],
                "instruments": ["EQNR.OL", "LCOc1"],
                "urgency": "1",
            }
        )

        self.assertEqual(event.source_id, "reuters_lseg_news")
        self.assertEqual(event.source_tier, SourceTier.TRIGGER)
        self.assertEqual(event.source_category, SourceCategory.WIRE_OR_NEWSPAPER)
        self.assertEqual(event.instrument, "EQNR.OL")
        self.assertEqual(event.payload["headline"], "Oil jumps as Hormuz risk rises")
        self.assertEqual(event.payload["topics"], ("OIL", "MIDEAST"))
        self.assertEqual(event.provenance["provider"], "lseg_reuters")
        self.assertEqual(
            event.provenance["raw_event_ref"],
            "urn:newsml:reuters.com:20260728:nL1N2ABCD",
        )
        self.assertEqual(
            event.idempotency_key,
            "lseg-reuters:urn:newsml:reuters.com:20260728:nL1N2ABCD",
        )
        self.assertEqual(event.source_timestamp.isoformat(), "2026-07-28T10:00:03+00:00")

    def test_ap_media_payload_normalizes_to_raw_adapter_event(self):
        event = ApMediaEventNormalizer().normalize(
            {
                "item": {
                    "id": "ap-20260728-1",
                    "headline": "AP reports tanker disruption near Hormuz",
                    "body_text": "A tanker disruption near Hormuz lifted oil futures.",
                    "firstcreated": "2026-07-28T10:01:00Z",
                    "url": "https://apnews.com/article/ap-20260728-1",
                    "subjects": ["Iran", "Oil"],
                    "instruments": ["EQNR:NO"],
                }
            }
        )

        self.assertEqual(event.source_id, "ap_media_api")
        self.assertEqual(event.source_tier, SourceTier.TRIGGER)
        self.assertEqual(event.instrument, "EQNR.OL")
        self.assertEqual(
            event.payload["headline"],
            "AP reports tanker disruption near Hormuz",
        )
        self.assertEqual(event.payload["topics"], ("Iran", "Oil"))
        self.assertEqual(event.provenance["provider"], "ap_media_api")
        self.assertEqual(event.provenance["raw_event_ref"], "ap-20260728-1")
        self.assertEqual(event.idempotency_key, "ap-media-api:ap-20260728-1")
        self.assertEqual(event.source_timestamp.isoformat(), "2026-07-28T10:01:00+00:00")

    def test_licensed_feed_adapters_expose_registry_health_and_normalizers(self):
        reuters = LsegReutersLicensedFeedAdapter(
            DEFAULT_SOURCE_REGISTRY.require("reuters_lseg_news")
        )
        ap = ApMediaLicensedFeedAdapter(DEFAULT_SOURCE_REGISTRY.require("ap_media_api"))

        self.assertEqual(reuters.health().source_id, "reuters_lseg_news")
        self.assertEqual(reuters.health().kind, AdapterKind.STREAMING_API)
        self.assertEqual(ap.health().source_id, "ap_media_api")
        self.assertEqual(ap.health().kind, AdapterKind.FALLBACK_POLLING)
        self.assertEqual(
            reuters.normalize_payload({"headline": "Reuters alert"}).source_id,
            "reuters_lseg_news",
        )
        self.assertEqual(
            ap.normalize_payload({"item": {"headline": "AP alert"}}).source_id,
            "ap_media_api",
        )

    def test_registry_marks_lseg_and_ap_as_trigger_grade_paid_sources(self):
        self.assertTrue(DEFAULT_SOURCE_REGISTRY.require("reuters_lseg_news").is_trigger_grade)
        self.assertTrue(DEFAULT_SOURCE_REGISTRY.require("ap_media_api").is_trigger_grade)


if __name__ == "__main__":
    unittest.main()
