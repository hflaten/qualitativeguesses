from __future__ import annotations

import time

from qualstocks.settings import load_settings


def main() -> None:
    settings = load_settings()
    print(
        "worker-service starting",
        {
            "app_env": settings.app_env,
            "runtime_secrets_present": settings.has_required_runtime_secrets,
        },
        flush=True,
    )
    print("worker-service waiting for durable analysis queue backend", flush=True)
    while True:
        time.sleep(30)


if __name__ == "__main__":
    main()
