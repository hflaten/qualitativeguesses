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
from qualstocks.sources.official_us import (
    OFFICIAL_US_KEYWORDS,
    HttpxTextFetchClient,
    build_centcom_rss_adapter,
    build_dod_rss_adapter,
    build_official_us_rss_adapters,
)
from qualstocks.sources.registry import (
    DEFAULT_SOURCE_DEFINITIONS,
    DEFAULT_SOURCE_REGISTRY,
    SourceDefinition,
    SourceRegistry,
)
from qualstocks.sources.rss import KeywordFilter, RssFeedAdapter, RssFeedNormalizer, RssItem
from qualstocks.sources.polymarket import (
    PolymarketAdapter,
    PolymarketEventNormalizer,
    PolymarketEventType,
    PolymarketMarket,
    PolymarketSignalConfig,
)

__all__ = [
    "AdapterHealth",
    "AdapterHealthStatus",
    "AdapterKind",
    "BaseSourceAdapter",
    "DEFAULT_SOURCE_DEFINITIONS",
    "DEFAULT_SOURCE_REGISTRY",
    "FallbackPollingAdapter",
    "HttpxTextFetchClient",
    "KeywordFilter",
    "OFFICIAL_US_KEYWORDS",
    "PolymarketAdapter",
    "PolymarketEventNormalizer",
    "PolymarketEventType",
    "PolymarketMarket",
    "PolymarketSignalConfig",
    "SourceAdapter",
    "SourceDefinition",
    "SourceRegistry",
    "StreamingApiAdapter",
    "WebSocketAdapter",
    "WebhookAdapter",
    "RssFeedAdapter",
    "RssFeedNormalizer",
    "RssItem",
    "build_centcom_rss_adapter",
    "build_dod_rss_adapter",
    "build_official_us_rss_adapters",
]
