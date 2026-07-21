"""Regression tests for H5: the Telegram bot is now instantiated and its
lifecycle tied to the FastAPI lifespan (started on startup, stopped on
shutdown), and misconfiguration fails clearly at settings load.

THE PREVIOUS FAILURE: TelegramBot was never instantiated anywhere in the
runtime -- the lifespan started only the cycle worker -- so commands and
notifications were dead despite the feature existing; and an enabled-but-
misconfigured Telegram silently self-disabled instead of failing clearly.

No live token/network: the bot's polling thread is prevented from doing
real HTTP by injecting a fake session, and start()/stop() are asserted via
is_running.
"""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.api import create_app
from app.runtime import AppSettings, AppState, CycleWorker

_SIGNING_ENV = {"TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1": "signing-secret-material"}


def _base_env(store_path, **overrides):
    e = {
        **_SIGNING_ENV,
        "ENGINE_CONFIG_PATH": "deploy/engine.paper.toml",
        "ENGINE_STORE_PATH": str(store_path),
    }
    e.update(overrides)
    return e


class _LifecycleCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = Path(self._tmp.name) / "events.log"


class TestSettingsFailClear(_LifecycleCase):
    def test_disabled_never_fails_even_with_no_token(self):
        settings = AppSettings.from_env(_base_env(self.store, TELEGRAM_ENABLED="false"))
        self.assertFalse(settings.telegram_enabled)

    def test_enabled_and_complete_boots(self):
        settings = AppSettings.from_env(_base_env(
            self.store, TELEGRAM_ENABLED="true", TELEGRAM_BOT_TOKEN="tok", TELEGRAM_CHAT_ID="42"))
        self.assertTrue(settings.telegram_enabled)

    def test_enabled_missing_token_fails_clearly(self):
        with self.assertRaises(ValueError) as ctx:
            AppSettings.from_env(_base_env(
                self.store, TELEGRAM_ENABLED="true", TELEGRAM_CHAT_ID="42"))
        self.assertIn("TELEGRAM_BOT_TOKEN", str(ctx.exception))

    def test_enabled_missing_chat_id_fails_clearly(self):
        with self.assertRaises(ValueError) as ctx:
            AppSettings.from_env(_base_env(
                self.store, TELEGRAM_ENABLED="true", TELEGRAM_BOT_TOKEN="tok"))
        self.assertIn("TELEGRAM_CHAT_ID", str(ctx.exception))

    def test_enabled_blank_token_is_treated_as_missing(self):
        with self.assertRaises(ValueError):
            AppSettings.from_env(_base_env(
                self.store, TELEGRAM_ENABLED="true", TELEGRAM_BOT_TOKEN="   ", TELEGRAM_CHAT_ID="42"))

    def test_enabled_missing_both_names_both_reported(self):
        with self.assertRaises(ValueError) as ctx:
            AppSettings.from_env(_base_env(self.store, TELEGRAM_ENABLED="true"))
        msg = str(ctx.exception)
        self.assertIn("TELEGRAM_BOT_TOKEN", msg)
        self.assertIn("TELEGRAM_CHAT_ID", msg)


class TestBotLifecycleTiedToLifespan(_LifecycleCase):
    def _app(self, **env_overrides):
        env = _base_env(self.store, **env_overrides)
        state = AppState.create(AppSettings.from_env(env), env=env)
        # start_worker/run_startup_cycle off for determinism; the Telegram
        # bot lifecycle is independent of both.
        return create_app(state, CycleWorker(state),
                          start_worker=False, run_startup_cycle=False)

    def test_disabled_constructs_no_bot(self):
        app = self._app(TELEGRAM_ENABLED="false")
        with TestClient(app):
            self.assertIsNone(app.state.telegram_bot)

    def test_enabled_bot_starts_on_startup_and_stops_on_shutdown(self):
        # A fake session keeps the polling thread off the network.
        class _Resp:
            status_code = 200

            @staticmethod
            def json():
                return {"result": []}

        class _Session:
            def get(self, *a, **k):
                import time
                time.sleep(0.01)
                return _Resp()

            def post(self, *a, **k):
                return _Resp()

        env = _base_env(self.store, TELEGRAM_ENABLED="true",
                        TELEGRAM_BOT_TOKEN="tok", TELEGRAM_CHAT_ID="42")
        state = AppState.create(AppSettings.from_env(env), env=env)
        from app.telegram import TelegramBot
        app = create_app(state, CycleWorker(state), start_worker=False, run_startup_cycle=False)
        # Replace the auto-built bot with one that cannot touch the network.
        app.state.telegram_bot = TelegramBot(state, state.settings, session=_Session())

        with TestClient(app):
            # PRE-FIX: nothing ever started the bot -> is_running would be
            # False here. POST-FIX: the lifespan started it.
            self.assertTrue(app.state.telegram_bot.is_running)
        # Exiting the lifespan (shutdown) must stop the polling thread.
        self.assertFalse(app.state.telegram_bot.is_running)

    def test_enabled_readonly_and_control_endpoints_unaffected(self):
        # Sanity: adding the bot does not disturb the HTTP surface.
        env = _base_env(self.store, TELEGRAM_ENABLED="true",
                        TELEGRAM_BOT_TOKEN="tok", TELEGRAM_CHAT_ID="42")
        state = AppState.create(AppSettings.from_env(env), env=env)
        from app.telegram import TelegramBot

        class _Session:
            def get(self, *a, **k):
                raise RuntimeError("no network in test")  # bot swallows this

            def post(self, *a, **k):
                raise RuntimeError("no network in test")

        app = create_app(state, CycleWorker(state), start_worker=False, run_startup_cycle=False)
        app.state.telegram_bot = TelegramBot(state, state.settings, session=_Session())
        with TestClient(app) as client:
            self.assertEqual(client.get("/health").status_code, 200)


if __name__ == "__main__":
    unittest.main()
