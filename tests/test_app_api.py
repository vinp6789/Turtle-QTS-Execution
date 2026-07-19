"""Tests for the FastAPI interface via TestClient (in-process, no socket).

Worker and startup-cycle are disabled so the tests drive cycles explicitly
and remain deterministic. Uses the real paper engine (MockExchangeAdapter).
"""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.api import create_app
from app.runtime import AppSettings, AppState, CycleWorker

_SIGNING_ENV = {"TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1": "signing-secret-material"}


def _env(store_path, **overrides):
    e = dict(_SIGNING_ENV)
    e["ENGINE_CONFIG_PATH"] = "deploy/engine.paper.toml"
    e["ENGINE_STORE_PATH"] = str(store_path)
    e.update(overrides)
    return e


class _ApiCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        store = Path(self._tmp.name) / "events.log"
        self.env = _env(store, **getattr(self, "extra_env", {}))
        settings = AppSettings.from_env(self.env)
        self.state = AppState.create(settings, env=self.env)
        app = create_app(self.state, CycleWorker(self.state),
                         start_worker=False, run_startup_cycle=False)
        self.client = TestClient(app)
        self.client.__enter__()  # trigger lifespan
        self.addCleanup(lambda: self.client.__exit__(None, None, None))


class TestReadOnlyEndpoints(_ApiCase):
    def test_health(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("current_state", body)
        self.assertFalse(body["emergency_stopped"])

    def test_status(self):
        r = self.client.get("/status")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("portfolio", body)
        self.assertIn("equity", body["portfolio"])

    def test_portfolio(self):
        r = self.client.get("/portfolio")
        self.assertEqual(r.status_code, 200)
        self.assertIn("available_cash", r.json())

    def test_reports(self):
        r = self.client.get("/reports")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        for key in ("portfolio", "execution", "cycle", "risk", "reconciliation"):
            self.assertIn(key, body)

    def test_metrics_prometheus_format(self):
        r = self.client.get("/metrics")
        self.assertEqual(r.status_code, 200)
        self.assertIn("turtle_engine_up", r.text)
        self.assertIn("# TYPE turtle_cycles_run_total counter", r.text)

    def test_openapi_available(self):
        r = self.client.get("/openapi.json")
        self.assertEqual(r.status_code, 200)
        self.assertIn("/health", r.json()["paths"])


class TestControlEndpointsUnprotected(_ApiCase):
    def test_run_cycle(self):
        r = self.client.post("/cycle/run")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["cycles_run"], 1)

    def test_emergency_stop(self):
        r = self.client.post("/control/emergency-stop")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["emergency_stopped"])
        # Reflected in health afterward.
        self.assertTrue(self.client.get("/health").json()["emergency_stopped"])


class TestDashboardServing(_ApiCase):
    def test_index_served_at_root(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Turtle Engine", r.text)

    def test_static_asset_served(self):
        r = self.client.get("/assets/app.js")
        self.assertEqual(r.status_code, 200)
        self.assertIn("refresh", r.text)


class TestControlEndpointsProtected(_ApiCase):
    extra_env = {"API_KEY": "secret-key-123"}

    def test_missing_key_rejected(self):
        self.assertEqual(self.client.post("/cycle/run").status_code, 401)

    def test_wrong_key_rejected(self):
        r = self.client.post("/cycle/run", headers={"X-API-Key": "wrong"})
        self.assertEqual(r.status_code, 401)

    def test_correct_key_accepted(self):
        r = self.client.post("/cycle/run", headers={"X-API-Key": "secret-key-123"})
        self.assertEqual(r.status_code, 200)

    def test_bearer_token_accepted(self):
        r = self.client.post("/cycle/run", headers={"Authorization": "Bearer secret-key-123"})
        self.assertEqual(r.status_code, 200)

    def test_readonly_still_open(self):
        self.assertEqual(self.client.get("/health").status_code, 200)


if __name__ == "__main__":
    unittest.main()
