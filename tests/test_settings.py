import os
import unittest
from unittest.mock import patch

from qualstocks.settings import load_settings


class SettingsTest(unittest.TestCase):
    def test_defaults_are_paper_trading_only_and_single_hypothesis(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = load_settings()

        self.assertTrue(settings.paper_trading_only)
        self.assertEqual(settings.max_open_hypotheses, 1)
        self.assertEqual(settings.exit_windows_minutes, (30, 40, 50))

    def test_runtime_secret_status_is_false_without_required_values(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = load_settings()

        self.assertFalse(settings.has_required_runtime_secrets)

    def test_runtime_secret_status_is_true_with_required_values(self):
        env = {
            "OPENAI_API_KEY": "test",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_ANON_KEY": "anon",
            "SUPABASE_SERVICE_ROLE_KEY": "service",
            "SUPABASE_DB_URL": "postgresql://postgres:password@example/postgres",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = load_settings()

        self.assertTrue(settings.has_required_runtime_secrets)


if __name__ == "__main__":
    unittest.main()

