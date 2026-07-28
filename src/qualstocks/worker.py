from __future__ import annotations

import time

from qualstocks.analysis import (
    AnalysisJobStatus,
    DatabaseAnalysisQueueRepository,
    EventAnalysisWorker,
    OpenAIJsonClassificationClient,
)
from qualstocks.ingestion import PaperTradingRepository, PsycopgDatabaseClient
from qualstocks.settings import load_settings


def build_analysis_worker() -> EventAnalysisWorker:
    settings = load_settings()
    if settings.source_persistence_backend != "postgres":
        raise ValueError("analysis worker requires SOURCE_PERSISTENCE_BACKEND=postgres")
    if not settings.supabase_db_url:
        raise ValueError("SUPABASE_DB_URL is required for analysis worker")
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required for analysis worker")

    database_client = PsycopgDatabaseClient(settings.supabase_db_url)
    model_client = OpenAIJsonClassificationClient(settings.openai_api_key)
    return EventAnalysisWorker(
        queue=DatabaseAnalysisQueueRepository(database_client),
        classification_repository=PaperTradingRepository(database_client),
        filter_model_client=model_client,
        analysis_model_client=model_client,
        filter_model=settings.openai_filter_model,
        analysis_model=settings.openai_analysis_model,
    )


def main() -> None:
    settings = load_settings()
    print(
        "worker-service starting",
        {
            "app_env": settings.app_env,
            "runtime_secrets_present": settings.has_required_runtime_secrets,
        },
        flush=True,
    )
    try:
        worker = build_analysis_worker()
    except ValueError as exc:
        print(f"worker-service not configured: {exc}", flush=True)
        return

    print("worker-service polling analysis queue", flush=True)
    while True:
        result = worker.run_once()
        if result.status != AnalysisJobStatus.NO_JOB:
            print(
                "worker-service analysis result",
                {"status": result.status.value, "error": result.error},
                flush=True,
            )
        if settings.watcher_run_once:
            return
        time.sleep(30)


if __name__ == "__main__":
    main()
