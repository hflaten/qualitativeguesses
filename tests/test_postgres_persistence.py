from __future__ import annotations

import asyncio
import json
import unittest

from qualstocks.ingestion import (
    IngestionService,
    PostgresAnalysisQueue,
    PostgresSourceEventRepository,
    SourceEventStatus,
)
from qualstocks.sources import DEFAULT_SOURCE_REGISTRY, WebhookAdapter


class FakeDatabaseClient:
    def __init__(self):
        self.events_by_key = {}
        self.source_health = {}
        self.analysis_jobs = []
        self.insert_source_event_calls = []

    def insert_source_event(self, values):
        self.insert_source_event_calls.append(values)
        key = values["idempotency_key"]
        if key in self.events_by_key:
            return None
        row = {"id": values["id"], "created_at": values["first_seen_at"]}
        self.events_by_key[key] = row
        return row

    def fetch_source_event_by_key(self, idempotency_key):
        return self.events_by_key.get(idempotency_key)

    def upsert_source_health(self, values):
        self.source_health[values["source"]] = values

    def insert_analysis_job(self, values):
        self.analysis_jobs.append(values)
        return {"id": f"job-{len(self.analysis_jobs)}", "queued_at": None}


def source_event():
    source_definition = DEFAULT_SOURCE_REGISTRY.require("centcom_rss")
    adapter = WebhookAdapter(
        source_definition.name,
        source_definition.source_class,
        source_definition=source_definition,
    )
    return adapter._record_event(
        title="CENTCOM statement on Strait of Hormuz tanker incident",
        url="https://example.invalid/centcom/hormuz",
        payload={
            "summary": "U.S. forces are monitoring a tanker incident near Hormuz.",
            "raw_event_ref": "centcom-hormuz-1",
        },
    )


class PostgresPersistenceTest(unittest.TestCase):
    def test_created_event_is_persisted_and_analysis_job_is_enqueued(self):
        client = FakeDatabaseClient()
        service = IngestionService(
            repository=PostgresSourceEventRepository(client),
            analysis_queue=PostgresAnalysisQueue(client),
        )

        result = asyncio.run(service.ingest(source_event()))

        self.assertEqual(result.status, SourceEventStatus.CREATED)
        self.assertIsNotNone(result.analysis_job)
        self.assertEqual(len(client.events_by_key), 1)
        self.assertEqual(len(client.analysis_jobs), 1)
        job_payload = json.loads(client.analysis_jobs[0]["payload"])
        self.assertEqual(job_payload["source_tier"], "trigger")
        self.assertEqual(client.analysis_jobs[0]["source_id"], "centcom_rss")

    def test_duplicate_event_is_not_enqueued_twice(self):
        client = FakeDatabaseClient()
        service = IngestionService(
            repository=PostgresSourceEventRepository(client),
            analysis_queue=PostgresAnalysisQueue(client),
        )
        event = source_event()

        first = asyncio.run(service.ingest(event))
        second = asyncio.run(service.ingest(event))

        self.assertEqual(first.status, SourceEventStatus.CREATED)
        self.assertEqual(second.status, SourceEventStatus.DUPLICATE)
        self.assertEqual(len(client.events_by_key), 1)
        self.assertEqual(len(client.analysis_jobs), 1)

    def test_source_event_values_include_metadata_and_json_payload(self):
        client = FakeDatabaseClient()
        service = IngestionService(
            repository=PostgresSourceEventRepository(client),
            analysis_queue=PostgresAnalysisQueue(client),
        )

        asyncio.run(service.ingest(source_event()))

        values = client.insert_source_event_calls[0]
        self.assertEqual(values["source_id"], "centcom_rss")
        self.assertEqual(values["source_tier"], "trigger")
        self.assertEqual(values["source_category"], "official_us")
        self.assertEqual(values["source_event_id"], "centcom-hormuz-1")
        self.assertEqual(json.loads(values["payload"])["raw_event_ref"], "centcom-hormuz-1")

    def test_source_health_is_upserted_after_ingest(self):
        client = FakeDatabaseClient()
        service = IngestionService(
            repository=PostgresSourceEventRepository(client),
            analysis_queue=PostgresAnalysisQueue(client),
        )

        asyncio.run(service.ingest(source_event()))

        health = client.source_health["CENTCOM RSS"]
        self.assertEqual(health["status"], "online")
        self.assertEqual(health["source_id"], "centcom_rss")
        self.assertEqual(health["source_class"], "official_actor")


if __name__ == "__main__":
    unittest.main()
