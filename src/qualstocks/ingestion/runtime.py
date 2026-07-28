from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from qualstocks.ingestion.service import IngestionResult, IngestionService
from qualstocks.sources import AdapterKind, SourceAdapter


@dataclass(frozen=True)
class AdapterBackoffPolicy:
    initial_seconds: float = 5.0
    max_seconds: float = 300.0
    multiplier: float = 2.0


@dataclass
class AdapterRuntimeState:
    consecutive_failures: int = 0
    next_retry_at: datetime | None = None


@dataclass
class IngestionRuntime:
    service: IngestionService
    adapters: tuple[SourceAdapter, ...]
    backoff_policy: AdapterBackoffPolicy = field(default_factory=AdapterBackoffPolicy)
    _adapter_states: dict[str, AdapterRuntimeState] = field(default_factory=dict)

    async def run_once(self, *, now: datetime | None = None) -> list[IngestionResult]:
        """Drain currently available events from all adapters.

        Push, stream, WebSocket, and fallback polling adapters all present as async
        event producers. Concrete adapters can decide whether this method returns
        quickly or blocks until their source yields.
        """
        checked_at = now or datetime.now(timezone.utc)
        results: list[IngestionResult] = []
        for adapter in self.adapters:
            state = self._adapter_state(adapter)
            if state.next_retry_at is not None and checked_at < state.next_retry_at:
                self.service.record_adapter_health(adapter.health())
                continue

            try:
                await adapter.start()
                async for event in adapter.events():
                    results.append(await self.service.ingest(event))
            except Exception as exc:  # pragma: no cover - defensive boundary
                if hasattr(adapter, "_record_error"):
                    adapter._record_error(str(exc))
                self._record_failure(adapter, state, checked_at)
                self.service.record_adapter_health(adapter.health())
                continue
            state.consecutive_failures = 0
            state.next_retry_at = None
            self.service.record_adapter_health(adapter.health())
        return results

    async def run_forever(self, interval_seconds: float = 1.0) -> None:
        while True:
            await self.run_once()
            await asyncio.sleep(interval_seconds)

    def _adapter_state(self, adapter: SourceAdapter) -> AdapterRuntimeState:
        source_id = adapter.health().source_id or adapter.source
        state = self._adapter_states.get(source_id)
        if state is None:
            state = AdapterRuntimeState()
            self._adapter_states[source_id] = state
        return state

    def _record_failure(
        self,
        adapter: SourceAdapter,
        state: AdapterRuntimeState,
        checked_at: datetime,
    ) -> None:
        state.consecutive_failures += 1
        if adapter.kind != AdapterKind.FALLBACK_POLLING:
            state.next_retry_at = None
            return
        exponent = max(0, state.consecutive_failures - 1)
        delay_seconds = min(
            self.backoff_policy.max_seconds,
            self.backoff_policy.initial_seconds * (self.backoff_policy.multiplier ** exponent),
        )
        state.next_retry_at = checked_at + timedelta(seconds=delay_seconds)
