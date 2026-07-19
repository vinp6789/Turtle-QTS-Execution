"""Tests for the pure Telegram command router and the guarded notifier.

The polling bot (app.telegram.bot) needs a live token/network and is not
exercised here; its logic is the command router + notifier, both tested.
"""

import tempfile
import unittest
from pathlib import Path

from app.runtime import AppSettings, AppState
from app.telegram import HELP_TEXT, TelegramNotifier, handle_command

_SIGNING_ENV = {"TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1": "signing-secret-material"}


def _env(store_path, **overrides):
    e = dict(_SIGNING_ENV)
    e["ENGINE_CONFIG_PATH"] = "deploy/engine.paper.toml"
    e["ENGINE_STORE_PATH"] = str(store_path)
    e.update(overrides)
    return e


class _StateCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        env = _env(Path(self._tmp.name) / "events.log")
        self.settings = AppSettings.from_env(env)
        self.state = AppState.create(self.settings, env=env)
        self.addCleanup(self.state.shutdown)


class TestCommandRouter(_StateCase):
    def test_help_for_blank_and_unknown(self):
        self.assertEqual(handle_command("", self.state), HELP_TEXT)
        self.assertIn("Unknown command", handle_command("/nope", self.state))

    def test_health_and_status_and_portfolio(self):
        self.assertIn("Health:", handle_command("/health", self.state))
        self.assertIn("Portfolio", handle_command("/status", self.state))
        self.assertIn("Equity", handle_command("/portfolio", self.state))

    def test_cycle_runs_a_real_cycle(self):
        self.assertEqual(self.state.cycles_run, 0)
        reply = handle_command("/cycle", self.state)
        self.assertIn("Cycle complete", reply)
        self.assertEqual(self.state.cycles_run, 1)

    def test_command_with_botname_suffix(self):
        self.assertIn("Health:", handle_command("/health@TurtleBot", self.state))

    def test_stop_requires_authorization(self):
        reply = handle_command("/stop", self.state, authorized=False)
        self.assertIn("Not authorized", reply)
        self.assertFalse(self.state.emergency_stopped)

    def test_stop_when_authorized_executes(self):
        reply = handle_command("/stop", self.state, authorized=True)
        self.assertIn("EMERGENCY STOP", reply)
        self.assertTrue(self.state.emergency_stopped)


class TestNotifier(_StateCase):
    def test_disabled_is_noop(self):
        notifier = TelegramNotifier(self.settings)  # telegram disabled by default
        self.assertFalse(notifier.enabled)
        self.assertFalse(notifier.send("hello"))

    def test_enabled_posts_via_session(self):
        sent = {}

        class _Resp:
            status_code = 200

        class _Session:
            def post(self, url, json, timeout):
                sent["url"] = url
                sent["json"] = json
                return _Resp()

        env = _env(Path(self._tmp.name) / "events2.log",
                   TELEGRAM_ENABLED="true", TELEGRAM_BOT_TOKEN="tok", TELEGRAM_CHAT_ID="42")
        settings = AppSettings.from_env(env)
        notifier = TelegramNotifier(settings, session=_Session())
        self.assertTrue(notifier.enabled)
        self.assertTrue(notifier.send("hello"))
        self.assertEqual(sent["json"]["chat_id"], "42")
        self.assertEqual(sent["json"]["text"], "hello")

    def test_enabled_swallows_network_error(self):
        class _Session:
            def post(self, *a, **k):
                raise RuntimeError("network down")

        env = _env(Path(self._tmp.name) / "events3.log",
                   TELEGRAM_ENABLED="true", TELEGRAM_BOT_TOKEN="tok", TELEGRAM_CHAT_ID="42")
        settings = AppSettings.from_env(env)
        notifier = TelegramNotifier(settings, session=_Session())
        self.assertFalse(notifier.send("hello"))  # no raise


if __name__ == "__main__":
    unittest.main()
