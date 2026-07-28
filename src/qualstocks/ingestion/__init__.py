"""Automatic ingestion runtime for normalized source events."""

from qualstocks.ingestion.assembly import (
    FixtureSourceAdapter,
    RuntimeAssembly,
    build_persistence_components,
    build_runtime_assembly,
    build_source_adapters,
)
from qualstocks.ingestion.contract import (
    AdapterContractConfig,
    AdapterEventErrorCode,
    AdapterEventValidationError,
    AdapterEventValidationResult,
    NormalizedAdapterEvent,
    RawAdapterEvent,
    normalize_raw_adapter_event,
    validate_raw_adapter_event,
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
    IngestionOutcome,
    IngestionResult,
    IngestionService,
    IngestionValidationConfig,
    InMemoryAnalysisQueue,
    InMemoryEventRepository,
    SourceEventRepository,
    SourceEventStatus,
)
from qualstocks.ingestion.trading_persistence import (
    PaperTradingRepository,
    PersistenceResult,
    PersistenceStatus,
    TradingDatabaseClient,
)

__all__ = [
    "AnalysisJob",
    "AdapterContractConfig",
    "AdapterEventErrorCode",
    "AdapterEventValidationError",
    "AdapterEventValidationResult",
    "DatabaseClient",
    "FixtureSourceAdapter",
    "IngestedEvent",
    "IngestionOutcome",
    "IngestionResult",
    "IngestionRuntime",
    "IngestionService",
    "IngestionValidationConfig",
    "InMemoryAnalysisQueue",
    "InMemoryEventRepository",
    "NormalizedAdapterEvent",
    "RuntimeAssembly",
    "PaperTradingRepository",
    "PersistenceResult",
    "PersistenceStatus",
    "RawAdapterEvent",
    "SourceEventRepository",
    "SourceEventStatus",
    "PostgresAnalysisQueue",
    "PostgresSourceEventRepository",
    "PsycopgDatabaseClient",
    "TradingDatabaseClient",
    "build_persistence_components",
    "build_runtime_assembly",
    "build_source_adapters",
    "normalize_raw_adapter_event",
    "validate_raw_adapter_event",
]
