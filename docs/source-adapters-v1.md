# Source Adapters V1

## Purpose

The watcher service converts external source updates into normalized `SourceEvent`
records for classification. V1 is event-triggered and paper-trading only. An
adapter must never create a trade or hypothesis directly.

## Adapter contract

Each adapter implements the same lifecycle:

- `start()` opens the connection or polling loop.
- `stop()` closes it and releases credentials.
- `health()` reports `healthy`, `degraded`, or `down`, plus last event time and
  last error.
- `events()` yields normalized `SourceEvent` values.

Every emitted event must include a stable source name, `SourceClass`, title, URL
or source reference, raw payload, and source timestamp when available. The
watcher adds `first_seen_at` and the event id. Invalid payloads are logged and
discarded; they do not stop other adapters.

## V1 adapter classes

| Class | Trigger and use | V1 behavior |
| --- | --- | --- |
| `WebSocketAdapter` | Long-lived feeds with pushed updates | Reconnect with bounded exponential backoff, heartbeat/timeouts, and sequence or cursor tracking where provided. |
| `WebhookAdapter` | Provider callbacks into `api-service` | Verify signature and timestamp, reject replayed requests, acknowledge quickly, and enqueue the payload for normalization. |
| `StreamingApiAdapter` | Server-sent events or chunked HTTP streams | Maintain the stream, parse complete messages only, reconnect from a cursor when supported, and expose backpressure metrics. |
| `FallbackPollingAdapter` | Sources without a dependable push interface | Poll on a source-specific interval, use conditional requests or cursors, and emit only unseen items. Polling is the recovery path for a failed push adapter where practical. |

All classes share: timeout and cancellation handling, structured logs, secret
redaction, rate-limit handling, raw payload retention, normalized timestamps in
UTC, and deterministic deduplication. A dedupe key should prefer the provider
event id; otherwise use a hash of source, URL, title, and source timestamp.

## Initial candidate sources

| Source | Source class | Preferred adapter | Fallback | First event shape to capture |
| --- | --- | --- | --- | --- |
| Polymarket | `prediction_market` | WebSocket | Polling API | Market, outcome, price/probability, volume, and update time. |
| Kalshi | `prediction_market` | WebSocket or streaming API | Polling API | Market, ticker, contract state, bid/ask or probability, and update time. |
| GDELT | `osint` | Streaming API where available | Polling API | Article URL, title, publication time, language, location, and matched topic/entity. |
| Official actor feeds | `official_actor` | Webhook or streaming API | Polling official pages/feeds | Issuer, statement text/title, canonical URL, publication time, and content hash. |
| Equinor and Oslo Bors announcements | `equinor_or_exchange` | Webhook or streaming API | Polling announcement pages/feeds | Issuer, announcement type, title, URL, publication time, and market relevance fields. |
| Norwegian confirmation feeds | `norwegian_confirmation` | Webhook or streaming API | Polling official Norwegian feeds | Issuer, confirmation type, text/title, canonical URL, publication time, and confirmation status. |

"Official actor feeds" and "Norwegian confirmation feeds" are source groups,
not one provider. Each concrete provider needs an owned adapter configuration
with endpoint, authentication, rate limit, parser version, and polling interval.

## Routing and failure policy

1. Start enabled adapters independently; one unavailable source must not block
   the watcher service.
2. Route each adapter to a source-specific normalizer, then to the common event
   queue.
3. On disconnect, retry with jitter and preserve the last cursor. After the
   retry budget is exhausted, mark the adapter degraded and activate its polling
   fallback if configured.
4. Do not silently downgrade authenticity: webhook signature failures and
   malformed official announcements are rejected and counted.
5. Keep raw payloads and adapter metadata for replay, parser debugging, and
   audit. Never log credentials or full signed requests.

## V1 readiness checklist

- [ ] Each candidate has an endpoint, credential ownership, rate limit, and
  documented fallback.
- [ ] Normalizers map into `SourceEvent` and the existing `SourceClass` values.
- [ ] Reconnect, timeout, rate-limit, duplicate, malformed-payload, and replay
  cases have focused tests.
- [ ] Health metrics cover connection state, lag, event count, errors, retries,
  and fallback activation.
- [ ] A replay fixture exists for at least one event per adapter class.
- [ ] Kill/restart testing confirms cursors and dedupe state do not create
  duplicate events.

