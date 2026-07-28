from __future__ import annotations

import importlib
import json
import unittest
from pathlib import Path


TEMPLATE_PATH = Path("railway/service-templates.json")


class RailwayTemplateTest(unittest.TestCase):
    def test_service_templates_define_expected_services_and_commands(self):
        template = _template()
        services = {service["name"]: service for service in template["services"]}

        self.assertEqual(
            set(services),
            {"api-service", "watcher-service", "worker-service"},
        )
        self.assertEqual(
            services["api-service"]["start_command"],
            "uvicorn qualstocks.main:app --host 0.0.0.0 --port $PORT",
        )
        self.assertEqual(
            services["watcher-service"]["start_command"],
            "python -m qualstocks.watcher",
        )
        self.assertEqual(
            services["worker-service"]["start_command"],
            "python -m qualstocks.worker",
        )

    def test_service_entrypoint_modules_are_importable(self):
        try:
            main = importlib.import_module("qualstocks.main")
        except ModuleNotFoundError as exc:
            self.skipTest(f"api dependencies unavailable: {exc}")
        watcher = importlib.import_module("qualstocks.watcher")
        worker = importlib.import_module("qualstocks.worker")

        self.assertTrue(hasattr(main, "app"))
        self.assertTrue(callable(watcher.main))
        self.assertTrue(callable(worker.main))

    def test_template_contains_variable_names_not_secret_values(self):
        template = _template()
        serialized = json.dumps(template)

        self.assertIn("SUPABASE_DB_URL", serialized)
        self.assertIn("OPENAI_API_KEY", serialized)
        self.assertNotIn("sk-", serialized)
        self.assertNotIn("sb_secret_", serialized)
        self.assertNotIn("postgresql://", serialized)

    def test_every_service_has_paper_only_gate_variables(self):
        for service in _template()["services"]:
            variables = set(service["required_variables"])
            self.assertIn("PAPER_TRADING_ONLY", variables)
            self.assertIn("LIVE_TRADING_ENABLED", variables)
            self.assertIn("MAX_OPEN_HYPOTHESES", variables)


def _template() -> dict[str, object]:
    with TEMPLATE_PATH.open() as handle:
        return json.load(handle)


if __name__ == "__main__":
    unittest.main()
