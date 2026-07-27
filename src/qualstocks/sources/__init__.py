"""Source adapter contracts for event-triggered ingestion."""

from qualstocks.sources.adapters import (
    AdapterHealth,
    AdapterHealthStatus,
    AdapterKind,
    BaseSourceAdapter,
    FallbackPollingAdapter,
    SourceAdapter,
    StreamingApiAdapter,
    WebSocketAdapter,
    WebhookAdapter,
)
from qualstocks.sources.registry import (
    DEFAULT_SOURCE_DEFINITIONS,
    DEFAULT_SOURCE_REGISTRY,
    SourceDefinition,
    SourceRegistry,
)

__all__ = [
    "AdapterHealth",
    "AdapterHealthStatus",
    "AdapterKind",
    "BaseSourceAdapter",
    "DEFAULT_SOURCE_DEFINITIONS",
    "DEFAULT_SOURCE_REGISTRY",
    "FallbackPollingAdapter",
    "SourceAdapter",
    "SourceDefinition",
    "SourceRegistry",
    "StreamingApiAdapter",
    "WebSocketAdapter",
    "WebhookAdapter",
]
