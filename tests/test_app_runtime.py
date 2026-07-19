"""Tests for app.runtime: settings, engine construction from env, AppState
cycle/observe/emergency-stop, and the background CycleWorker.

Uses the real paper config (deploy/engine.paper.toml) and MockExchangeAdapter
-- no network. Each test gets its own temp event-store path.
"""

import tempfile
import time
import unittest
from decimal import Decimal
from pathlib import Path

from secrets_boundary import SecretRevokedError

from app.runtime import AppSettings, AppState, CycleWorker, build_engine_from_settings

_SIGNING_ENV = {"TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1": "signing-secret-material"}


def _env(store_path, **overrides):
    e = dict(_SIGNING_ENV)
    e["ENGINE_CONFIG_PATH"] = "deploy/engine.paper.toml"
    e["ENGINE_STORE_PATH"] = str(store_path)
    e["WORKER_ENABLED"] = "true"
    e["CYCLE_INTERVAL_SECONDS"] = "1"
    e.update(overrides)
    return e


class _RuntimeCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store_path = Path(self._tmp.name) / "events.log"

    def _state(self, **env_overrides):
        env = _env(self.store_path, **env_overrides)
        settings = AppSettings.from_env(env)
        state = AppState.create(settings, env=env)
        self.addCleanup(state.shutdown)
        return state


class TestSettings(unittest.TestCase):
    def test_defaults_boot_in_paper_mode(self):
        settings = AppSettings.from_env(dict(_SIGNING_ENV))
        self.assertEqual(settings.port, 8000)
        self.assertTrue(settings.worker_enabled)
        self.assertEqual(settings.engine_config_path, "deploy/engine.paper.toml")
        self.assertEqual(settings.log_format, "json")

    def test_railway_port_is_honored(self):
        settings = AppSettings.from_env({"PORT": "5555", **_SIGNING_ENV})
        self.assertEqual(settings.port, 5555)

    def test_invalid_port_raises_clearly(self):
        with self.assertRaises(ValueError):
            AppSettings.from_env({"PORT": "not-a-number", **_SIGNING_ENV})


class TestEngineConstruction(_RuntimeCase):
    def test_builds_engine_universe_and_risk_profile(self):
        env = _env(self.store_path)
        settings = AppSettings.from_env(env)
        engine, universe, risk_profile = build_engine_from_settings(settings, env=env)
        self.addCleanup(engine.event_store.close)
        self.assertTrue(len(universe) >= 1)
        self.assertGreater(risk_profile.max_positions, 0)


class TestAppStateCycle(_RuntimeCase):
    def test_run_one_cycle_starts_engine_and_records_result(self):
        state = self._state()
        result = state.run_one_cycle()
        self.assertTrue(state.engine.is_started)
        self.assertEqual(state.cycles_run, 1)
        self.assertIs(state.last_cycle, result)
        self.assertIsNotNone(state.last_cycle_completed_at_utc)

    def test_capture_returns_snapshot_reflecting_the_last_cycle(self):
        state = self._state()
        state.run_one_cycle()
        snapshot = state.capture()
        self.assertTrue(snapshot.is_started)
        self.assertIsNotNone(snapshot.last_cycle_completed_at_utc)

    def test_emergency_stop_revokes_signing(self):
        state = self._state()
        state.run_one_cycle()
        state.emergency_stop()
        self.assertTrue(state.emergency_stopped)
        # After revoke_all, any further signing attempt fails closed --
        # a subsequent cycle that needs to connect/sign must raise.
        with self.assertRaises(SecretRevokedError):
            state.engine.signing_boundary.sign(
                state.engine._signing_key_ref if hasattr(state.engine, "_signing_key_ref") else "hyperliquid_signing_key_v1",
                __import__("secrets_boundary").SigningPurpose.AUTH, b"probe",
            )


class TestCycleWorker(_RuntimeCase):
    def test_worker_runs_cycles_on_interval_then_stops(self):
        state = self._state()
        cycles = []
        worker = CycleWorker(state, on_cycle=lambda r: cycles.append(r))
        worker.start()
        self.addCleanup(worker.stop)
        # Interval is 1s; wait long enough for at least one cycle.
        deadline = time.time() + 8
        while state.cycles_run < 1 and time.time() < deadline:
            time.sleep(0.1)
        worker.stop()
        self.assertGreaterEqual(state.cycles_run, 1)
        self.assertFalse(worker.is_running)

    def test_worker_run_once_is_synchronous(self):
        state = self._state()
        worker = CycleWorker(state)
        result = worker.run_once()
        self.assertEqual(state.cycles_run, 1)
        self.assertIs(result, state.last_cycle)


if __name__ == "__main__":
    unittest.main()
