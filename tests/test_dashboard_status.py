from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from qualstocks.dashboard import build_dashboard_status
from qualstocks.settings import Settings


class DashboardStatusTest(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(
            app_name="qualitativeguesses",
            app_env="test",
            paper_trading_only=True,
            max_open_hypotheses=1,
            tranche_one_aum_pct=50,
            tranche_two_aum_pct=50,
            exit_windows_minutes=(30, 40, 50),
            live_trading_enabled=False,
            risk_max_single_name_exposure_pct=100,
            risk_max_event_exposure_pct=100,
            risk_max_daily_loss_pct=5,
            risk_live_max_order_aum_pct=5,
            openai_api_key="test",
            openai_filter_model="gpt-5-nano",
            openai_analysis_model="gpt-5-mini",
            openai_escalation_model="gpt-5.1",
            openai_embedding_model="text-embedding-3-small",
            supabase_url="https://example.supabase.co",
            supabase_anon_key="anon",
            supabase_service_role_key="service",
            supabase_db_url="postgresql://example",
            railway_token="",
            railway_api_token="",
            kalshi_env="demo",
            kalshi_api_key_id="",
            kalshi_private_key_pem="",
            quote_source="yahoo",
            quote_instrument="EQNR.OL",
            quote_yahoo_symbol="EQNR.OL",
            quote_stale_after_seconds=60,
            quote_timeout_seconds=10,
            source_official_us_rss_enabled=True,
            source_official_iran_rss_enabled=True,
            source_norwegian_confirmation_rss_enabled=False,
            source_lseg_reuters_enabled=False,
            source_ap_media_api_enabled=False,
            source_fixture_mode_enabled=False,
            source_persistence_backend="postgres",
            watcher_run_once=False,
            watcher_interval_seconds=30,
            watcher_backoff_initial_seconds=5,
            watcher_backoff_max_seconds=300,
        )
        self.now = datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc)

    def test_idle_status_has_no_position(self):
        status = build_dashboard_status(self.settings, now=self.now)

        self.assertEqual(status["system_state"], "listening")
        self.assertEqual(status["mode"], "paper")
        self.assertIsNone(status["active_hypothesis"])
        self.assertIsNone(status["paper_position"])
        self.assertEqual(status["queue_status"], {"queued": 0, "running": 0, "failed": 0})
        self.assertEqual(status["event_timeline"], [])

    def test_active_hypothesis_sets_operator_state(self):
        status = build_dashboard_status(
            self.settings,
            read_model={
                "active_hypothesis": {
                    "id": "hyp-1",
                    "state": "active",
                    "created_at": self.now,
                    "thesis": "Escalation raises oil supply risk.",
                    "direction": "bullish_equinor",
                    "confidence": Decimal("0.82"),
                }
            },
            now=self.now,
        )

        self.assertEqual(status["system_state"], "waiting_for_norwegian_confirmation")
        self.assertEqual(status["active_hypothesis"]["confidence_label"], "high")
        self.assertEqual(status["active_hypothesis"]["created_at"], "2026-07-28T10:00:00Z")

    def test_open_position_includes_live_mark_to_market_pnl(self):
        status = build_dashboard_status(
            self.settings,
            read_model=self._position_model("fresh"),
            now=self.now,
        )
        position = status["paper_position"]

        self.assertIsNotNone(position)
        assert position is not None
        self.assertEqual(position["instrument"], "EQNR.OL")
        self.assertEqual(position["last_price"], 330.0)
        self.assertEqual(position["market_value"], 55000.0)
        self.assertEqual(position["unrealized_pnl"], 5000.0)
        self.assertEqual(position["unrealized_pnl_pct"], 10.0)
        self.assertEqual(position["total_pnl"], 4995.0)
        self.assertEqual(position["quote_freshness"], "fresh")

    def test_stale_quote_is_visible_in_position_payload(self):
        status = build_dashboard_status(
            self.settings,
            read_model=self._position_model("stale"),
            now=self.now,
        )

        self.assertEqual(status["paper_position"]["quote_freshness"], "stale")

    def test_timeline_orders_mixed_events_newest_first(self):
        status = build_dashboard_status(
            self.settings,
            read_model={
                "latest_events": [
                    {
                        "id": "event-1",
                        "source": "CENTCOM RSS",
                        "title": "Escalation report",
                        "first_seen_at": self.now - timedelta(minutes=5),
                    }
                ],
                "risk_decisions": [
                    {
                        "id": "risk-1",
                        "status": "approved",
                        "reason": "Paper order approved.",
                        "created_at": self.now - timedelta(minutes=3),
                    }
                ],
                "audit_timeline": [
                    {
                        "action": "paper_fill_created",
                        "summary": "Paper fill created.",
                        "created_at": self.now - timedelta(minutes=1),
                    }
                ],
            },
            now=self.now,
        )

        self.assertEqual(
            [item["type"] for item in status["event_timeline"]],
            ["paper_fill_created", "risk_decision", "source_event"],
        )
        self.assertEqual(status["event_timeline"][0]["title"], "Paper fill created.")

    def test_timeline_includes_duplicate_and_rejected_events(self):
        status = build_dashboard_status(
            self.settings,
            read_model={
                "ingestion_results": [
                    {
                        "status": "duplicate",
                        "source": "Reuters / LSEG News Service",
                        "title": "Duplicate wire alert",
                        "timestamp": self.now - timedelta(seconds=30),
                        "idempotency_key": "reuters:1",
                    },
                    {
                        "status": "unsupported",
                        "source": "AP Media API",
                        "rejection_reason": "instrument is not supported",
                        "timestamp": self.now - timedelta(seconds=20),
                        "idempotency_key": "ap:1",
                    },
                ]
            },
            now=self.now,
        )

        self.assertEqual(status["event_timeline"][0]["type"], "rejected_event")
        self.assertEqual(status["event_timeline"][0]["severity"], "error")
        self.assertEqual(status["event_timeline"][0]["entity_id"], "ap:1")
        self.assertEqual(status["event_timeline"][1]["type"], "duplicate_event")
        self.assertEqual(status["event_timeline"][1]["severity"], "info")

    def test_active_hypothesis_adds_timeline_item(self):
        status = build_dashboard_status(
            self.settings,
            read_model={
                "active_hypothesis": {
                    "id": "hyp-1",
                    "state": "active",
                    "created_at": self.now,
                    "thesis": "Escalation raises oil supply risk.",
                    "direction": "bullish_equinor",
                    "confidence": Decimal("0.82"),
                }
            },
            now=self.now,
        )

        self.assertEqual(status["event_timeline"][0]["type"], "hypothesis_active")
        self.assertEqual(status["event_timeline"][0]["source"], "strategy")
        self.assertEqual(status["event_timeline"][0]["entity_id"], "hyp-1")

    def test_zero_quantity_position_is_treated_as_no_open_position(self):
        model = self._position_model("fresh")
        model["position"]["quantity"] = Decimal("0")

        status = build_dashboard_status(self.settings, read_model=model, now=self.now)

        self.assertIsNone(status["paper_position"])

    def test_source_health_includes_lag_seconds(self):
        status = build_dashboard_status(
            self.settings,
            read_model={
                "source_health": [
                    {
                        "source": "CENTCOM RSS",
                        "source_class": "official_actor",
                        "source_id": "centcom_rss",
                        "status": "online",
                        "last_event_at": self.now - timedelta(seconds=45),
                        "last_checked_at": self.now,
                        "last_error": None,
                    }
                ]
            },
            now=self.now,
        )

        self.assertEqual(status["source_health"][0]["lag_seconds"], 45)
        self.assertEqual(status["source_health"][0]["source_id"], "centcom_rss")

    def _position_model(self, quote_freshness: str) -> dict[str, object]:
        return {
            "position": {
                "instrument": "EQNR.OL",
                "quantity": Decimal("166.666667"),
                "average_entry_price": Decimal("300"),
                "realized_pnl": Decimal("0"),
                "unrealized_pnl": Decimal("0"),
            },
            "valuation": {
                "instrument": "EQNR.OL",
                "last_price": Decimal("330"),
                "market_value": Decimal("55000"),
                "realized_pnl": Decimal("0"),
                "unrealized_pnl": Decimal("5000"),
                "unrealized_pnl_pct": Decimal("10"),
                "total_pnl": Decimal("4995"),
                "total_pnl_pct": Decimal("4.995"),
                "quote_freshness": quote_freshness,
                "quote_source": "yahoo:EQNR.OL",
                "quote_observed_at": self.now - timedelta(seconds=30),
            },
        }


if __name__ == "__main__":
    unittest.main()
