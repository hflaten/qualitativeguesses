from __future__ import annotations

import unittest
from datetime import datetime, timezone

from qualstocks.analysis import (
    AnalysisJobClaim,
    AnalysisJobStatus,
    EventAnalysisWorker,
    MalformedModelOutput,
    classify_from_payload,
)
from qualstocks.domain import Direction, SourceClass, SourceEvent, SourceTier
from qualstocks.ingestion import PaperTradingRepository
from qualstocks.ingestion.trading_persistence import PersistenceStatus


class FakeModelClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def classify(self, prompt, *, model):
        self.calls.append({"prompt": prompt, "model": model})
        if not self.responses:
            raise AssertionError("unexpected model call")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeQueue:
    def __init__(self, event=None, job=None):
        self.event = event
        self.job = job
        self.completed = []
        self.failed = []

    def claim_queued_analysis_job(self, *, now=None):
        job = self.job
        self.job = None
        return job

    def fetch_source_event(self, event_id):
        if self.event is None or self.event.id != event_id:
            raise KeyError(event_id)
        return self.event

    def mark_analysis_job_completed(self, job_id, *, classification, raw_response, now=None):
        self.completed.append(
            {
                "job_id": job_id,
                "classification": classification,
                "raw_response": raw_response,
                "now": now,
            }
        )

    def mark_analysis_job_failed(self, job_id, *, error, now=None):
        self.failed.append({"job_id": job_id, "error": error, "now": now})


class FakeTradingDatabaseClient:
    def __init__(self):
        self.classifications = {}

    def insert_event_classification(self, values):
        key = (values["event_id"], values["model"])
        if key in self.classifications:
            return None
        self.classifications[key] = {"id": "classification-1", **values}
        return self.classifications[key]

    def fetch_event_classification(self, event_id, model):
        return self.classifications.get((event_id, model))


class AnalysisWorkerTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc)
        self.event = SourceEvent(
            source="CENTCOM",
            source_class=SourceClass.OFFICIAL_ACTOR,
            title="CENTCOM reports tanker incident near Hormuz",
            url="https://example.invalid/centcom",
            payload={"summary": "Hormuz tanker disruption and oil risk."},
            source_id="centcom_rss",
            source_tier=SourceTier.TRIGGER,
            id="event-1",
        )
        self.job = AnalysisJobClaim(
            id="job-1",
            event_id="event-1",
            idempotency_key="event-key",
            source="CENTCOM",
            source_class="official_actor",
            source_id="centcom_rss",
            payload={"source_tier": "trigger"},
        )

    def test_classify_from_payload_parses_trade_relevant_output(self):
        classification = classify_from_payload(
            "event-1",
            {
                "relevant_to_equinor": True,
                "direction": "bullish_equinor",
                "confidence": 0.87,
                "event_type": "hormuz_disruption",
                "reasoning_summary": "Hormuz disruption can lift oil prices.",
                "is_reinforcement": True,
                "is_contradiction": False,
            },
        )

        self.assertTrue(classification.relevant_to_equinor)
        self.assertEqual(classification.direction, Direction.BULLISH_EQUINOR)
        self.assertEqual(classification.confidence, 0.87)
        self.assertTrue(classification.is_reinforcement)

    def test_worker_uses_filter_and_analysis_models_for_relevant_event(self):
        queue = FakeQueue(event=self.event, job=self.job)
        db_client = FakeTradingDatabaseClient()
        worker = EventAnalysisWorker(
            queue=queue,
            classification_repository=PaperTradingRepository(db_client),
            filter_model_client=FakeModelClient(
                {
                    "relevant_to_equinor": True,
                    "confidence": 0.9,
                    "event_type": "hormuz_disruption",
                    "reasoning_summary": "Relevant oil-risk signal.",
                }
            ),
            analysis_model_client=FakeModelClient(
                {
                    "relevant_to_equinor": True,
                    "direction": "bullish_equinor",
                    "confidence": 0.86,
                    "event_type": "hormuz_disruption",
                    "reasoning_summary": "Hormuz disruption can lift oil prices.",
                    "is_reinforcement": False,
                    "is_contradiction": False,
                }
            ),
        )

        result = worker.run_once(now=self.now)

        self.assertEqual(result.status, AnalysisJobStatus.COMPLETED)
        self.assertEqual(result.classification.direction, Direction.BULLISH_EQUINOR)
        self.assertEqual(result.persistence_result.status, PersistenceStatus.CREATED)
        self.assertEqual(len(queue.completed), 1)
        self.assertEqual(len(queue.failed), 0)
        self.assertIn(("event-1", "gpt-5-mini"), db_client.classifications)

    def test_no_trade_filter_output_completes_without_analysis_model_call(self):
        queue = FakeQueue(event=self.event, job=self.job)
        analysis_model = FakeModelClient()
        worker = EventAnalysisWorker(
            queue=queue,
            classification_repository=PaperTradingRepository(FakeTradingDatabaseClient()),
            filter_model_client=FakeModelClient(
                {
                    "relevant_to_equinor": False,
                    "confidence": 0.2,
                    "event_type": "not_relevant",
                    "reasoning_summary": "No Equinor or oil-risk relevance.",
                }
            ),
            analysis_model_client=analysis_model,
        )

        result = worker.run_once(now=self.now)

        self.assertEqual(result.status, AnalysisJobStatus.COMPLETED)
        self.assertFalse(result.classification.relevant_to_equinor)
        self.assertEqual(result.classification.direction, Direction.UNCLEAR)
        self.assertEqual(len(analysis_model.calls), 0)

    def test_malformed_model_output_marks_job_failed(self):
        queue = FakeQueue(event=self.event, job=self.job)
        worker = EventAnalysisWorker(
            queue=queue,
            classification_repository=PaperTradingRepository(FakeTradingDatabaseClient()),
            filter_model_client=FakeModelClient({"relevant_to_equinor": True}),
            analysis_model_client=FakeModelClient(
                {
                    "relevant_to_equinor": True,
                    "direction": "sideways",
                    "confidence": 0.8,
                    "event_type": "bad",
                    "reasoning_summary": "Bad output.",
                }
            ),
        )

        result = worker.run_once(now=self.now)

        self.assertEqual(result.status, AnalysisJobStatus.FAILED)
        self.assertIn("unsupported direction", result.error)
        self.assertEqual(queue.failed[0]["job_id"], "job-1")

    def test_no_queued_job_returns_no_job_status(self):
        worker = EventAnalysisWorker(
            queue=FakeQueue(),
            classification_repository=PaperTradingRepository(FakeTradingDatabaseClient()),
            filter_model_client=FakeModelClient(),
            analysis_model_client=FakeModelClient(),
        )

        result = worker.run_once(now=self.now)

        self.assertEqual(result.status, AnalysisJobStatus.NO_JOB)

    def test_parser_rejects_missing_reasoning_summary(self):
        with self.assertRaises(MalformedModelOutput):
            classify_from_payload(
                "event-1",
                {
                    "relevant_to_equinor": True,
                    "direction": "bullish_equinor",
                    "confidence": 0.8,
                    "event_type": "hormuz_disruption",
                },
            )


if __name__ == "__main__":
    unittest.main()
