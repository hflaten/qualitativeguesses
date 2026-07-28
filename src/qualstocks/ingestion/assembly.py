from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator

from qualstocks.domain import SourceClass, SourceEvent
from qualstocks.ingestion.runtime import IngestionRuntime
from qualstocks.ingestion.service import (
    AnalysisQueue,
    IngestionService,
    InMemoryAnalysisQueue,
    InMemoryEventRepository,
    SourceEventRepository,
)
from qualstocks.ingestion.postgres import (
    DatabaseClient,
    PostgresAnalysisQueue,
    PostgresSourceEventRepository,
    PsycopgDatabaseClient,
)
from qualstocks.settings import Settings
from qualstocks.sources import (
    DEFAULT_SOURCE_REGISTRY,
    SourceAdapter,
    TextFetchClient,
    WebhookAdapter,
    build_norwegian_confirmation_rss_adapters,
    build_official_iran_rss_adapters,
    build_official_us_rss_adapters,
)


@dataclass(frozen=True)
class RuntimeAssembly:
    runtime: IngestionRuntime
    repository: SourceEventRepository
    analysis_queue: AnalysisQueue
    adapter_source_ids: tuple[str, ...]
    persistence_backend: str


def build_source_adapters(
    settings: Settings,
    *,
    fetch_client: TextFetchClient | None = None,
) -> tuple[SourceAdapter, ...]:
    adapters: list[SourceAdapter] = []
    if settings.source_fixture_mode_enabled:
        adapters.append(FixtureSourceAdapter())
    if settings.source_official_us_rss_enabled:
        adapters.extend(build_official_us_rss_adapters(fetch_client=fetch_client))
    if settings.source_official_iran_rss_enabled:
        adapters.extend(build_official_iran_rss_adapters(fetch_client=fetch_client))
    if settings.source_norwegian_confirmation_rss_enabled:
        adapters.extend(
            build_norwegian_confirmation_rss_adapters(fetch_client=fetch_client)
        )
    return tuple(adapters)


def build_runtime_assembly(
    settings: Settings,
    *,
    fetch_client: TextFetchClient | None = None,
    database_client: DatabaseClient | None = None,
) -> RuntimeAssembly:
    repository, analysis_queue = build_persistence_components(
        settings,
        database_client=database_client,
    )
    service = IngestionService(repository=repository, analysis_queue=analysis_queue)
    adapters = build_source_adapters(settings, fetch_client=fetch_client)
    return RuntimeAssembly(
        runtime=IngestionRuntime(service=service, adapters=adapters),
        repository=repository,
        analysis_queue=analysis_queue,
        adapter_source_ids=_adapter_source_ids(adapters),
        persistence_backend=settings.source_persistence_backend,
    )


def build_persistence_components(
    settings: Settings,
    *,
    database_client: DatabaseClient | None = None,
) -> tuple[SourceEventRepository, AnalysisQueue]:
    if settings.source_persistence_backend == "postgres":
        if database_client is None and not settings.supabase_db_url:
            raise ValueError("SUPABASE_DB_URL is required for postgres source persistence")
        client = database_client or PsycopgDatabaseClient(settings.supabase_db_url)
        return PostgresSourceEventRepository(client), PostgresAnalysisQueue(client)
    if settings.source_persistence_backend != "memory":
        raise ValueError(
            f"unknown source persistence backend: {settings.source_persistence_backend}"
        )
    return InMemoryEventRepository(), InMemoryAnalysisQueue()


class FixtureSourceAdapter(WebhookAdapter):
    def __init__(self) -> None:
        source_definition = DEFAULT_SOURCE_REGISTRY.require("centcom_rss")
        super().__init__(
            "Local fixture source",
            SourceClass.OFFICIAL_ACTOR,
            source_definition=source_definition,
        )

    async def events(self) -> AsyncIterator[SourceEvent]:
        yield self._record_event(
            title="Fixture: CENTCOM reports Strait of Hormuz maritime risk",
            url="https://example.invalid/fixture/hormuz",
            payload={
                "summary": "Fixture event for watcher runtime validation.",
                "raw_event_ref": "fixture-centcom-hormuz-1",
            },
        )


def _adapter_source_ids(adapters: tuple[SourceAdapter, ...]) -> tuple[str, ...]:
    source_ids: list[str] = []
    for adapter in adapters:
        health = adapter.health()
        if health.source_id is not None:
            source_ids.append(health.source_id)
    return tuple(source_ids)
