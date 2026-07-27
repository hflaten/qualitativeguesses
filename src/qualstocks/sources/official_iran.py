from __future__ import annotations

from dataclasses import dataclass

from qualstocks.sources.official_us import HttpxTextFetchClient
from qualstocks.sources.registry import DEFAULT_SOURCE_REGISTRY
from qualstocks.sources.rss import KeywordFilter, RssFeedAdapter


IRAN_SIGNAL_KEYWORDS: tuple[str, ...] = (
    "iran",
    "tehran",
    "america",
    "united states",
    "us",
    "israel",
    "hormuz",
    "strait",
    "persian gulf",
    "gulf",
    "oil",
    "tanker",
    "sanctions",
    "strike",
    "missile",
    "nuclear",
    "war",
    "irgc",
    "navy",
    "ایران",
    "تهران",
    "آمریکا",
    "ایالات متحده",
    "اسرائیل",
    "هرمز",
    "تنگه هرمز",
    "خلیج فارس",
    "نفت",
    "نفتکش",
    "تحریم",
    "حمله",
    "موشک",
    "هسته‌ای",
    "جنگ",
    "سپاه",
    "نیروی دریایی",
)


@dataclass(frozen=True)
class IranSourceAccessNote:
    source_id: str
    source_name: str
    implemented: bool
    reason: str


def build_tasnim_rss_adapter(fetch_client: HttpxTextFetchClient | None = None) -> RssFeedAdapter:
    return RssFeedAdapter(
        source_definition=DEFAULT_SOURCE_REGISTRY.require("tasnim"),
        fetch_client=fetch_client or HttpxTextFetchClient(),
        keyword_filter=KeywordFilter(IRAN_SIGNAL_KEYWORDS),
    )


def build_official_iran_rss_adapters(
    fetch_client: HttpxTextFetchClient | None = None,
) -> tuple[RssFeedAdapter, ...]:
    adapters: list[RssFeedAdapter] = []
    for source_id in ("tasnim", "irna", "iran_foreign_ministry", "mehr", "fars", "presstv"):
        source_definition = DEFAULT_SOURCE_REGISTRY.require(source_id)
        if source_definition.url is None or "rss" not in {
            method.value for method in source_definition.access_methods
        }:
            continue
        if source_id != "tasnim":
            continue
        adapters.append(
            RssFeedAdapter(
                source_definition=source_definition,
                fetch_client=fetch_client or HttpxTextFetchClient(),
                keyword_filter=KeywordFilter(IRAN_SIGNAL_KEYWORDS),
            )
        )
    return tuple(adapters)


def iran_source_access_notes() -> tuple[IranSourceAccessNote, ...]:
    return (
        IranSourceAccessNote(
            source_id="tasnim",
            source_name=DEFAULT_SOURCE_REGISTRY.require("tasnim").name,
            implemented=True,
            reason="Official RSS page verified at https://www.tasnimnews.ir/fa/rss.",
        ),
        IranSourceAccessNote(
            source_id="irna",
            source_name=DEFAULT_SOURCE_REGISTRY.require("irna").name,
            implemented=False,
            reason="Official site verified, but no stable RSS URL is encoded until confirmed.",
        ),
        IranSourceAccessNote(
            source_id="iran_foreign_ministry",
            source_name=DEFAULT_SOURCE_REGISTRY.require("iran_foreign_ministry").name,
            implemented=False,
            reason="Official page source only; implement after stable feed/page parser review.",
        ),
        IranSourceAccessNote(
            source_id="mehr",
            source_name=DEFAULT_SOURCE_REGISTRY.require("mehr").name,
            implemented=False,
            reason="RSS/page access class exists, but exact feed URL needs confirmation.",
        ),
        IranSourceAccessNote(
            source_id="fars",
            source_name=DEFAULT_SOURCE_REGISTRY.require("fars").name,
            implemented=False,
            reason="RSS/page access class exists, but exact feed URL needs confirmation.",
        ),
        IranSourceAccessNote(
            source_id="presstv",
            source_name=DEFAULT_SOURCE_REGISTRY.require("presstv").name,
            implemented=False,
            reason="English source candidate; exact stable feed URL needs confirmation.",
        ),
    )
