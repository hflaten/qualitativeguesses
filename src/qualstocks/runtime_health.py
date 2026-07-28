from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from qualstocks.settings import Settings


class ServiceName(str, Enum):
    API = "api-service"
    WATCHER = "watcher-service"
    AI_WORKER = "worker-service"
    PAPER_WORKER = "paper-trading-worker"


@dataclass(frozen=True)
class StartupValidation:
    service: ServiceName
    ok: bool
    strict: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    def raise_for_errors(self) -> None:
        if self.errors:
            raise RuntimeError("; ".join(self.errors))

    def as_log_payload(self) -> dict[str, object]:
        return {
            "service": self.service.value,
            "ok": self.ok,
            "strict": self.strict,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def validate_service_startup(
    settings: Settings,
    service: ServiceName,
    *,
    environ: Mapping[str, str] | None = None,
) -> StartupValidation:
    env = environ if environ is not None else os.environ
    strict = _is_production(settings)
    findings: list[str] = []

    findings.extend(_paper_only_findings(settings))
    findings.extend(_missing_required_env(service, settings, env, strict=strict))
    findings.extend(_service_mode_findings(service, settings))

    errors = tuple(findings if strict else _strict_only_findings(findings))
    warnings = tuple(() if strict else findings)
    return StartupValidation(
        service=service,
        ok=not errors,
        strict=strict,
        errors=errors,
        warnings=warnings,
    )


def service_health_payload(settings: Settings) -> dict[str, object]:
    watcher_configured = (
        settings.source_fixture_mode_enabled
        or settings.source_official_us_rss_enabled
        or settings.source_official_iran_rss_enabled
        or settings.source_norwegian_confirmation_rss_enabled
        or settings.source_lseg_reuters_enabled
        or settings.source_ap_media_api_enabled
    )
    ai_worker_configured = (
        settings.source_persistence_backend == "postgres"
        and bool(settings.supabase_db_url and settings.openai_api_key)
    )
    return {
        "api": _component("api-service", True, "serving HTTP health and dashboard API"),
        "watcher": _component(
            "watcher-service",
            watcher_configured,
            "no adapters enabled",
        ),
        "ai_worker": _component(
            "worker-service",
            ai_worker_configured,
            "requires postgres persistence, SUPABASE_DB_URL, and OPENAI_API_KEY",
        ),
        "quote_provider": _component(
            "quote-provider",
            bool(settings.quote_source and settings.quote_instrument),
            "quote source or instrument missing",
        ),
        "paper_trading_worker": _component(
            "paper-trading-worker",
            settings.paper_trading_only and settings.max_open_hypotheses == 1,
            "requires PAPER_TRADING_ONLY=true and MAX_OPEN_HYPOTHESES=1",
        ),
    }


def _is_production(settings: Settings) -> bool:
    return settings.app_env.lower() in {"prod", "production"}


def _paper_only_findings(settings: Settings) -> tuple[str, ...]:
    findings: list[str] = []
    if not settings.paper_trading_only:
        findings.append("PAPER_TRADING_ONLY must be true before Railway startup")
    if settings.live_trading_enabled:
        findings.append(
            "LIVE_TRADING_ENABLED must remain false until live-readiness gates exist"
        )
    if settings.max_open_hypotheses != 1:
        findings.append("MAX_OPEN_HYPOTHESES must be 1 for V1 runtime")
    return tuple(findings)


def _missing_required_env(
    service: ServiceName,
    settings: Settings,
    env: Mapping[str, str],
    *,
    strict: bool,
) -> tuple[str, ...]:
    required = list(_required_env_names(service, settings))
    if strict:
        required.extend(("PAPER_TRADING_ONLY", "MAX_OPEN_HYPOTHESES"))
    missing = tuple(
        name
        for name in required
        if not _required_value(name, env, settings, strict=strict)
    )
    return tuple(f"{name} is required for {service.value}" for name in missing)


def _required_env_names(service: ServiceName, settings: Settings) -> tuple[str, ...]:
    if service == ServiceName.API:
        return (
            ("SUPABASE_DB_URL",)
            if settings.source_persistence_backend == "postgres"
            else ()
        )
    if service == ServiceName.WATCHER:
        return (
            ("SUPABASE_DB_URL",)
            if settings.source_persistence_backend == "postgres"
            else ()
        )
    if service == ServiceName.AI_WORKER:
        return ("SUPABASE_DB_URL", "OPENAI_API_KEY")
    if service == ServiceName.PAPER_WORKER:
        return ("SUPABASE_DB_URL",)
    return ()


def _service_mode_findings(service: ServiceName, settings: Settings) -> tuple[str, ...]:
    if (
        service == ServiceName.AI_WORKER
        and settings.source_persistence_backend != "postgres"
    ):
        return ("worker-service requires SOURCE_PERSISTENCE_BACKEND=postgres",)
    if (
        service == ServiceName.PAPER_WORKER
        and settings.source_persistence_backend != "postgres"
    ):
        return ("paper-trading-worker requires SOURCE_PERSISTENCE_BACKEND=postgres",)
    return ()


def _env_value(name: str, env: Mapping[str, str], settings: Settings) -> str:
    if name in env:
        return env[name].strip()
    return str(getattr(settings, name.lower(), "") or "").strip()


def _required_value(
    name: str,
    env: Mapping[str, str],
    settings: Settings,
    *,
    strict: bool,
) -> str:
    if strict and name in {"PAPER_TRADING_ONLY", "MAX_OPEN_HYPOTHESES"}:
        return env.get(name, "").strip()
    return _env_value(name, env, settings)


def _strict_only_findings(findings: list[str]) -> tuple[str, ...]:
    return tuple(
        finding
        for finding in findings
        if finding.startswith("LIVE_TRADING_ENABLED")
        or finding.startswith("PAPER_TRADING_ONLY")
    )


def _component(name: str, ok: bool, detail: str) -> dict[str, object]:
    return {
        "name": name,
        "status": "healthy" if ok else "degraded",
        "detail": "configured" if ok else detail,
    }
