import asyncio
import unittest
from datetime import timedelta

from qualstocks.domain import SourceClass
from qualstocks.ingestion import (
    InMemoryAnalysisQueue,
    InMemoryEventRepository,
    IngestionRuntime,
    IngestionService,
    SourceEventStatus,
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


if __name__ == "__main__":
    unittest.main()
