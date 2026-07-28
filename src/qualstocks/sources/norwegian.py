from __future__ import annotations

from dataclasses import dataclass

from qualstocks.sources.official_us import HttpxTextFetchClient
from qualstocks.sources.registry import DEFAULT_SOURCE_REGISTRY
from qualstocks.sources.rss import KeywordFilter, RssFeedAdapter


NORWEGIAN_CONFIRMATION_KEYWORDS: tuple[str, ...] = (
    "equinor",
    "statoil",
    "oslo bors",
    "oslo børs",
    "borsmelding",
    "børsmelding",
    "aksjelive",
    "olje",
    "oljepris",
    "brent",
    "iran",
    "usa",
    "us",
    "israel",
    "hormuz",
    "hormuzstredet",
    "persiabukta",
    "persiske gulf",
    "tanker",
    "shipping",
    "sanksjoner",
    "angrep",
    "missil",
    "krig",
    "atom",
)


@dataclass(frozen=True)
class NorwegianSourceAccessNote:
    source_id: str
    source_name: str
    implemented: bool
    reason: str


def build_e24_rss_adapter(
    fetch_client: HttpxTextFetchClient | None = None,
) -> RssFeedAdapter:
    return RssFeedAdapter(
        source_definition=DEFAULT_SOURCE_REGISTRY.require("e24"),
        fetch_client=fetch_client or HttpxTextFetchClient(),
        keyword_filter=KeywordFilter(NORWEGIAN_CONFIRMATION_KEYWORDS),
    )


def build_norwegian_confirmation_rss_adapters(
    fetch_client: HttpxTextFetchClient | None = None,
) -> tuple[RssFeedAdapter, ...]:
    return (build_e24_rss_adapter(fetch_client=fetch_client),)


def norwegian_source_access_notes() -> tuple[NorwegianSourceAccessNote, ...]:
    return (
        NorwegianSourceAccessNote(
            source_id="e24",
            source_name=DEFAULT_SOURCE_REGISTRY.require("e24").name,
            implemented=True,
            reason=(
                "Official E24 RSS overview lists Bors og finans at "
                "http://e24.no/rss/?seksjon=boers-og-finans."
            ),
        ),
        NorwegianSourceAccessNote(
            source_id="dn",
            source_name=DEFAULT_SOURCE_REGISTRY.require("dn").name,
            implemented=False,
            reason=(
                "DN publishes RSS feeds, but category/topic-specific feed URL "
                "selection needs endpoint capture before live ingestion."
            ),
        ),
        NorwegianSourceAccessNote(
            source_id="euronext_newsweb",
            source_name=DEFAULT_SOURCE_REGISTRY.require("euronext_newsweb").name,
            implemented=False,
            reason=(
                "NewsWeb is the primary borsmelding source; implement after "
                "selecting a stable machine endpoint or page parser."
            ),
        ),
        NorwegianSourceAccessNote(
            source_id="equinor_ir",
            source_name=DEFAULT_SOURCE_REGISTRY.require("equinor_ir").name,
            implemented=False,
            reason=(
                "Equinor has official news and subscription pages; implement "
                "after selecting a reliable stock-market-announcement endpoint."
            ),
        ),
    )
