from __future__ import annotations

import time

from qualstocks.settings import load_settings


def main() -> None:
    settings = load_settings()
    print(
        "watcher-service starting",
        {
            "app_env": settings.app_env,
            "paper_trading_only": settings.paper_trading_only,
            "max_open_hypotheses": settings.max_open_hypotheses,
        },
        flush=True,
    )
    print("watcher-service waiting for enabled source adapters", flush=True)
    while True:
        time.sleep(30)


if __name__ == "__main__":
    main()
