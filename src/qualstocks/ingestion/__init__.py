"""Automatic ingestion runtime for normalized source events."""

from qualstocks.ingestion.assembly import (
    FixtureSourceAdapter,
    RuntimeAssembly,
    build_runtime_assembly,
    build_source_adapters,
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
    "build_runtime_assembly",
    "build_source_adapters",
]
