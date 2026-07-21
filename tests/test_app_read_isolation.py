"""Regression tests for H3: read endpoints must never perform venue I/O
and must never block on (or contend for) the engine lock.

THE PREVIOUS FAILURE: /status, /portfolio, /reports, and /metrics each
called AppState.capture(), which held the global engine_lock while making
live venue REST calls (frontendOpenOrders + clearinghouseState + one
allMids per open position, each with a 10s timeout). A slow venue inside
one unauthenticated read blocked the worker's next cycle and serialized
every concurrent read; a dashboard poll alone generated continuous venue
traffic under the global lock.
"""

import tempfile
import threading
import unittest
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from app.api import create_app
from app.runtime import AppSettings, AppState, CycleWorker

_SIGNING_ENV = {"TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1": "signing-secret-material"}

_READ_PATHS = ("/status", "/portfolio", "/reports", "/metrics")


class _ReadIsolationCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        env = {
            **_SIGNING_ENV,
            "ENGINE_CONFIG_PATH": "deploy/engine.paper.toml",
            "ENGINE_STORE_PATH": str(Path(self._tmp.name) / "events.log"),
            "PORTFOLIO_INITIAL_DEPOSIT": "100000",
            "RISK_MAX_STALE_DATA_SECONDS": "3600",
        }
        self.state = AppState.create(AppSettings.from_env(env), env=env)
        app = create_app(self.state, CycleWorker(self.state),
                         start_worker=False, run_startup_cycle=False)
        self.client = TestClient(app)
        self.client.__enter__()
        self.addCleanup(lambda: self.client.__exit__(None, None, None))

    def _instrument_venue_reads(self):
        """Count every venue-read the adapter would serve. On the live
        adapter these are network round-trips; the counter is
        adapter-agnostic."""
        adapter = self.state.engine.adapter
        counter = {"n": 0}
        for name in ("get_orders", "get_mark_price", "get_positions", "reconcile"):
            original = getattr(adapter, name)

            def wrapped(*args, _original=original, **kwargs):
                counter["n"] += 1
                return _original(*args, **kwargs)

            setattr(adapter, name, wrapped)
        return counter


class TestReadsPerformNoVenueIO(_ReadIsolationCase):
    def test_reads_trigger_zero_adapter_calls(self):
        """PRE-FIX: every /status did 2+N venue reads. POST-FIX: zero."""
        self.state.run_one_cycle()          # produce the cached snapshot
        counter = self._instrument_venue_reads()
        for _ in range(5):
            for path in _READ_PATHS:
                self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertEqual(counter["n"], 0)   # twenty reads, zero venue calls

    def test_reads_work_before_any_cycle_with_zero_venue_calls(self):
        counter = self._instrument_venue_reads()
        for path in _READ_PATHS:
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertEqual(counter["n"], 0)
        body = self.client.get("/status").json()
        # Degraded-but-honest pre-cycle shape: venue-derived fields are null.
        self.assertIsNone(body["open_order_count"])
        self.assertIsNone(body["reconciliation"])


class TestReadsNeverBlockOnEngineLock(_ReadIsolationCase):
    def test_reads_complete_while_the_engine_lock_is_held(self):
        """PRE-FIX: capture() acquired engine_lock, so a long-running
        cycle blocked every read for its full duration. POST-FIX: reads
        take no engine lock at all -- they complete while another thread
        holds it indefinitely."""
        self.state.run_one_cycle()
        lock_held = threading.Event()
        release = threading.Event()

        def hold_lock():
            with self.state.engine_lock:      # simulates a slow cycle mid-flight
                lock_held.set()
                release.wait(timeout=10)

        holder = threading.Thread(target=hold_lock)
        holder.start()
        self.addCleanup(holder.join)
        self.addCleanup(release.set)
        self.assertTrue(lock_held.wait(timeout=5))

        finished = {}

        def read_all():
            finished["codes"] = [self.client.get(p).status_code for p in _READ_PATHS]

        reader = threading.Thread(target=read_all)
        reader.start()
        reader.join(timeout=5)                # PRE-FIX: still blocked here
        self.assertFalse(reader.is_alive(), "reads blocked on the engine lock")
        self.assertEqual(finished["codes"], [200, 200, 200, 200])

    def test_concurrent_reads_and_cycles_are_consistent(self):
        errors = []
        stop = threading.Event()

        def reader():
            while not stop.is_set():
                for path in _READ_PATHS:
                    if self.client.get(path).status_code != 200:
                        errors.append(path)

        threads = [threading.Thread(target=reader) for _ in range(4)]
        for t in threads:
            t.start()
        try:
            for _ in range(3):
                self.state.run_one_cycle()
        finally:
            stop.set()
            for t in threads:
                t.join(timeout=5)
        self.assertEqual(errors, [])
        self.assertEqual(self.state.cycles_run, 3)


class TestSnapshotFreshness(_ReadIsolationCase):
    def test_cycle_refreshes_the_read_snapshot(self):
        first = self.client.get("/status").json()
        self.state.run_one_cycle()
        second = self.client.get("/status").json()
        self.assertNotEqual(first["captured_at_utc"], second["captured_at_utc"])
        # Post-cycle the snapshot is the FULL one: venue-derived fields present.
        self.assertIsNotNone(second["open_order_count"])
        self.assertIsNotNone(second["reconciliation"])

    def test_emergency_stop_refreshes_without_venue_io(self):
        self.state.run_one_cycle()
        counter = self._instrument_venue_reads()
        self.state.emergency_stop()
        stop_reads = counter["n"]             # cancel_all may read; snapshot must not add venue reads beyond it
        body = self.client.get("/status").json()
        self.assertTrue(body["kill_switch_active"])
        self.assertTrue(body["emergency_stopped"])
        self.assertEqual(counter["n"], stop_reads)   # the /status added zero


if __name__ == "__main__":
    unittest.main()
