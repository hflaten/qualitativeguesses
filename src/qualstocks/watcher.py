from __future__ import annotations

import asyncio

from qualstocks.ingestion import RuntimeAssembly, build_runtime_assembly
from qualstocks.settings import load_settings


async def run_watcher(assembly: RuntimeAssembly) -> None:
    if not assembly.runtime.adapters:
        print("watcher-service has no enabled source adapters", flush=True)
        return
    await assembly.runtime.run_once()


async def run_watcher_forever(assembly: RuntimeAssembly, *, interval_seconds: int) -> None:
    if not assembly.runtime.adapters:
        print("watcher-service has no enabled source adapters", flush=True)
        return
    await assembly.runtime.run_forever(interval_seconds=interval_seconds)


async def async_main() -> None:
    settings = load_settings()
    assembly = build_runtime_assembly(settings)
    print(
        "watcher-service starting",
        {
            "app_env": settings.app_env,
            "paper_trading_only": settings.paper_trading_only,
            "max_open_hypotheses": settings.max_open_hypotheses,
            "adapter_source_ids": assembly.adapter_source_ids,
        },
        flush=True,
    )
    if settings.watcher_run_once:
        await run_watcher(assembly)
        return
    await run_watcher_forever(
        assembly,
        interval_seconds=settings.watcher_interval_seconds,
    )


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
