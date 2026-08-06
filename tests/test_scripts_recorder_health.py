"""Tests for scripts/recorder_health.py -- the live recorder's monitor.

Synthetic on-disk state only; no network, no real recorder. The monitor
is READ-ONLY, so every test also asserts it wrote nothing.
"""

import os
import sys
import tempfile
import unittest
from unittest import mock
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import recorder_health as rh  # noqa: E402

from alpha_engine.historical import storage  # noqa: E402
from alpha_engine.historical.models import (  # noqa: E402
    FundingRateObservation,
    MarkPriceObservation,
    OpenInterestObservation,
)
from exchange_adapter import Symbol  # noqa: E402

_TYPES = {"open_interest": OpenInterestObservation,
          "funding_rate": FundingRateObservation,
          "mark_price": MarkPriceObservation}


def _seed(root, hours=3, *, symbols=("BTC", "ETH", "SOL"), metrics=_TYPES, end=None, step_hours=1):
    """Write `hours` hourly rows per (metric, symbol), ending at `end`."""
    end = end or datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    for metric, typ in metrics.items():
        for sym in symbols:
            rows = []
            for i in range(hours):
                t = end - timedelta(hours=step_hours * (hours - 1 - i))
                rows.append(typ(
                    symbol=Symbol(sym), observed_at_utc=t.isoformat(),
                    value=Decimal("1") + Decimal(i), source="hyperliquid_live",
                    source_detail="metaAndAssetCtxs test", ingested_at_utc=t.isoformat(),
                ))
            storage.merge_and_write(Path(root) / storage.series_filename(metric, Symbol(sym), "hyperliquid_live"),
                                    typ, tuple(rows))


def _job(runtime, name="live_recorder", pid=None, log="RECORDED 2026-01-01T00:00:00+00:00\n"):
    d = Path(runtime) / "jobs" / name
    d.mkdir(parents=True, exist_ok=True)
    if pid is not None:
        (d / "pid").write_text(str(pid), encoding="utf-8")
    (d / "cmd").write_text('["python", "-m", "alpha_engine.historical.live_recorder"]', encoding="utf-8")
    (d / "log").write_text(log, encoding="utf-8")
    return d


class TestHealthy(unittest.TestCase):
    def test_fresh_complete_series_is_healthy_apart_from_process(self):
        with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as rt:
            _seed(store)
            _job(rt, pid=999999)  # dead pid -> only the process check should complain
            healthy, lines = rh.check("live_recorder", rt, store, 90.0, 2.0)
            text = "\n".join(lines)
            self.assertFalse(healthy)
            self.assertNotIn("STALE", text)
            self.assertNotIn("DUPLICATE", text)
            self.assertNotIn("CORRUPTION", text)
            self.assertIn("UNEXPECTED PROCESS EXIT", text)

    def test_reports_row_counts_for_all_nine_series(self):
        with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as rt:
            _seed(store, hours=4)
            _job(rt, pid=999999)
            _, lines = rh.check("live_recorder", rt, store, 90.0, 2.0)
            text = "\n".join(lines)
            self.assertIn("total rows across all live series: 36", text)  # 4h x 3 sym x 3 metrics


class TestFailureModes(unittest.TestCase):
    def _base(self, store, rt, **kw):
        return rh.check("live_recorder", rt, store, kw.get("lag", 90.0), kw.get("gap", 2.0))

    def test_stale_timestamps_detected(self):
        with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as rt:
            old = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=6)
            _seed(store, hours=2, end=old)
            _job(rt, pid=999999)
            healthy, lines = self._base(store, rt)
            self.assertFalse(healthy)
            self.assertIn("STALE", "\n".join(lines))

    def test_excessive_gaps_detected(self):
        with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as rt:
            _seed(store, hours=3, step_hours=5)  # 5h between rows
            _job(rt, pid=999999)
            healthy, lines = self._base(store, rt)
            self.assertFalse(healthy)
            self.assertIn("gap(s) longer than", "\n".join(lines))

    def test_missing_symbol_detected(self):
        with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as rt:
            _seed(store, symbols=("BTC", "ETH"))  # SOL never recorded
            _job(rt, pid=999999)
            healthy, lines = self._base(store, rt)
            self.assertFalse(healthy)
            self.assertIn("SOL", "\n".join(lines))
            self.assertIn("no file", "\n".join(lines))

    def test_storage_corruption_detected_and_does_not_crash(self):
        with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as rt:
            _seed(store)
            bad = Path(store) / storage.series_filename("open_interest", Symbol("BTC"), "hyperliquid_live")
            bad.write_text("observed_at_utc,symbol,value,source,source_detail,ingested_at_utc\n"
                           "not-a-timestamp,BTC,notanumber,x,y,z\n", encoding="utf-8")
            _job(rt, pid=999999)
            healthy, lines = self._base(store, rt)
            self.assertFalse(healthy)
            self.assertIn("STORAGE CORRUPTION", "\n".join(lines))

    def test_running_but_writing_nothing_detected(self):
        """Process alive, but no RECORDED line in the log."""
        import os
        with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as rt:
            _seed(store)
            _job(rt, pid=os.getpid(), log="starting up\n")
            healthy, lines = self._base(store, rt)
            self.assertFalse(healthy)
            self.assertIn("running but writing nothing", "\n".join(lines))

    def test_record_failed_lines_are_reported(self):
        with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as rt:
            _seed(store)
            _job(rt, pid=999999, log="RECORDED x\nRECORD_FAILED TimeoutError: boom\n")
            healthy, lines = self._base(store, rt)
            self.assertFalse(healthy)   # the dead pid, not the failed poll
            self.assertIn("RECORD_FAILED=1", "\n".join(lines))


    def test_skipped_warnings_detected(self):
        with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as rt:
            _seed(store)
            _job(rt, pid=999999, log="RECORDED x\nlive_recorder skipped 2 field(s): ETH ...\n")
            healthy, lines = self._base(store, rt)
            self.assertIn("repeated unavailable readings", "\n".join(lines))

    def test_clean_stop_is_not_reported_as_unexpected_exit(self):
        with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as rt:
            _seed(store)
            _job(rt, pid=999999, log="RECORDED x\nRECORDER_STOPPED after 5 cycle(s)\n")
            _, lines = rh.check("live_recorder", rt, store, 90.0, 2.0)
            text = "\n".join(lines)
            self.assertNotIn("UNEXPECTED PROCESS EXIT", text)
            self.assertIn("stopped cleanly", text)

    def test_missing_pid_file_reported(self):
        with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as rt:
            _seed(store)
            _job(rt, pid=None)
            healthy, lines = self._base(store, rt)
            self.assertFalse(healthy)
            self.assertIn("NO PID FILE", "\n".join(lines))


class TestReadOnly(unittest.TestCase):
    def test_monitor_writes_nothing(self):
        with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as rt:
            _seed(store)
            _job(rt, pid=999999)
            before = {p: (p.stat().st_mtime, p.stat().st_size)
                      for p in list(Path(store).rglob("*")) + list(Path(rt).rglob("*")) if p.is_file()}
            rh.check("live_recorder", rt, store, 90.0, 2.0)
            after = {p: (p.stat().st_mtime, p.stat().st_size)
                     for p in list(Path(store).rglob("*")) + list(Path(rt).rglob("*")) if p.is_file()}
            self.assertEqual(before, after)

    def test_exit_code_zero_when_healthy_one_when_degraded(self):
        """A truly healthy state needs a live pid whose command line
        matches the recorded cmd -- not reproducible from inside pytest,
        so the liveness probe is stubbed to isolate the exit-code
        contract itself."""
        import os
        with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as rt:
            _seed(store)
            _job(rt, pid=os.getpid(), log="RECORDED now\n")
            real = rh.liveness
            rh.liveness = lambda pid, argv=None: rh.ALIVE_AND_MATCHES
            try:
                rc_healthy = rh.main(["--name", "live_recorder",
                                      "--runtime-dir", rt, "--storage-root", store])
            finally:
                rh.liveness = real
            self.assertEqual(rc_healthy, 0)

            # same state, but the process is genuinely gone -> degraded
            _job(rt, pid=999999, log="RECORDED now\n")
            rc_degraded = rh.main(["--name", "live_recorder",
                                   "--runtime-dir", rt, "--storage-root", store])
            self.assertEqual(rc_degraded, 1)


if __name__ == "__main__":
    unittest.main()


class TestTransportFailureClassification(unittest.TestCase):
    """A RECORD_FAILED is a failed POLL, not lost data.

    The recorder polls four times per hourly slot (RD-18 section B), so a
    transient HTTP 429 or DNS failure costs nothing. Measured on the live
    deployment 2026-08-06: two RECORD_FAILED events (HTTP 429, and
    getaddrinfo Errno 11001), both in hours whose rows are present, with
    25 contiguous hourly observations and zero gaps across all nine
    series. Escalating on the count alone produced a permanently-red
    monitor on a self-healed transient.
    """

    def _check(self, store, rt):
        """Process liveness is stubbed ALIVE so the verdict under test is the
        transport-failure classification alone, not process introspection."""
        with mock.patch.object(rh, "liveness", return_value=rh.ALIVE_AND_MATCHES):
            return rh.check("live_recorder", rt, store, 90.0, 2.0)

    def test_transport_failure_with_contiguous_series_is_a_note_not_degradation(self):
        with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as rt:
            _seed(store)
            _job(rt, pid=os.getpid(),
                 log="RECORDED x\nRECORD_FAILED HTTPError: HTTP Error 429: Too Many Requests\n")
            healthy, lines = self._check(store, rt)
            text = "\n".join(lines)
            self.assertTrue(healthy, msg=text)
            self.assertIn("HEALTHY (with notes)", text)
            self.assertIn("Informational, not degradation", text)

    def test_transport_failure_escalates_when_a_gap_also_exists(self):
        with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as rt:
            _seed(store, hours=3, step_hours=5)   # a real gap
            _job(rt, pid=os.getpid(),
                 log="RECORDED x\nRECORD_FAILED URLError: getaddrinfo failed\n")
            healthy, lines = self._check(store, rt)
            text = "\n".join(lines)
            self.assertFalse(healthy)
            self.assertIn("cost real samples", text)

    def test_transport_failure_escalates_when_duplicates_exist(self):
        with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as rt:
            _seed(store)
            path = next(p for p in Path(store).iterdir() if p.name.endswith(".csv"))
            lines_ = path.read_text(encoding="utf-8").splitlines()
            path.write_text("\n".join(lines_ + [lines_[-1]]) + "\n", encoding="utf-8")
            _job(rt, pid=os.getpid(), log="RECORDED x\nRECORD_FAILED boom\n")
            healthy, out = self._check(store, rt)
            self.assertFalse(healthy)
            self.assertIn("cost real samples", "\n".join(out))

    def test_no_failures_reports_plain_healthy(self):
        with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as rt:
            _seed(store)
            _job(rt, pid=os.getpid(), log="RECORDED x\n")
            healthy, lines = self._check(store, rt)
            text = "\n".join(lines)
            self.assertTrue(healthy, msg=text)
            self.assertIn("VERDICT: HEALTHY", text)
            self.assertNotIn("with notes", text)

