from __future__ import annotations

import asyncio
from dataclasses import dataclass

from qualstocks.ingestion.service import IngestionResult, IngestionService
from qualstocks.sources import SourceAdapter


@dataclass
class IngestionRuntime:
    service: IngestionService
    adapters: tuple[SourceAdapter, ...]

    async def run_once(self) -> list[IngestionResult]:
        """Drain currently available events from all adapters.

        Push, stream, WebSocket, and fallback polling adapters all present as async
        event producers. Concrete adapters can decide whether this method returns
        quickly or blocks until their source yields.
        """
        results: list[IngestionResult] = []
        for adapter in self.adapters:
            await adapter.start()
            try:
                async for event in adapter.events():
                    results.append(await self.service.ingest(event))
            except Exception as exc:  # pragma: no cover - defensive boundary
                if hasattr(adapter, "_record_error"):
                    adapter._record_error(str(exc))
                raise
        return results

    async def run_forever(self, interval_seconds: float = 1.0) -> None:
        while True:
            await self.run_once()
            await asyncio.sleep(interval_seconds)

