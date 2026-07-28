from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

from qualstocks.domain import SourceClass, SourceEvent
from qualstocks.ingestion.runtime import AdapterBackoffPolicy, IngestionRuntime
from qualstocks.ingestion.service import (
    IngestionService,
    InMemoryAnalysisQueue,
    InMemoryEventRepository,
)
from qualstocks.sources import FallbackPollingAdapter


class SequencePollingAdapter(FallbackPollingAdapter):
    def __init__(self, source: str, outcomes: list[SourceEvent | Exception]) -> None:
        super().__init__(source, SourceClass.OFFICIAL_ACTOR)
        self.outcomes = outcomes

    async def events(self) -> AsyncIterator[SourceEvent]:
        if not self.outcomes:
            return
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        yield outcome

    def event(self, title: str, raw_event_ref: str) -> SourceEvent:
        return self._record_event(
            title=title,
            url=f"https://example.invalid/{raw_event_ref}",
            payload={"raw_event_ref": raw_event_ref},
        )


class StartFailingPollingAdapter(SequencePollingAdapter):
    async def start(self) -> None:
        raise RuntimeError("connection refused")


class WatcherResilienceTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 28, 13, 30, tzinfo=timezone.utc)
        self.repository = InMemoryEventRepository()
        self.queue = InMemoryAnalysisQueue()
        self.service = IngestionService(
            repository=self.repository,
            analysis_queue=self.queue,
        )

    def test_one_failing_adapter_does_not_stop_healthy_adapter(self):
        failing = SequencePollingAdapter("Failing RSS", [RuntimeError("source timeout")])
        healthy = SequencePollingAdapter("Healthy RSS", [])
        healthy.outcomes.append(healthy.event("Healthy Hormuz update", "healthy-1"))
        runtime = IngestionRuntime(
            service=self.service,
            adapters=(failing, healthy),
            backoff_policy=AdapterBackoffPolicy(initial_seconds=10),
        )

        results = asyncio.run(runtime.run_once(now=self.now))

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].created)
        self.assertEqual(len(self.queue.jobs), 1)
        self.assertEqual(self.repository.source_health["Failing RSS"]["status"], "degraded")
        self.assertEqual(
            self.repository.source_health["Failing RSS"]["last_error"],
            "source timeout",
        )
        self.assertEqual(self.repository.source_health["Healthy RSS"]["status"], "online")

    def test_start_failure_records_offline_and_continues(self):
        failing = StartFailingPollingAdapter("Dead RSS", [])
        healthy = SequencePollingAdapter("Healthy RSS", [])
        healthy.outcomes.append(healthy.event("Healthy Hormuz update", "healthy-2"))
        runtime = IngestionRuntime(service=self.service, adapters=(failing, healthy))

        results = asyncio.run(runtime.run_once(now=self.now))

        self.assertEqual(len(results), 1)
        self.assertEqual(self.repository.source_health["Dead RSS"]["status"], "offline")
        self.assertEqual(
            self.repository.source_health["Dead RSS"]["last_error"],
            "connection refused",
        )
        self.assertEqual(self.repository.source_health["Healthy RSS"]["status"], "online")

    def test_polling_adapter_uses_backoff_then_recovers_after_success(self):
        adapter = SequencePollingAdapter("Recovering RSS", [RuntimeError("rate limited")])
        runtime = IngestionRuntime(
            service=self.service,
            adapters=(adapter,),
            backoff_policy=AdapterBackoffPolicy(initial_seconds=10),
        )

        first = asyncio.run(runtime.run_once(now=self.now))
        adapter.outcomes.append(adapter.event("Recovered Hormuz update", "recover-1"))
        skipped = asyncio.run(runtime.run_once(now=self.now + timedelta(seconds=5)))
        recovered = asyncio.run(runtime.run_once(now=self.now + timedelta(seconds=11)))

        self.assertEqual(first, [])
        self.assertEqual(skipped, [])
        self.assertEqual(len(recovered), 1)
        self.assertTrue(recovered[0].created)
        self.assertEqual(self.repository.source_health["Recovering RSS"]["status"], "online")
        self.assertIsNone(self.repository.source_health["Recovering RSS"]["last_error"])


if __name__ == "__main__":
    unittest.main()
