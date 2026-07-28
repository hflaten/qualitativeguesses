import unittest

try:
    from qualstocks.main import api_timeline, dashboard
except ModuleNotFoundError as exc:
    dashboard = None
    api_timeline = None
    FASTAPI_IMPORT_ERROR = exc
else:
    FASTAPI_IMPORT_ERROR = None


class DashboardHtmlTest(unittest.TestCase):
    @unittest.skipIf(
        dashboard is None,
        f"dashboard dependencies unavailable: {FASTAPI_IMPORT_ERROR}",
    )
    def test_dashboard_fetches_status_api_and_renders_position_fields(self):
        assert dashboard is not None
        html = dashboard()

        self.assertIn('fetch("/api/status")', html)
        self.assertIn("Total P/L", html)
        self.assertIn("Unrealized P/L", html)
        self.assertIn("quote_freshness", html)
        self.assertIn("event_timeline", html)
        self.assertIn("Timeline", html)
        self.assertIn("setInterval(refresh, 3000)", html)

    @unittest.skipIf(
        api_timeline is None,
        f"dashboard dependencies unavailable: {FASTAPI_IMPORT_ERROR}",
    )
    def test_timeline_api_returns_operator_feed_and_position_state(self):
        assert api_timeline is not None

        payload = api_timeline()

        self.assertIn("system_state", payload)
        self.assertIn("paper_position", payload)
        self.assertIn("event_timeline", payload)


if __name__ == "__main__":
    unittest.main()
