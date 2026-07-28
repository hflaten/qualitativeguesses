from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import AsyncIterator, Protocol

from qualstocks.domain import SourceClass, SourceEvent
from qualstocks.sources.registry import SourceDefinition


class StrEnum(str, Enum):
    pass


class AdapterHealthStatus(StrEnum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


class AdapterKind(StrEnum):
    WEBSOCKET = "websocket"
    WEBHOOK = "webhook"
    STREAMING_API = "streaming_api"
    FALLBACK_POLLING = "fallback_polling"


@dataclass(frozen=True)
class AdapterHealth:
    source: str
    source_class: SourceClass
    kind: AdapterKind
    source_id: str | None = None
    status: AdapterHealthStatus = AdapterHealthStatus.UNKNOWN
    last_event_at: datetime | None = None
    last_checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_error: str | None = None

    @property
    def is_usable(self) -> bool:
        return self.status in {AdapterHealthStatus.HEALTHY, AdapterHealthStatus.DEGRADED}


class SourceAdapter(Protocol):
    source: str
    source_class: SourceClass
    kind: AdapterKind

    async def start(self) -> None:
        """Open the adapter connection or start its loop."""

    async def stop(self) -> None:
        """Close the adapter connection and release resources."""

    def health(self) -> AdapterHealth:
        """Return current adapter health without exposing secrets."""

    async def events(self) -> AsyncIterator[SourceEvent]:
        """Yield normalized source events."""


@dataclass
class BaseSourceAdapter:
    source: str
    source_class: SourceClass
    kind: AdapterKind
    source_definition: SourceDefinition | None = None
    _started: bool = False
    _last_event_at: datetime | None = None
    _last_error: str | None = None

    async def start(self) -> None:
        self._started = True
        self._last_error = None

    async def stop(self) -> None:
        self._started = False

    def health(self) -> AdapterHealth:
        if self._last_error:
            status = AdapterHealthStatus.DEGRADED if self._started else AdapterHealthStatus.DOWN
        elif self._started:
            status = AdapterHealthStatus.HEALTHY
        else:
            status = AdapterHealthStatus.UNKNOWN

        return AdapterHealth(
            source=self.source,
            source_class=self.source_class,
            kind=self.kind,
            source_id=self.source_definition.source_id if self.source_definition else None,
            status=status,
            last_event_at=self._last_event_at,
            last_error=self._last_error,
        )

    async def events(self) -> AsyncIterator[SourceEvent]:
        if False:
            yield self._record_event(
                title="placeholder",
                url="",
                payload={},
                source_timestamp=None,
            )

    def _record_event(
        self,
        *,
        title: str,
        url: str,
        payload: dict[str, object],
        instrument: str | None = None,
        source_timestamp: datetime | None = None,
    ) -> SourceEvent:
        event = SourceEvent(
            source=self.source,
            source_class=self.source_class,
            title=title,
            url=url,
            payload=payload,
            instrument=instrument,
            source_id=self.source_definition.source_id if self.source_definition else None,
            source_tier=self.source_definition.tier if self.source_definition else None,
            source_category=self.source_definition.category if self.source_definition else None,
            reliability_score=(
                self.source_definition.reliability_score if self.source_definition else None
            ),
            language=self.source_definition.language if self.source_definition else None,
            translation_required=(
                self.source_definition.translation_required if self.source_definition else False
            ),
            licensing_class=(
                self.source_definition.licensing_class if self.source_definition else None
            ),
            raw_event_ref=(
                payload.get("raw_event_ref")
                if isinstance(payload.get("raw_event_ref"), str)
                else None
            ),
            source_timestamp=source_timestamp,
        )
        self._last_event_at = event.first_seen_at
        return event

    def _record_error(self, message: str) -> None:
        self._last_error = message


class WebSocketAdapter(BaseSourceAdapter):
    def __init__(
        self,
        source: str,
        source_class: SourceClass,
        source_definition: SourceDefinition | None = None,
    ) -> None:
        super().__init__(
            source=source,
            source_class=source_class,
            kind=AdapterKind.WEBSOCKET,
            source_definition=source_definition,
        )


class WebhookAdapter(BaseSourceAdapter):
    def __init__(
        self,
        source: str,
        source_class: SourceClass,
        source_definition: SourceDefinition | None = None,
    ) -> None:
        super().__init__(
            source=source,
            source_class=source_class,
            kind=AdapterKind.WEBHOOK,
            source_definition=source_definition,
        )


class StreamingApiAdapter(BaseSourceAdapter):
    def __init__(
        self,
        source: str,
        source_class: SourceClass,
        source_definition: SourceDefinition | None = None,
    ) -> None:
        super().__init__(
            source=source,
            source_class=source_class,
            kind=AdapterKind.STREAMING_API,
            source_definition=source_definition,
        )


class FallbackPollingAdapter(BaseSourceAdapter):
    def __init__(
        self,
        source: str,
        source_class: SourceClass,
        source_definition: SourceDefinition | None = None,
    ) -> None:
        super().__init__(
            source=source,
            source_class=source_class,
            kind=AdapterKind.FALLBACK_POLLING,
            source_definition=source_definition,
        )
