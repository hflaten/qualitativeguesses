from __future__ import annotations

from dataclasses import dataclass

from qualstocks.sources.registry import DEFAULT_SOURCE_REGISTRY
from qualstocks.sources.rss import KeywordFilter, RssFeedAdapter


OFFICIAL_US_KEYWORDS: tuple[str, ...] = (
    "iran",
    "iraq",
    "israel",
    "gulf",
    "hormuz",
    "oil",
    "sanctions",
    "strike",
    "missile",
    "nuclear",
    "military",
    "centcom",
    "tanker",
    "red sea",
)


@dataclass(frozen=True)
class HttpxTextFetchClient:
    timeout_seconds: float = 10.0

    async def get_text(self, url: str) -> str:
        import httpx

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text


def build_dod_rss_adapter(fetch_client: HttpxTextFetchClient | None = None) -> RssFeedAdapter:
    return RssFeedAdapter(
        source_definition=DEFAULT_SOURCE_REGISTRY.require("dod_rss"),
        fetch_client=fetch_client or HttpxTextFetchClient(),
        keyword_filter=KeywordFilter(OFFICIAL_US_KEYWORDS),
    )


def build_centcom_rss_adapter(fetch_client: HttpxTextFetchClient | None = None) -> RssFeedAdapter:
    return RssFeedAdapter(
        source_definition=DEFAULT_SOURCE_REGISTRY.require("centcom_rss"),
        fetch_client=fetch_client or HttpxTextFetchClient(),
        keyword_filter=KeywordFilter(OFFICIAL_US_KEYWORDS),
    )


def build_official_us_rss_adapters(
    fetch_client: HttpxTextFetchClient | None = None,
) -> tuple[RssFeedAdapter, ...]:
    return (
        build_dod_rss_adapter(fetch_client=fetch_client),
        build_centcom_rss_adapter(fetch_client=fetch_client),
    )
