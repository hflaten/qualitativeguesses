from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, AsyncIterator, Protocol

from qualstocks.domain import SourceClass, SourceEvent
from qualstocks.sources.adapters import AdapterKind, WebSocketAdapter
from qualstocks.sources.registry import DEFAULT_SOURCE_REGISTRY, SourceDefinition


class StrEnum(str, Enum):
    pass


class PolymarketEventType(StrEnum):
    PRICE_CHANGE = "price_change"
    LAST_TRADE_PRICE = "last_trade_price"
    BEST_BID_ASK = "best_bid_ask"
    NEW_MARKET = "new_market"
    MARKET_RESOLVED = "market_resolved"


class PolymarketStreamClient(Protocol):
    async def subscribe_market(
        self,
        token_ids: tuple[str, ...],
        *,
        custom_feature_enabled: bool,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield raw Polymarket market-stream payloads."""


@dataclass(frozen=True)
class PolymarketMarket:
    market_id: str
    question: str
    slug: str | None = None
    token_ids: tuple[str, ...] = ()
    outcomes: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    @property
    def normalized_text(self) -> str:
        return " ".join((self.question, self.slug or "", " ".join(self.tags))).lower()


@dataclass(frozen=True)
class PolymarketSignalConfig:
    keywords: tuple[str, ...] = (
        "iran",
        "us-iran",
        "u.s.-iran",
        "oil",
        "brent",
        "wti",
        "hormuz",
        "strait of hormuz",
        "israel",
        "sanctions",
        "war",
        "nuclear",
        "missile",
        "tanker",
    )
    min_price_delta: Decimal = Decimal("0.08")
    min_trade_size: Decimal = Decimal("100")
    min_probability: Decimal = Decimal("0.45")

    def market_is_relevant(self, market: PolymarketMarket) -> bool:
        return any(keyword in market.normalized_text for keyword in self.keywords)

    def price_change_is_trigger(self, price: Decimal, previous_price: Decimal | None) -> bool:
        if price >= self.min_probability:
            return True
        if previous_price is None:
            return False
        return abs(price - previous_price) >= self.min_price_delta

    def trade_is_trigger(self, price: Decimal, size: Decimal | None) -> bool:
        return price >= self.min_probability or (
            size is not None and size >= self.min_trade_size
        )


@dataclass
class PolymarketEventNormalizer:
    config: PolymarketSignalConfig = field(default_factory=PolymarketSignalConfig)
    source_definition: SourceDefinition = field(
        default_factory=lambda: DEFAULT_SOURCE_REGISTRY.require("polymarket")
    )
    _previous_prices: dict[str, Decimal] = field(default_factory=dict)

    def normalize(
        self,
        raw_event: dict[str, Any],
        *,
        market: PolymarketMarket | None = None,
    ) -> tuple[SourceEvent, ...]:
        event_type = str(raw_event.get("type", ""))
        if event_type == PolymarketEventType.NEW_MARKET:
            return self._normalize_new_market(raw_event)
        if event_type == PolymarketEventType.MARKET_RESOLVED:
            return self._normalize_market_resolved(raw_event, market=market)
        if market is not None and not self.config.market_is_relevant(market):
            return ()
        if event_type == PolymarketEventType.PRICE_CHANGE:
            return self._normalize_price_change(raw_event, market=market)
        if event_type == PolymarketEventType.LAST_TRADE_PRICE:
            return self._normalize_last_trade_price(raw_event, market=market)
        if event_type == PolymarketEventType.BEST_BID_ASK:
            return self._normalize_best_bid_ask(raw_event, market=market)
        return ()

    def _normalize_new_market(self, raw_event: dict[str, Any]) -> tuple[SourceEvent, ...]:
        payload = _payload(raw_event)
        market = _market_from_payload(payload)
        if not self.config.market_is_relevant(market):
            return ()
        event = self._event(
            title=f"New Polymarket market: {market.question}",
            url=_market_url(market),
            payload={
                "polymarket_event_type": PolymarketEventType.NEW_MARKET.value,
                "market_id": market.market_id,
                "market_question": market.question,
                "market_slug": market.slug,
                "token_ids": market.token_ids,
                "outcomes": market.outcomes,
                "tags": market.tags,
                "raw_event_ref": _raw_ref(raw_event),
                "raw": raw_event,
            },
            source_timestamp=_timestamp(payload.get("timestamp")),
        )
        return (event,)

    def _normalize_market_resolved(
        self,
        raw_event: dict[str, Any],
        *,
        market: PolymarketMarket | None,
    ) -> tuple[SourceEvent, ...]:
        payload = _payload(raw_event)
        market = market or _market_from_payload(payload)
        if not self.config.market_is_relevant(market):
            return ()
        event = self._event(
            title=f"Polymarket resolved: {market.question}",
            url=_market_url(market),
            payload={
                "polymarket_event_type": PolymarketEventType.MARKET_RESOLVED.value,
                "market_id": market.market_id,
                "market_question": market.question,
                "market_slug": market.slug,
                "winning_token_id": _string(payload.get("winningTokenId")),
                "winning_outcome": _string(payload.get("winningOutcome")),
                "token_ids": _string_tuple(payload.get("tokenIds")),
                "raw_event_ref": _raw_ref(raw_event),
                "raw": raw_event,
            },
            source_timestamp=_timestamp(payload.get("timestamp")),
        )
        return (event,)

    def _normalize_price_change(
        self,
        raw_event: dict[str, Any],
        *,
        market: PolymarketMarket | None,
    ) -> tuple[SourceEvent, ...]:
        payload = _payload(raw_event)
        events: list[SourceEvent] = []
        for change in _list_of_dicts(payload.get("priceChanges")):
            token_id = _string(change.get("tokenId") or change.get("token_id"))
            price = _decimal(change.get("price"))
            if token_id is None or price is None:
                continue
            previous_price = self._previous_prices.get(token_id)
            self._previous_prices[token_id] = price
            if not self.config.price_change_is_trigger(price, previous_price):
                continue
            events.append(
                self._event(
                    title=f"Polymarket price change: {_market_question(market, payload)}",
                    url=_market_url(market),
                    payload={
                        "polymarket_event_type": PolymarketEventType.PRICE_CHANGE.value,
                        "market_id": _string(payload.get("market")),
                        "market_question": market.question if market else None,
                        "market_slug": market.slug if market else None,
                        "token_id": token_id,
                        "probability": float(price),
                        "previous_probability": (
                            float(previous_price) if previous_price is not None else None
                        ),
                        "probability_delta": (
                            float(price - previous_price)
                            if previous_price is not None
                            else None
                        ),
                        "side": _string(change.get("side")),
                        "best_bid": _float(change.get("bestBid") or change.get("best_bid")),
                        "best_ask": _float(change.get("bestAsk") or change.get("best_ask")),
                        "size": _float(change.get("size")),
                        "raw_event_ref": _raw_ref(raw_event, token_id=token_id),
                        "raw": raw_event,
                    },
                    source_timestamp=_timestamp(payload.get("timestamp")),
                )
            )
        return tuple(events)

    def _normalize_last_trade_price(
        self,
        raw_event: dict[str, Any],
        *,
        market: PolymarketMarket | None,
    ) -> tuple[SourceEvent, ...]:
        payload = _payload(raw_event)
        token_id = _string(payload.get("tokenId") or payload.get("token_id"))
        price = _decimal(payload.get("price"))
        size = _decimal(payload.get("size"))
        if token_id is None or price is None or not self.config.trade_is_trigger(price, size):
            return ()
        return (
            self._event(
                title=f"Polymarket trade: {_market_question(market, payload)}",
                url=_market_url(market),
                payload={
                    "polymarket_event_type": PolymarketEventType.LAST_TRADE_PRICE.value,
                    "market_id": _string(payload.get("market")),
                    "market_question": market.question if market else None,
                    "market_slug": market.slug if market else None,
                    "token_id": token_id,
                    "probability": float(price),
                    "size": float(size) if size is not None else None,
                    "side": _string(payload.get("side")),
                    "transaction_hash": _string(payload.get("transactionHash")),
                    "raw_event_ref": _raw_ref(raw_event, token_id=token_id),
                    "raw": raw_event,
                },
                source_timestamp=_timestamp(payload.get("timestamp")),
            ),
        )

    def _normalize_best_bid_ask(
        self,
        raw_event: dict[str, Any],
        *,
        market: PolymarketMarket | None,
    ) -> tuple[SourceEvent, ...]:
        payload = _payload(raw_event)
        token_id = _string(payload.get("tokenId") or payload.get("token_id"))
        best_bid = _decimal(payload.get("bestBid") or payload.get("best_bid"))
        best_ask = _decimal(payload.get("bestAsk") or payload.get("best_ask"))
        probability = _midpoint(best_bid, best_ask)
        if token_id is None or probability is None:
            return ()
        previous_price = self._previous_prices.get(token_id)
        self._previous_prices[token_id] = probability
        if not self.config.price_change_is_trigger(probability, previous_price):
            return ()
        return (
            self._event(
                title=f"Polymarket top-of-book change: {_market_question(market, payload)}",
                url=_market_url(market),
                payload={
                    "polymarket_event_type": PolymarketEventType.BEST_BID_ASK.value,
                    "market_id": _string(payload.get("market")),
                    "market_question": market.question if market else None,
                    "market_slug": market.slug if market else None,
                    "token_id": token_id,
                    "probability": float(probability),
                    "previous_probability": (
                        float(previous_price) if previous_price is not None else None
                    ),
                    "probability_delta": (
                        float(probability - previous_price)
                        if previous_price is not None
                        else None
                    ),
                    "best_bid": float(best_bid) if best_bid is not None else None,
                    "best_ask": float(best_ask) if best_ask is not None else None,
                    "raw_event_ref": _raw_ref(raw_event, token_id=token_id),
                    "raw": raw_event,
                },
                source_timestamp=_timestamp(payload.get("timestamp")),
            ),
        )

    def _event(
        self,
        *,
        title: str,
        url: str,
        payload: dict[str, Any],
        source_timestamp: datetime | None,
    ) -> SourceEvent:
        return SourceEvent(
            source=self.source_definition.name,
            source_class=self.source_definition.source_class,
            title=title,
            url=url,
            payload=payload,
            source_id=self.source_definition.source_id,
            source_tier=self.source_definition.tier,
            source_category=self.source_definition.category,
            reliability_score=self.source_definition.reliability_score,
            language=self.source_definition.language,
            translation_required=self.source_definition.translation_required,
            licensing_class=self.source_definition.licensing_class,
            raw_event_ref=_string(payload.get("raw_event_ref")),
            source_timestamp=source_timestamp,
        )


class PolymarketAdapter(WebSocketAdapter):
    def __init__(
        self,
        *,
        token_ids: tuple[str, ...],
        markets_by_token_id: dict[str, PolymarketMarket],
        stream_client: PolymarketStreamClient,
        normalizer: PolymarketEventNormalizer | None = None,
        reconnect_backoff_seconds: float = 1.0,
    ) -> None:
        source_definition = DEFAULT_SOURCE_REGISTRY.require("polymarket")
        super().__init__(
            source_definition.name,
            SourceClass.PREDICTION_MARKET,
            source_definition=source_definition,
        )
        self.token_ids = token_ids
        self.markets_by_token_id = markets_by_token_id
        self.stream_client = stream_client
        self.normalizer = normalizer or PolymarketEventNormalizer()
        self.reconnect_backoff_seconds = reconnect_backoff_seconds

    async def events(self) -> AsyncIterator[SourceEvent]:
        while self._started:
            try:
                async for raw_event in self.stream_client.subscribe_market(
                    self.token_ids,
                    custom_feature_enabled=True,
                ):
                    market = self._market_for_raw_event(raw_event)
                    for event in self.normalizer.normalize(raw_event, market=market):
                        self._last_event_at = event.first_seen_at
                        yield event
                return
            except Exception as exc:
                self._record_error(str(exc))
                await asyncio.sleep(self.reconnect_backoff_seconds)

    def _market_for_raw_event(self, raw_event: dict[str, Any]) -> PolymarketMarket | None:
        payload = _payload(raw_event)
        token_id = _string(payload.get("tokenId") or payload.get("token_id"))
        if token_id and token_id in self.markets_by_token_id:
            return self.markets_by_token_id[token_id]
        for change in _list_of_dicts(payload.get("priceChanges")):
            token_id = _string(change.get("tokenId") or change.get("token_id"))
            if token_id and token_id in self.markets_by_token_id:
                return self.markets_by_token_id[token_id]
        return None


def _payload(raw_event: dict[str, Any]) -> dict[str, Any]:
    payload = raw_event.get("payload")
    return payload if isinstance(payload, dict) else {}


def _market_from_payload(payload: dict[str, Any]) -> PolymarketMarket:
    event_message = payload.get("eventMessage")
    if not isinstance(event_message, dict):
        event_message = {}
    question = (
        _string(payload.get("question"))
        or _string(event_message.get("title"))
        or _string(payload.get("description"))
        or "Unknown Polymarket market"
    )
    slug = _string(payload.get("slug")) or _string(event_message.get("slug"))
    return PolymarketMarket(
        market_id=_string(payload.get("market") or payload.get("id")) or "unknown",
        question=question,
        slug=slug,
        token_ids=_string_tuple(payload.get("tokenIds") or payload.get("clobTokenIds")),
        outcomes=_string_tuple(payload.get("outcomes")),
        tags=_string_tuple(payload.get("tags")),
    )


def _market_question(market: PolymarketMarket | None, payload: dict[str, Any]) -> str:
    if market is not None:
        return market.question
    return _string(payload.get("market")) or "unknown market"


def _market_url(market: PolymarketMarket | None) -> str:
    if market and market.slug:
        return f"https://polymarket.com/event/{market.slug}"
    return "https://polymarket.com/"


def _raw_ref(raw_event: dict[str, Any], *, token_id: str | None = None) -> str:
    payload = _payload(raw_event)
    parts = [
        "polymarket",
        _string(raw_event.get("type")) or "unknown",
        _string(payload.get("market") or payload.get("id")) or "unknown",
        token_id or _string(payload.get("tokenId") or payload.get("token_id")) or "",
        _string(payload.get("timestamp")) or "",
    ]
    return ":".join(parts)


def _timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, int):
        return datetime.fromtimestamp(value / 1000, timezone.utc)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return datetime.fromtimestamp(int(stripped) / 1000, timezone.utc)
        try:
            return datetime.fromisoformat(stripped.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _float(value: object) -> float | None:
    number = _decimal(value)
    return float(number) if number is not None else None


def _midpoint(first: Decimal | None, second: Decimal | None) -> Decimal | None:
    if first is not None and second is not None:
        return (first + second) / Decimal("2")
    return first or second


def _string(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in (_string(item) for item in value) if item is not None)


def _list_of_dicts(value: object) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, dict))
