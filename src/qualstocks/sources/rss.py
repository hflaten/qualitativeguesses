from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import AsyncIterator, Protocol
from xml.etree import ElementTree

from qualstocks.domain import SourceEvent
from qualstocks.sources.adapters import FallbackPollingAdapter
from qualstocks.sources.registry import SourceDefinition


class TextFetchClient(Protocol):
    async def get_text(self, url: str) -> str:
        """Fetch UTF-8 text from a source URL."""


@dataclass(frozen=True)
class RssItem:
    title: str
    link: str
    guid: str | None
    published_at: datetime | None
    summary: str

    @property
    def canonical_ref(self) -> str:
        return self.guid or self.link or self.title


@dataclass(frozen=True)
class KeywordFilter:
    keywords: tuple[str, ...]

    def matches(self, item: RssItem) -> bool:
        text = f"{item.title} {item.summary}".lower()
        return any(keyword.lower() in text for keyword in self.keywords)


@dataclass
class RssFeedNormalizer:
    source_definition: SourceDefinition
    keyword_filter: KeywordFilter

    def normalize(self, xml_text: str) -> tuple[SourceEvent, ...]:
        events: list[SourceEvent] = []
        for item in parse_rss_items(xml_text):
            if not self.keyword_filter.matches(item):
                continue
            events.append(
                SourceEvent(
                    source=self.source_definition.name,
                    source_class=self.source_definition.source_class,
                    title=item.title,
                    url=item.link,
                    payload={
                        "summary": item.summary,
                        "guid": item.guid,
                        "raw_event_ref": item.canonical_ref,
                        "source_feed_url": self.source_definition.url,
                    },
                    source_id=self.source_definition.source_id,
                    source_tier=self.source_definition.tier,
                    source_category=self.source_definition.category,
                    reliability_score=self.source_definition.reliability_score,
                    language=self.source_definition.language,
                    translation_required=self.source_definition.translation_required,
                    licensing_class=self.source_definition.licensing_class,
                    raw_event_ref=item.canonical_ref,
                    source_timestamp=item.published_at,
                )
            )
        return tuple(events)


class RssFeedAdapter(FallbackPollingAdapter):
    def __init__(
        self,
        *,
        source_definition: SourceDefinition,
        fetch_client: TextFetchClient,
        keyword_filter: KeywordFilter,
    ) -> None:
        super().__init__(
            source_definition.name,
            source_definition.source_class,
            source_definition=source_definition,
        )
        self.source_definition = source_definition
        self.fetch_client = fetch_client
        self.keyword_filter = keyword_filter
        self.normalizer = RssFeedNormalizer(
            source_definition=self.source_definition,
            keyword_filter=self.keyword_filter,
        )

    async def events(self) -> AsyncIterator[SourceEvent]:
        if self.source_definition.url is None:
            self._record_error("RSS source has no URL")
            return
        xml_text = await self.fetch_client.get_text(self.source_definition.url)
        for event in self.normalizer.normalize(xml_text):
            self._last_event_at = event.first_seen_at
            yield event


def parse_rss_items(xml_text: str) -> tuple[RssItem, ...]:
    root = ElementTree.fromstring(xml_text)
    items: list[RssItem] = []
    for element in root.findall(".//item"):
        title = _child_text(element, "title")
        link = _child_text(element, "link")
        guid = _child_text(element, "guid") or None
        published_at = _published_at(_child_text(element, "pubDate"))
        summary = (
            _child_text(element, "description")
            or _child_text(element, "{http://purl.org/rss/1.0/modules/content/}encoded")
        )
        if not title:
            continue
        items.append(
            RssItem(
                title=title,
                link=link,
                guid=guid,
                published_at=published_at,
                summary=summary,
            )
        )
    return tuple(items)


def _child_text(element: ElementTree.Element, child_name: str) -> str:
    child = element.find(child_name)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def _published_at(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
