from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Mapping

from qualstocks.runtime_health import (
    ServiceName,
    service_health_payload,
    validate_service_startup,
)
from qualstocks.settings import Settings, load_settings


@dataclass(frozen=True)
class SmokeCheck:
    name: str
    ok: bool
    severity: str
    detail: str

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "ok": self.ok,
            "severity": self.severity,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class RuntimeSmokeReport:
    ok: bool
    checks: tuple[SmokeCheck, ...]
    services: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "checks": [check.as_dict() for check in self.checks],
            "services": self.services,
        }


def run_runtime_smoke_checks(
    settings: Settings,
    *,
    environ: Mapping[str, str] | None = None,
) -> RuntimeSmokeReport:
    env = environ if environ is not None else os.environ
    validations = tuple(
        validate_service_startup(settings, service, environ=env)
        for service in (
            ServiceName.API,
            ServiceName.WATCHER,
            ServiceName.AI_WORKER,
            ServiceName.PAPER_WORKER,
        )
    )
    services = service_health_payload(settings)
    checks: list[SmokeCheck] = []
    for validation in validations:
        checks.append(
            SmokeCheck(
                name=f"startup:{validation.service.value}",
                ok=validation.ok,
                severity="error" if validation.errors else "warning",
                detail=_validation_detail(validation.errors, validation.warnings),
            )
        )
    for name in ("api", "watcher", "ai_worker", "quote_provider", "paper_trading_worker"):
        component = services[name]
        status = str(component.get("status"))
        checks.append(
            SmokeCheck(
                name=f"component:{name}",
                ok=status == "healthy",
                severity="error",
                detail=str(component.get("detail") or status),
            )
        )
    checks.append(_paper_live_gate_check(settings))
    return RuntimeSmokeReport(
        ok=all(check.ok for check in checks),
        checks=tuple(checks),
        services=services,
    )


def main() -> None:
    report = run_runtime_smoke_checks(load_settings())
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    raise SystemExit(0 if report.ok else 1)


def _paper_live_gate_check(settings: Settings) -> SmokeCheck:
    ok = (
        settings.paper_trading_only
        and not settings.live_trading_enabled
        and settings.max_open_hypotheses == 1
    )
    detail = (
        "paper trading only; live trading disabled; one hypothesis"
        if ok
        else "requires PAPER_TRADING_ONLY=true, LIVE_TRADING_ENABLED=false, MAX_OPEN_HYPOTHESES=1"
    )
    return SmokeCheck(
        name="live_gate:paper_only",
        ok=ok,
        severity="error",
        detail=detail,
    )


def _validation_detail(errors: tuple[str, ...], warnings: tuple[str, ...]) -> str:
    findings = errors or warnings
    return "; ".join(findings) if findings else "startup validation passed"


if __name__ == "__main__":
    main()
