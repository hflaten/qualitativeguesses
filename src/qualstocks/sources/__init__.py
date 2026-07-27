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

__all__ = [
    "AdapterHealth",
    "AdapterHealthStatus",
    "AdapterKind",
    "BaseSourceAdapter",
    "FallbackPollingAdapter",
    "SourceAdapter",
    "StreamingApiAdapter",
    "WebSocketAdapter",
    "WebhookAdapter",
]

