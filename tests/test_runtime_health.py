from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from qualstocks.runtime_health import (
    ServiceName,
    service_health_payload,
    validate_service_startup,
)
from qualstocks.settings import load_settings


def settings_from_env(env: dict[str, str]):
    with patch.dict(os.environ, env, clear=True):
        return load_settings()


class RuntimeHealthTest(unittest.TestCase):
    def test_dev_missing_worker_secrets_are_reported_as_warnings(self):
        settings = settings_from_env({"SOURCE_PERSISTENCE_BACKEND": "memory"})

        validation = validate_service_startup(settings, ServiceName.AI_WORKER)

        self.assertTrue(validation.ok)
        self.assertFalse(validation.strict)
        self.assertEqual(validation.errors, ())
        self.assertIn(
            "worker-service requires SOURCE_PERSISTENCE_BACKEND=postgres",
            validation.warnings,
        )

    def test_production_worker_requires_db_openai_and_explicit_paper_flags(self):
        settings = settings_from_env(
            {
                "APP_ENV": "prod",
                "SOURCE_PERSISTENCE_BACKEND": "postgres",
                "PAPER_TRADING_ONLY": "true",
                "MAX_OPEN_HYPOTHESES": "1",
            }
        )

        validation = validate_service_startup(settings, ServiceName.AI_WORKER)

        self.assertFalse(validation.ok)
        self.assertTrue(validation.strict)
        self.assertIn(
            "SUPABASE_DB_URL is required for worker-service",
            validation.errors,
        )
        self.assertIn(
            "OPENAI_API_KEY is required for worker-service",
            validation.errors,
        )

    def test_production_denies_live_trading_startup(self):
        settings = settings_from_env(
            {
                "APP_ENV": "prod",
                "PAPER_TRADING_ONLY": "false",
                "LIVE_TRADING_ENABLED": "true",
                "MAX_OPEN_HYPOTHESES": "1",
            }
        )

        validation = validate_service_startup(settings, ServiceName.API)

        self.assertFalse(validation.ok)
        self.assertIn(
            "PAPER_TRADING_ONLY must be true before Railway startup",
            validation.errors,
        )
        self.assertIn(
            "LIVE_TRADING_ENABLED must remain false until live-readiness gates exist",
            validation.errors,
        )

    def test_production_requires_explicit_single_hypothesis_flag(self):
        settings = settings_from_env(
            {
                "APP_ENV": "prod",
                "PAPER_TRADING_ONLY": "true",
            }
        )

        validation = validate_service_startup(settings, ServiceName.API)

        self.assertFalse(validation.ok)
        self.assertIn(
            "MAX_OPEN_HYPOTHESES is required for api-service",
            validation.errors,
        )

    def test_service_health_payload_reports_configured_components(self):
        settings = settings_from_env(
            {
                "SOURCE_PERSISTENCE_BACKEND": "postgres",
                "SOURCE_NORWEGIAN_CONFIRMATION_RSS_ENABLED": "true",
                "SUPABASE_DB_URL": "postgresql://example",
                "OPENAI_API_KEY": "test",
            }
        )

        payload = service_health_payload(settings)

        self.assertEqual(payload["api"]["status"], "healthy")
        self.assertEqual(payload["watcher"]["status"], "healthy")
        self.assertEqual(payload["ai_worker"]["status"], "healthy")
        self.assertEqual(payload["quote_provider"]["status"], "healthy")
        self.assertEqual(payload["paper_trading_worker"]["status"], "healthy")


if __name__ == "__main__":
    unittest.main()
