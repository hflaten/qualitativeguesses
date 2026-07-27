from __future__ import annotations

from hashlib import sha256

from qualstocks.domain import SourceEvent


def build_idempotency_key(event: SourceEvent) -> str:
    """Build a deterministic key for deduping source events before AI analysis."""
    timestamp = event.source_timestamp.isoformat() if event.source_timestamp else ""
    parts = (
        event.source.strip().lower(),
        event.source_class.value,
        event.url.strip().lower(),
        event.title.strip().lower(),
        timestamp,
    )
    digest = sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return f"{event.source_class.value}:{event.source.strip().lower()}:{digest}"

