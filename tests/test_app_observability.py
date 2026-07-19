"""Tests for app.observability: JSON logging + Prometheus metrics rendering."""

import json
import logging
import tempfile
import unittest
from io import StringIO
from pathlib import Path

from app.observability import configure_logging, log_event, render_metrics
from app.observability.logging import JsonFormatter
from app.runtime import AppSettings, AppState

_SIGNING_ENV = {"TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1": "signing-secret-material"}


def _env(store_path):
    return {
        **_SIGNING_ENV,
        "ENGINE_CONFIG_PATH": "deploy/engine.paper.toml",
        "ENGINE_STORE_PATH": str(store_path),
    }


class TestJsonLogging(unittest.TestCase):
    def test_json_formatter_emits_valid_json_with_fields(self):
        formatter = JsonFormatter()
        record = logging.LogRecord("t", logging.INFO, __file__, 1, "hello", None, None)
        record.extra_fields = {"cycles_run": 3}
        parsed = json.loads(formatter.format(record))
        self.assertEqual(parsed["message"], "hello")
        self.assertEqual(parsed["level"], "INFO")
        self.assertEqual(parsed["cycles_run"], 3)

    def test_configure_logging_attaches_single_handler(self):
        configure_logging("DEBUG", "json")
        configure_logging("INFO", "text")  # re-invoke must not stack handlers
        self.assertEqual(len(logging.getLogger().handlers), 1)


class TestMetrics(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        env = _env(Path(self._tmp.name) / "events.log")
        self.state = AppState.create(AppSettings.from_env(env), env=env)
        self.addCleanup(self.state.shutdown)

    def test_render_before_start(self):
        text = render_metrics(self.state)
        self.assertIn("turtle_engine_up 0", text)
        self.assertIn("# TYPE turtle_cycles_run_total counter", text)

    def test_render_after_cycle(self):
        self.state.run_one_cycle()
        text = render_metrics(self.state)
        self.assertIn("turtle_engine_up 1", text)
        self.assertIn("turtle_cycles_run_total 1", text)
        self.assertIn("turtle_equity", text)
        # Every metric line is well-formed exposition (name value).
        for line in text.splitlines():
            if line and not line.startswith("#"):
                self.assertEqual(len(line.split(" ")), 2, line)


if __name__ == "__main__":
    unittest.main()
