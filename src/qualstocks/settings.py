from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    return int(raw)


def _env_csv_int(name: str, default: tuple[int, ...]) -> tuple[int, ...]:
    raw = _env(name)
    if not raw:
        return default
    return tuple(int(part.strip()) for part in raw.split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    paper_trading_only: bool
    max_open_hypotheses: int
    tranche_one_aum_pct: int
    tranche_two_aum_pct: int
    exit_windows_minutes: tuple[int, ...]
    openai_api_key: str
    openai_filter_model: str
    openai_analysis_model: str
    openai_escalation_model: str
    openai_embedding_model: str
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    supabase_db_url: str
    railway_token: str
    railway_api_token: str
    source_official_us_rss_enabled: bool
    source_official_iran_rss_enabled: bool
    source_fixture_mode_enabled: bool
    watcher_run_once: bool
    watcher_interval_seconds: int

    @property
    def has_required_runtime_secrets(self) -> bool:
        required = (
            self.openai_api_key,
            self.supabase_url,
            self.supabase_anon_key,
            self.supabase_service_role_key,
            self.supabase_db_url,
        )
        return all(required)

    @property
    def public_status(self) -> dict[str, object]:
        return {
            "app_name": self.app_name,
            "app_env": self.app_env,
            "paper_trading_only": self.paper_trading_only,
            "max_open_hypotheses": self.max_open_hypotheses,
            "exit_windows_minutes": list(self.exit_windows_minutes),
            "runtime_secrets_present": self.has_required_runtime_secrets,
            "source_official_us_rss_enabled": self.source_official_us_rss_enabled,
            "source_official_iran_rss_enabled": self.source_official_iran_rss_enabled,
            "source_fixture_mode_enabled": self.source_fixture_mode_enabled,
        }


def load_settings() -> Settings:
    return Settings(
        app_name=_env("APP_NAME", "qualitativeguesses"),
        app_env=_env("APP_ENV", "dev"),
        paper_trading_only=_env_bool("PAPER_TRADING_ONLY", True),
        max_open_hypotheses=_env_int("MAX_OPEN_HYPOTHESES", 1),
        tranche_one_aum_pct=_env_int("TRANCHE_ONE_AUM_PCT", 50),
        tranche_two_aum_pct=_env_int("TRANCHE_TWO_AUM_PCT", 50),
        exit_windows_minutes=_env_csv_int("EXIT_WINDOWS_MINUTES", (30, 40, 50)),
        openai_api_key=_env("OPENAI_API_KEY"),
        openai_filter_model=_env("OPENAI_FILTER_MODEL", "gpt-5-nano"),
        openai_analysis_model=_env("OPENAI_ANALYSIS_MODEL", "gpt-5-mini"),
        openai_escalation_model=_env("OPENAI_ESCALATION_MODEL", "gpt-5.1"),
        openai_embedding_model=_env("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        supabase_url=_env("SUPABASE_URL"),
        supabase_anon_key=_env("SUPABASE_ANON_KEY"),
        supabase_service_role_key=_env("SUPABASE_SERVICE_ROLE_KEY"),
        supabase_db_url=_env("SUPABASE_DB_URL"),
        railway_token=_env("RAILWAY_TOKEN"),
        railway_api_token=_env("RAILWAY_API_TOKEN"),
        source_official_us_rss_enabled=_env_bool("SOURCE_OFFICIAL_US_RSS_ENABLED", False),
        source_official_iran_rss_enabled=_env_bool("SOURCE_OFFICIAL_IRAN_RSS_ENABLED", False),
        source_fixture_mode_enabled=_env_bool("SOURCE_FIXTURE_MODE_ENABLED", False),
        watcher_run_once=_env_bool("WATCHER_RUN_ONCE", False),
        watcher_interval_seconds=_env_int("WATCHER_INTERVAL_SECONDS", 30),
    )
