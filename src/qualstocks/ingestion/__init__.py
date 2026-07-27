"""Automatic ingestion runtime for normalized source events."""

from qualstocks.ingestion.assembly import (
    FixtureSourceAdapter,
    RuntimeAssembly,
    build_persistence_components,
    build_runtime_assembly,
    build_source_adapters,
)
from qualstocks.ingestion.postgres import (
    DatabaseClient,
    PostgresAnalysisQueue,
    PostgresSourceEventRepository,
    PsycopgDatabaseClient,
)
from qualstocks.ingestion.runtime import IngestionRuntime
from qualstocks.ingestion.service import (
    AnalysisJob,
    IngestedEvent,
    IngestionResult,
    IngestionService,
    InMemoryAnalysisQueue,
    InMemoryEventRepository,
    SourceEventRepository,
    SourceEventStatus,
)

__all__ = [
    "AnalysisJob",
    "DatabaseClient",
    "FixtureSourceAdapter",
    "IngestedEvent",
    "IngestionResult",
    "IngestionRuntime",
    "IngestionService",
    "InMemoryAnalysisQueue",
    "InMemoryEventRepository",
    "RuntimeAssembly",
    "SourceEventRepository",
    "SourceEventStatus",
    "PostgresAnalysisQueue",
    "PostgresSourceEventRepository",
    "PsycopgDatabaseClient",
    "build_persistence_components",
    "build_runtime_assembly",
    "build_source_adapters",
]
