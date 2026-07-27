from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator

from qualstocks.domain import SourceClass, SourceEvent
from qualstocks.ingestion.runtime import IngestionRuntime
from qualstocks.ingestion.service import (
    IngestionService,
    InMemoryAnalysisQueue,
    InMemoryEventRepository,
)
from qualstocks.settings import Settings
from qualstocks.sources import (
    DEFAULT_SOURCE_REGISTRY,
    SourceAdapter,
    TextFetchClient,
    WebhookAdapter,
    build_official_iran_rss_adapters,
    build_official_us_rss_adapters,
)


@dataclass(frozen=True)
class RuntimeAssembly:
    runtime: IngestionRuntime
    repository: InMemoryEventRepository
    analysis_queue: InMemoryAnalysisQueue
    adapter_source_ids: tuple[str, ...]


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
    return tuple(adapters)


def build_runtime_assembly(
    settings: Settings,
    *,
    fetch_client: TextFetchClient | None = None,
) -> RuntimeAssembly:
    repository = InMemoryEventRepository()
    analysis_queue = InMemoryAnalysisQueue()
    service = IngestionService(repository=repository, analysis_queue=analysis_queue)
    adapters = build_source_adapters(settings, fetch_client=fetch_client)
    return RuntimeAssembly(
        runtime=IngestionRuntime(service=service, adapters=adapters),
        repository=repository,
        analysis_queue=analysis_queue,
        adapter_source_ids=_adapter_source_ids(adapters),
    )


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
