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
        self.assertFalse(settings.live_trading_enabled)
        self.assertEqual(settings.risk_max_single_name_exposure_pct, 100)
        self.assertEqual(settings.risk_max_event_exposure_pct, 100)
        self.assertEqual(settings.risk_max_daily_loss_pct, 5)
        self.assertEqual(settings.risk_live_max_order_aum_pct, 5)
        self.assertFalse(settings.source_official_us_rss_enabled)
        self.assertFalse(settings.source_official_iran_rss_enabled)
        self.assertFalse(settings.source_norwegian_confirmation_rss_enabled)
        self.assertFalse(settings.source_fixture_mode_enabled)
        self.assertEqual(settings.source_persistence_backend, "memory")
        self.assertEqual(settings.kalshi_env, "demo")
        self.assertEqual(settings.kalshi_api_key_id, "")
        self.assertEqual(settings.kalshi_private_key_pem, "")
        self.assertEqual(settings.quote_source, "yahoo")
        self.assertEqual(settings.quote_instrument, "EQNR.OL")
        self.assertEqual(settings.quote_yahoo_symbol, "EQNR.OL")
        self.assertEqual(settings.quote_stale_after_seconds, 60)
        self.assertEqual(settings.quote_timeout_seconds, 10)
        self.assertFalse(settings.watcher_run_once)
        self.assertEqual(settings.watcher_interval_seconds, 30)

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

    def test_source_runtime_flags_are_loaded_from_environment(self):
        env = {
            "SOURCE_OFFICIAL_US_RSS_ENABLED": "true",
            "SOURCE_OFFICIAL_IRAN_RSS_ENABLED": "1",
            "SOURCE_NORWEGIAN_CONFIRMATION_RSS_ENABLED": "on",
            "SOURCE_FIXTURE_MODE_ENABLED": "yes",
            "SOURCE_PERSISTENCE_BACKEND": "postgres",
            "KALSHI_ENV": "production",
            "KALSHI_API_KEY_ID": "kalshi-key",
            "KALSHI_PRIVATE_KEY_PEM": "kalshi-private-key",
            "LIVE_TRADING_ENABLED": "true",
            "RISK_MAX_SINGLE_NAME_EXPOSURE_PCT": "80",
            "RISK_MAX_EVENT_EXPOSURE_PCT": "60",
            "RISK_MAX_DAILY_LOSS_PCT": "4",
            "RISK_LIVE_MAX_ORDER_AUM_PCT": "3",
            "QUOTE_SOURCE": "yahoo",
            "QUOTE_INSTRUMENT": "EQNR.OL",
            "QUOTE_YAHOO_SYMBOL": "EQNR.OL",
            "QUOTE_STALE_AFTER_SECONDS": "15",
            "QUOTE_TIMEOUT_SECONDS": "4",
            "WATCHER_RUN_ONCE": "on",
            "WATCHER_INTERVAL_SECONDS": "7",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = load_settings()

        self.assertTrue(settings.source_official_us_rss_enabled)
        self.assertTrue(settings.source_official_iran_rss_enabled)
        self.assertTrue(settings.source_norwegian_confirmation_rss_enabled)
        self.assertTrue(settings.source_fixture_mode_enabled)
        self.assertEqual(settings.source_persistence_backend, "postgres")
        self.assertEqual(settings.kalshi_env, "production")
        self.assertEqual(settings.kalshi_api_key_id, "kalshi-key")
        self.assertEqual(settings.kalshi_private_key_pem, "kalshi-private-key")
        self.assertTrue(settings.public_status["kalshi_configured"])
        self.assertTrue(settings.live_trading_enabled)
        self.assertEqual(settings.risk_max_single_name_exposure_pct, 80)
        self.assertEqual(settings.risk_max_event_exposure_pct, 60)
        self.assertEqual(settings.risk_max_daily_loss_pct, 4)
        self.assertEqual(settings.risk_live_max_order_aum_pct, 3)
        self.assertEqual(settings.quote_source, "yahoo")
        self.assertEqual(settings.quote_instrument, "EQNR.OL")
        self.assertEqual(settings.quote_yahoo_symbol, "EQNR.OL")
        self.assertEqual(settings.quote_stale_after_seconds, 15)
        self.assertEqual(settings.quote_timeout_seconds, 4)
        self.assertEqual(settings.public_status["quote_source"], "yahoo")
        self.assertEqual(settings.public_status["quote_instrument"], "EQNR.OL")
        self.assertTrue(settings.watcher_run_once)
        self.assertEqual(settings.watcher_interval_seconds, 7)


if __name__ == "__main__":
    unittest.main()
