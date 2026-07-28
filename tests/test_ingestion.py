import asyncio
import unittest
from datetime import datetime, timedelta, timezone

from qualstocks.domain import SourceClass, SourceEvent
from qualstocks.ingestion import (
    AdapterEventErrorCode,
    InMemoryAnalysisQueue,
    InMemoryEventRepository,
    IngestionRuntime,
    IngestionService,
    IngestionValidationConfig,
    RawAdapterEvent,
    SourceEventStatus,
    normalize_raw_adapter_event,
    validate_raw_adapter_event,
)
from qualstocks.sources import DEFAULT_SOURCE_REGISTRY, WebhookAdapter


class SingleEventAdapter(WebhookAdapter):
    def __init__(self):
        super().__init__("CENTCOM", SourceClass.OFFICIAL_ACTOR)

    async def events(self):
        yield self._record_event(
            title="Statement on regional military activity",
            url="https://example.invalid/centcom",
            payload={"severity": "high"},
        )


class IngestionTest(unittest.TestCase):
    def test_new_event_is_persisted_and_enqueued_for_analysis(self):
        repository = InMemoryEventRepository()
        queue = InMemoryAnalysisQueue()
        service = IngestionService(repository=repository, analysis_queue=queue)
        adapter = SingleEventAdapter()
        runtime = IngestionRuntime(service=service, adapters=(adapter,))

        results = asyncio.run(runtime.run_once())

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, SourceEventStatus.CREATED)
        self.assertIsNotNone(results[0].analysis_job)
        self.assertEqual(len(repository.events_by_key), 1)
        self.assertEqual(len(queue.jobs), 1)
        self.assertIn("CENTCOM", repository.source_seen_at)

    def test_raw_adapter_event_normalizes_to_source_event_with_contract_fields(self):
        raw = RawAdapterEvent(
            source="CENTCOM",
            source_class=SourceClass.OFFICIAL_ACTOR,
            instrument="EQNR.OL",
            payload={"headline": "Statement on regional military activity"},
            provenance={
                "url": "https://example.invalid/centcom",
                "raw_event_ref": "centcom-1",
            },
            source_timestamp=datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc),
            first_seen_at=datetime(2026, 7, 27, 12, 0, 5, tzinfo=timezone.utc),
        )

        normalized = normalize_raw_adapter_event(raw)

        self.assertEqual(normalized.event.title, "Statement on regional military activity")
        self.assertEqual(normalized.event.instrument, "EQNR.OL")
        self.assertEqual(normalized.event.raw_event_ref, "centcom-1")
        self.assertTrue(normalized.idempotency_key.startswith("official_actor:centcom:"))

    def test_raw_adapter_event_is_ingested_and_enqueued_for_analysis(self):
        repository = InMemoryEventRepository()
        queue = InMemoryAnalysisQueue()
        service = IngestionService(repository=repository, analysis_queue=queue)
        raw = RawAdapterEvent(
            source="CENTCOM",
            source_class=SourceClass.OFFICIAL_ACTOR,
            instrument="EQNR.OL",
            payload={"headline": "Statement on regional military activity"},
            provenance={
                "url": "https://example.invalid/centcom",
                "raw_event_ref": "centcom-1",
            },
            source_timestamp=datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc),
            first_seen_at=datetime(2026, 7, 27, 12, 0, 5, tzinfo=timezone.utc),
        )

        result = asyncio.run(service.ingest_raw(raw))

        self.assertEqual(result.status, SourceEventStatus.CREATED)
        self.assertIsNotNone(result.ingested_event)
        self.assertIsNotNone(result.analysis_job)
        self.assertEqual(result.ingested_event.event.instrument, "EQNR.OL")
        self.assertEqual(result.ingested_event.event.raw_event_ref, "centcom-1")
        self.assertEqual(len(repository.events_by_key), 1)
        self.assertEqual(len(queue.jobs), 1)

    def test_raw_adapter_event_preserves_provided_idempotency_key_for_duplicates(self):
        repository = InMemoryEventRepository()
        queue = InMemoryAnalysisQueue()
        service = IngestionService(repository=repository, analysis_queue=queue)
        raw = RawAdapterEvent(
            source="CENTCOM",
            source_class=SourceClass.OFFICIAL_ACTOR,
            instrument="EQNR.OL",
            payload={"headline": "Statement on regional military activity"},
            provenance={"url": "https://example.invalid/centcom"},
            idempotency_key="provider-event:centcom:123",
        )

        first = asyncio.run(service.ingest_raw(raw))
        second = asyncio.run(service.ingest_raw(raw))

        self.assertEqual(first.status, SourceEventStatus.CREATED)
        self.assertEqual(second.status, SourceEventStatus.DUPLICATE)
        self.assertEqual(first.ingested_event.idempotency_key, "provider-event:centcom:123")
        self.assertEqual(second.ingested_event.idempotency_key, "provider-event:centcom:123")
        self.assertEqual(len(repository.events_by_key), 1)
        self.assertEqual(len(queue.jobs), 1)

    def test_duplicate_event_is_not_enqueued_twice(self):
        repository = InMemoryEventRepository()
        queue = InMemoryAnalysisQueue()
        service = IngestionService(repository=repository, analysis_queue=queue)
        adapter = SingleEventAdapter()
        runtime = IngestionRuntime(service=service, adapters=(adapter,))

        first = asyncio.run(runtime.run_once())
        second = asyncio.run(runtime.run_once())

        self.assertEqual(first[0].status, SourceEventStatus.CREATED)
        self.assertEqual(second[0].status, SourceEventStatus.DUPLICATE)
        self.assertEqual(len(repository.events_by_key), 1)
        self.assertEqual(len(queue.jobs), 1)

    def test_source_latency_is_recorded_when_source_timestamp_exists(self):
        repository = InMemoryEventRepository()
        queue = InMemoryAnalysisQueue()
        service = IngestionService(repository=repository, analysis_queue=queue)
        adapter = WebhookAdapter("CENTCOM", SourceClass.OFFICIAL_ACTOR)
        event = adapter._record_event(
            title="Statement on regional military activity",
            url="https://example.invalid/centcom",
            payload={"severity": "high"},
            source_timestamp=adapter.health().last_checked_at - timedelta(seconds=5),
        )

        result = asyncio.run(service.ingest(event))

        self.assertIsNotNone(result.ingested_event.source_latency_seconds)
        self.assertGreaterEqual(result.ingested_event.source_latency_seconds, 0)

    def test_analysis_job_preserves_source_id(self):
        source_definition = DEFAULT_SOURCE_REGISTRY.require("ukmto")
        repository = InMemoryEventRepository()
        queue = InMemoryAnalysisQueue()
        service = IngestionService(repository=repository, analysis_queue=queue)
        adapter = WebhookAdapter(
            source_definition.name,
            source_definition.source_class,
            source_definition=source_definition,
        )
        event = adapter._record_event(
            title="UKMTO warning near Strait of Hormuz",
            url="https://example.invalid/ukmto",
            payload={"severity": "high"},
        )

        result = asyncio.run(service.ingest(event))

        self.assertIsNotNone(result.analysis_job)
        self.assertEqual(result.analysis_job.source_id, "ukmto")

    def test_malformed_event_is_rejected_before_persistence(self):
        repository = InMemoryEventRepository()
        queue = InMemoryAnalysisQueue()
        service = IngestionService(repository=repository, analysis_queue=queue)

        result = asyncio.run(
            service.ingest(
                SourceEvent(
                    source="CENTCOM",
                    source_class=SourceClass.OFFICIAL_ACTOR,
                    title="",
                    url="https://example.invalid/centcom",
                    payload={"severity": "high"},
                    instrument="EQNR.OL",
                )
            )
        )

        self.assertTrue(result.rejected)
        self.assertEqual(result.status, SourceEventStatus.MALFORMED)
        self.assertEqual(result.rejection_reason, "title is required")
        self.assertEqual(len(repository.events_by_key), 0)
        self.assertEqual(len(queue.jobs), 0)

    def test_unsupported_instrument_is_rejected_before_persistence(self):
        repository = InMemoryEventRepository()
        queue = InMemoryAnalysisQueue()
        service = IngestionService(repository=repository, analysis_queue=queue)
        adapter = WebhookAdapter("CENTCOM", SourceClass.OFFICIAL_ACTOR)
        event = adapter._record_event(
            title="Statement on another issuer",
            url="https://example.invalid/centcom",
            payload={"severity": "high"},
            instrument="AKRBP.OL",
        )

        result = asyncio.run(service.ingest(event))

        self.assertEqual(result.status, SourceEventStatus.UNSUPPORTED)
        self.assertEqual(result.rejection_reason, "instrument is not supported")
        self.assertEqual(len(repository.events_by_key), 0)

    def test_late_event_is_rejected_before_persistence(self):
        repository = InMemoryEventRepository()
        queue = InMemoryAnalysisQueue()
        service = IngestionService(
            repository=repository,
            analysis_queue=queue,
            validation_config=IngestionValidationConfig(max_source_event_age=timedelta(minutes=5)),
        )
        adapter = WebhookAdapter("CENTCOM", SourceClass.OFFICIAL_ACTOR)
        event = adapter._record_event(
            title="Old statement",
            url="https://example.invalid/centcom",
            payload={"severity": "high"},
            instrument="EQNR.OL",
            source_timestamp=datetime.now(timezone.utc) - timedelta(minutes=10),
        )

        result = asyncio.run(service.ingest(event))

        self.assertEqual(result.status, SourceEventStatus.LATE)
        self.assertEqual(result.rejection_reason, "source event is too old")
        self.assertEqual(len(queue.jobs), 0)

    def test_raw_adapter_validation_reports_unsupported_and_late_events(self):
        raw = RawAdapterEvent(
            source="CENTCOM",
            source_class=SourceClass.OFFICIAL_ACTOR,
            instrument="AKRBP.OL",
            payload={"headline": "Old event"},
            provenance={"url": "https://example.invalid/centcom"},
            source_timestamp=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
            first_seen_at=datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc),
        )

        validation = validate_raw_adapter_event(raw)

        self.assertFalse(validation.valid)
        self.assertEqual(
            {error.code for error in validation.errors},
            {AdapterEventErrorCode.UNSUPPORTED, AdapterEventErrorCode.LATE},
        )

    def test_malformed_raw_adapter_event_is_rejected_before_persistence(self):
        repository = InMemoryEventRepository()
        queue = InMemoryAnalysisQueue()
        service = IngestionService(repository=repository, analysis_queue=queue)
        raw = RawAdapterEvent(
            source="CENTCOM",
            source_class=SourceClass.OFFICIAL_ACTOR,
            instrument="EQNR.OL",
            payload={"severity": "high"},
            provenance={"url": "https://example.invalid/centcom"},
        )

        result = asyncio.run(service.ingest_raw(raw))

        self.assertEqual(result.status, SourceEventStatus.MALFORMED)
        self.assertEqual(result.rejection_reason, "title is required")
        self.assertEqual(len(repository.events_by_key), 0)
        self.assertEqual(len(queue.jobs), 0)

    def test_late_raw_adapter_event_is_rejected_before_persistence(self):
        repository = InMemoryEventRepository()
        queue = InMemoryAnalysisQueue()
        service = IngestionService(
            repository=repository,
            analysis_queue=queue,
            validation_config=IngestionValidationConfig(max_source_event_age=timedelta(minutes=5)),
        )
        raw = RawAdapterEvent(
            source="CENTCOM",
            source_class=SourceClass.OFFICIAL_ACTOR,
            instrument="EQNR.OL",
            payload={"headline": "Old statement"},
            provenance={"url": "https://example.invalid/centcom"},
            source_timestamp=datetime.now(timezone.utc) - timedelta(minutes=10),
        )

        result = asyncio.run(service.ingest_raw(raw))

        self.assertEqual(result.status, SourceEventStatus.LATE)
        self.assertEqual(result.rejection_reason, "source event is too old")
        self.assertEqual(len(repository.events_by_key), 0)

    def test_unsupported_raw_adapter_event_is_rejected_before_persistence(self):
        repository = InMemoryEventRepository()
        queue = InMemoryAnalysisQueue()
        service = IngestionService(repository=repository, analysis_queue=queue)
        raw = RawAdapterEvent(
            source="CENTCOM",
            source_class=SourceClass.OFFICIAL_ACTOR,
            instrument="AKRBP.OL",
            payload={"headline": "Statement on another issuer"},
            provenance={"url": "https://example.invalid/centcom"},
        )

        result = asyncio.run(service.ingest_raw(raw))

        self.assertEqual(result.status, SourceEventStatus.UNSUPPORTED)
        self.assertEqual(result.rejection_reason, "instrument is not supported")
        self.assertEqual(len(repository.events_by_key), 0)


if __name__ == "__main__":
    unittest.main()
