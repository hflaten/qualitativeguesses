from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, AsyncIterator, Protocol

from qualstocks.domain import SourceClass, SourceEvent
from qualstocks.sources.adapters import WebSocketAdapter
from qualstocks.sources.registry import DEFAULT_SOURCE_REGISTRY, SourceDefinition


class StrEnum(str, Enum):
    pass


class KalshiEnvironment(StrEnum):
    DEMO = "demo"
    PRODUCTION = "production"

    @property
    def rest_base_url(self) -> str:
        if self == KalshiEnvironment.PRODUCTION:
            return "https://external-api.kalshi.com/trade-api/v2"
        return "https://demo-api.kalshi.co/trade-api/v2"

    @property
    def websocket_url(self) -> str:
        if self == KalshiEnvironment.PRODUCTION:
            return "wss://external-api-ws.kalshi.com/trade-api/ws/v2"
        return "wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2"


class KalshiEventType(StrEnum):
    TICKER = "ticker"
    TRADE = "trade"
    MARKET_LIFECYCLE = "market_lifecycle_v2"


class KalshiSigner(Protocol):
    def authentication_headers(
        self,
        *,
        method: str,
        path: str,
        timestamp_ms: int | None = None,
    ) -> dict[str, str]:
        """Return Kalshi authentication headers for a REST or WebSocket request."""


class KalshiStreamClient(Protocol):
    async def subscribe(
        self,
        *,
        url: str,
        channels: tuple[str, ...],
        market_tickers: tuple[str, ...],
        auth_headers: dict[str, str],
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield raw Kalshi WebSocket messages."""


@dataclass(frozen=True)
class KalshiCredentials:
    api_key_id: str
    private_key_pem: str

    def __post_init__(self) -> None:
        if not self.api_key_id.strip():
            raise ValueError("api_key_id must be non-empty")
        if not self.private_key_pem.strip():
            raise ValueError("private_key_pem must be non-empty")


@dataclass(frozen=True)
class KalshiAuthSigner:
    credentials: KalshiCredentials

    def authentication_headers(
        self,
        *,
        method: str,
        path: str,
        timestamp_ms: int | None = None,
    ) -> dict[str, str]:
        timestamp = str(timestamp_ms or int(datetime.now(timezone.utc).timestamp() * 1000))
        signature = self._signature(timestamp=timestamp, method=method.upper(), path=path)
        return {
            "KALSHI-ACCESS-KEY": self.credentials.api_key_id,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
        }

    def _signature(self, *, timestamp: str, method: str, path: str) -> str:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        private_key = serialization.load_pem_private_key(
            self.credentials.private_key_pem.encode("utf-8"),
            password=None,
        )
        message = f"{timestamp}{method}{path}".encode("utf-8")
        signature = private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("ascii")


@dataclass(frozen=True)
class KalshiMarket:
    ticker: str
    title: str
    subtitle: str | None = None
    category: str | None = None
    tags: tuple[str, ...] = ()

    @property
    def normalized_text(self) -> str:
        return " ".join(
            (self.ticker, self.title, self.subtitle or "", self.category or "", " ".join(self.tags))
        ).lower()


@dataclass(frozen=True)
class KalshiSignalConfig:
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
        "shipping",
    )
    min_probability_delta: Decimal = Decimal("0.08")
    min_trade_count: Decimal = Decimal("100")
    min_probability: Decimal = Decimal("0.45")

    def market_is_relevant(self, market: KalshiMarket) -> bool:
        return any(keyword in market.normalized_text for keyword in self.keywords)

    def probability_is_trigger(
        self,
        probability: Decimal,
        previous_probability: Decimal | None,
    ) -> bool:
        if probability >= self.min_probability:
            return True
        if previous_probability is None:
            return False
        return abs(probability - previous_probability) >= self.min_probability_delta

    def trade_is_trigger(self, probability: Decimal, count: Decimal | None) -> bool:
        return probability >= self.min_probability or (
            count is not None and count >= self.min_trade_count
        )


@dataclass
class KalshiEventNormalizer:
    config: KalshiSignalConfig = field(default_factory=KalshiSignalConfig)
    source_definition: SourceDefinition = field(
        default_factory=lambda: DEFAULT_SOURCE_REGISTRY.require("kalshi")
    )
    _previous_probabilities: dict[str, Decimal] = field(default_factory=dict)

    def normalize(
        self,
        raw_event: dict[str, Any],
        *,
        market: KalshiMarket | None = None,
    ) -> tuple[SourceEvent, ...]:
        payload = _payload(raw_event)
        event_type = _event_type(raw_event, payload)
        market = market or _market_from_payload(payload)
        if market is not None and not self.config.market_is_relevant(market):
            return ()
        if event_type == KalshiEventType.TICKER:
            return self._normalize_ticker(raw_event, payload, market=market)
        if event_type == KalshiEventType.TRADE:
            return self._normalize_trade(raw_event, payload, market=market)
        if event_type == KalshiEventType.MARKET_LIFECYCLE:
            return self._normalize_market_lifecycle(raw_event, payload, market=market)
        return ()

    def _normalize_ticker(
        self,
        raw_event: dict[str, Any],
        payload: dict[str, Any],
        *,
        market: KalshiMarket | None,
    ) -> tuple[SourceEvent, ...]:
        market_ticker = _market_ticker(payload, market=market)
        probability = _probability(
            payload.get("yes_bid")
            or payload.get("yesBid")
            or payload.get("last_price")
            or payload.get("lastPrice")
            or payload.get("price")
        )
        if market_ticker is None or probability is None:
            return ()
        previous_probability = self._previous_probabilities.get(market_ticker)
        self._previous_probabilities[market_ticker] = probability
        if not self.config.probability_is_trigger(probability, previous_probability):
            return ()
        return (
            self._event(
                title=f"Kalshi ticker move: {_market_title(market, payload)}",
                url=_market_url(market_ticker),
                payload={
                    "kalshi_event_type": KalshiEventType.TICKER.value,
                    "market_ticker": market_ticker,
                    "market_title": market.title if market else _string(payload.get("title")),
                    "market_subtitle": (
                        market.subtitle if market else _string(payload.get("subtitle"))
                    ),
                    "probability": float(probability),
                    "previous_probability": (
                        float(previous_probability) if previous_probability is not None else None
                    ),
                    "probability_delta": (
                        float(probability - previous_probability)
                        if previous_probability is not None
                        else None
                    ),
                    "yes_bid": _float(payload.get("yes_bid") or payload.get("yesBid")),
                    "yes_ask": _float(payload.get("yes_ask") or payload.get("yesAsk")),
                    "last_price": _float(payload.get("last_price") or payload.get("lastPrice")),
                    "volume": _float(payload.get("volume")),
                    "open_interest": _float(payload.get("open_interest")),
                    "raw_event_ref": _raw_ref(raw_event, market_ticker=market_ticker),
                    "raw": raw_event,
                },
                source_timestamp=_timestamp(
                    payload.get("ts") or payload.get("timestamp") or raw_event.get("ts")
                ),
            ),
        )

    def _normalize_trade(
        self,
        raw_event: dict[str, Any],
        payload: dict[str, Any],
        *,
        market: KalshiMarket | None,
    ) -> tuple[SourceEvent, ...]:
        market_ticker = _market_ticker(payload, market=market)
        probability = _probability(
            payload.get("yes_price")
            or payload.get("yesPrice")
            or payload.get("price")
            or payload.get("last_price")
            or payload.get("lastPrice")
        )
        count = _decimal(payload.get("count") or payload.get("size") or payload.get("quantity"))
        if (
            market_ticker is None
            or probability is None
            or not self.config.trade_is_trigger(probability, count)
        ):
            return ()
        return (
            self._event(
                title=f"Kalshi trade: {_market_title(market, payload)}",
                url=_market_url(market_ticker),
                payload={
                    "kalshi_event_type": KalshiEventType.TRADE.value,
                    "market_ticker": market_ticker,
                    "market_title": market.title if market else _string(payload.get("title")),
                    "probability": float(probability),
                    "count": float(count) if count is not None else None,
                    "taker_side": _string(payload.get("taker_side") or payload.get("takerSide")),
                    "trade_id": _string(payload.get("trade_id") or payload.get("tradeId")),
                    "raw_event_ref": _raw_ref(raw_event, market_ticker=market_ticker),
                    "raw": raw_event,
                },
                source_timestamp=_timestamp(
                    payload.get("ts") or payload.get("timestamp") or raw_event.get("ts")
                ),
            ),
        )

    def _normalize_market_lifecycle(
        self,
        raw_event: dict[str, Any],
        payload: dict[str, Any],
        *,
        market: KalshiMarket | None,
    ) -> tuple[SourceEvent, ...]:
        market_ticker = _market_ticker(payload, market=market)
        status = _string(payload.get("status"))
        if market_ticker is None:
            return ()
        return (
            self._event(
                title=f"Kalshi market lifecycle: {_market_title(market, payload)}",
                url=_market_url(market_ticker),
                payload={
                    "kalshi_event_type": KalshiEventType.MARKET_LIFECYCLE.value,
                    "market_ticker": market_ticker,
                    "market_title": market.title if market else _string(payload.get("title")),
                    "market_subtitle": (
                        market.subtitle if market else _string(payload.get("subtitle"))
                    ),
                    "status": status,
                    "event_ticker": _string(
                        payload.get("event_ticker") or payload.get("eventTicker")
                    ),
                    "raw_event_ref": _raw_ref(raw_event, market_ticker=market_ticker),
                    "raw": raw_event,
                },
                source_timestamp=_timestamp(
                    payload.get("ts") or payload.get("timestamp") or raw_event.get("ts")
                ),
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


class KalshiAdapter(WebSocketAdapter):
    def __init__(
        self,
        *,
        market_tickers: tuple[str, ...],
        markets_by_ticker: dict[str, KalshiMarket],
        stream_client: KalshiStreamClient,
        signer: KalshiSigner,
        environment: KalshiEnvironment = KalshiEnvironment.DEMO,
        channels: tuple[str, ...] = (
            KalshiEventType.TICKER.value,
            KalshiEventType.TRADE.value,
            KalshiEventType.MARKET_LIFECYCLE.value,
        ),
        normalizer: KalshiEventNormalizer | None = None,
        reconnect_backoff_seconds: float = 1.0,
    ) -> None:
        source_definition = DEFAULT_SOURCE_REGISTRY.require("kalshi")
        super().__init__(
            source_definition.name,
            SourceClass.PREDICTION_MARKET,
            source_definition=source_definition,
        )
        self.market_tickers = market_tickers
        self.markets_by_ticker = markets_by_ticker
        self.stream_client = stream_client
        self.signer = signer
        self.environment = environment
        self.channels = channels
        self.normalizer = normalizer or KalshiEventNormalizer()
        self.reconnect_backoff_seconds = reconnect_backoff_seconds

    async def events(self) -> AsyncIterator[SourceEvent]:
        while self._started:
            try:
                auth_headers = self.signer.authentication_headers(
                    method="GET",
                    path="/trade-api/ws/v2",
                )
                async for raw_event in self.stream_client.subscribe(
                    url=self.environment.websocket_url,
                    channels=self.channels,
                    market_tickers=self.market_tickers,
                    auth_headers=auth_headers,
                ):
                    market = self._market_for_raw_event(raw_event)
                    for event in self.normalizer.normalize(raw_event, market=market):
                        self._last_event_at = event.first_seen_at
                        yield event
                return
            except Exception as exc:
                self._record_error(str(exc))
                await asyncio.sleep(self.reconnect_backoff_seconds)

    def _market_for_raw_event(self, raw_event: dict[str, Any]) -> KalshiMarket | None:
        payload = _payload(raw_event)
        market_ticker = _market_ticker(payload)
        if market_ticker and market_ticker in self.markets_by_ticker:
            return self.markets_by_ticker[market_ticker]
        return None


def _payload(raw_event: dict[str, Any]) -> dict[str, Any]:
    payload = raw_event.get("msg")
    if isinstance(payload, dict):
        return payload
    payload = raw_event.get("payload")
    if isinstance(payload, dict):
        return payload
    return raw_event


def _event_type(raw_event: dict[str, Any], payload: dict[str, Any]) -> str:
    return str(raw_event.get("type") or payload.get("type") or "")


def _market_from_payload(payload: dict[str, Any]) -> KalshiMarket | None:
    market_ticker = _string(payload.get("market_ticker") or payload.get("marketTicker"))
    title = _string(payload.get("title"))
    if market_ticker is None or title is None:
        return None
    return KalshiMarket(
        ticker=market_ticker,
        title=title,
        subtitle=_string(payload.get("subtitle")),
        category=_string(payload.get("category")),
        tags=_string_tuple(payload.get("tags")),
    )


def _market_ticker(payload: dict[str, Any], *, market: KalshiMarket | None = None) -> str | None:
    return (
        _string(payload.get("market_ticker") or payload.get("marketTicker"))
        or (market.ticker if market is not None else None)
    )


def _market_title(market: KalshiMarket | None, payload: dict[str, Any]) -> str:
    if market is not None:
        return market.title
    return _string(payload.get("title")) or _market_ticker(payload) or "unknown market"


def _market_url(market_ticker: str) -> str:
    return f"https://kalshi.com/markets/{market_ticker}"


def _raw_ref(raw_event: dict[str, Any], *, market_ticker: str) -> str:
    payload = _payload(raw_event)
    return ":".join(
        [
            "kalshi",
            _event_type(raw_event, payload) or "unknown",
            market_ticker,
            _string(payload.get("trade_id") or payload.get("tradeId")) or "",
            _string(payload.get("ts") or payload.get("timestamp") or raw_event.get("ts")) or "",
        ]
    )


def _timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, int):
        return datetime.fromtimestamp(_seconds(value), timezone.utc)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return datetime.fromtimestamp(_seconds(int(stripped)), timezone.utc)
        try:
            return datetime.fromisoformat(stripped.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _seconds(value: int) -> float:
    if value > 10_000_000_000:
        return value / 1000
    return float(value)


def _probability(value: object) -> Decimal | None:
    number = _decimal(value)
    if number is None:
        return None
    if number > 1:
        return number / Decimal("100")
    return number


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _float(value: object) -> float | None:
    number = _probability(value)
    return float(number) if number is not None else None


def _string(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in (_string(item) for item in value) if item is not None)
