import unittest

try:
    from qualstocks.main import dashboard
except ModuleNotFoundError as exc:
    dashboard = None
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
        self.assertIn("setInterval(refresh, 3000)", html)


if __name__ == "__main__":
    unittest.main()
