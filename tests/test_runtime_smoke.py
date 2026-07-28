from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from qualstocks.runtime_smoke import run_runtime_smoke_checks
from qualstocks.settings import load_settings


def settings_from_env(env: dict[str, str]):
    with patch.dict(os.environ, env, clear=True):
        return load_settings()


class RuntimeSmokeTest(unittest.TestCase):
    def test_production_paper_runtime_smoke_passes_when_services_are_configured(self):
        env = {
            "APP_ENV": "prod",
            "PAPER_TRADING_ONLY": "true",
            "LIVE_TRADING_ENABLED": "false",
            "MAX_OPEN_HYPOTHESES": "1",
            "SOURCE_PERSISTENCE_BACKEND": "postgres",
            "SOURCE_OFFICIAL_US_RSS_ENABLED": "true",
            "SUPABASE_DB_URL": "postgresql://example",
            "OPENAI_API_KEY": "test",
            "QUOTE_SOURCE": "yahoo",
            "QUOTE_INSTRUMENT": "EQNR.OL",
        }
        settings = settings_from_env(env)

        report = run_runtime_smoke_checks(settings, environ=env)

        self.assertTrue(report.ok)
        self.assertTrue(all(check.ok for check in report.checks))
        self.assertEqual(report.services["watcher"]["status"], "healthy")
        self.assertEqual(report.services["quote_provider"]["status"], "healthy")

    def test_smoke_fails_when_live_trading_gate_is_open(self):
        env = {
            "APP_ENV": "prod",
            "PAPER_TRADING_ONLY": "false",
            "LIVE_TRADING_ENABLED": "true",
            "MAX_OPEN_HYPOTHESES": "1",
            "SOURCE_PERSISTENCE_BACKEND": "postgres",
            "SOURCE_OFFICIAL_US_RSS_ENABLED": "true",
            "SUPABASE_DB_URL": "postgresql://example",
            "OPENAI_API_KEY": "test",
        }
        settings = settings_from_env(env)

        report = run_runtime_smoke_checks(settings, environ=env)

        self.assertFalse(report.ok)
        live_gate = next(
            check for check in report.checks if check.name == "live_gate:paper_only"
        )
        self.assertFalse(live_gate.ok)
        self.assertIn("LIVE_TRADING_ENABLED=false", live_gate.detail)
        startup_api = next(
            check for check in report.checks if check.name == "startup:api-service"
        )
        self.assertFalse(startup_api.ok)

    def test_smoke_fails_when_no_watcher_sources_are_enabled(self):
        env = {
            "APP_ENV": "prod",
            "PAPER_TRADING_ONLY": "true",
            "LIVE_TRADING_ENABLED": "false",
            "MAX_OPEN_HYPOTHESES": "1",
            "SOURCE_PERSISTENCE_BACKEND": "postgres",
            "SUPABASE_DB_URL": "postgresql://example",
            "OPENAI_API_KEY": "test",
        }
        settings = settings_from_env(env)

        report = run_runtime_smoke_checks(settings, environ=env)

        self.assertFalse(report.ok)
        watcher = next(check for check in report.checks if check.name == "component:watcher")
        self.assertFalse(watcher.ok)
        self.assertEqual(watcher.detail, "no adapters enabled")


if __name__ == "__main__":
    unittest.main()
