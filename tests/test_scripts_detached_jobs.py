"""Verification tests for the operational job-control scripts
(scripts/run_detached_job.py, scripts/job_status.py,
scripts/liquidation_backfill_progress.py).

These are OPERATIONS tooling, not pipeline code: they exist because the
Backlog 1.5 backfill died when its parent chat session ended. They must
never write to, signal, or otherwise disturb a running collection --
several tests below pin exactly that.

No network, no AWS, no real collection: the "jobs" here are short-lived
`python -c` commands, and the progress reporter is pointed at synthetic
CSVs in a temp directory.
"""

import subprocess
import sys
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from scripts import job_status, liquidation_backfill_progress, run_detached_job  # noqa: E402


def _wait_until(predicate, timeout_s=30.0, interval_s=0.2):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval_s)
    return False


def _wait_for_job_exit(runtime_dir, name, timeout_s=30.0):
    """Block until a detached job's process is gone.

    Necessary before a TemporaryDirectory teardown: a detached child holds
    its own inherited handle on the job log (by design -- that is how it
    keeps writing after the parent lets go), and on Windows an open handle
    blocks directory removal. Tests must therefore let the child finish
    rather than yanking its log out from under it.
    """
    pid_file = run_detached_job.job_dir(name, runtime_dir) / "pid"
    if not pid_file.is_file():
        return True
    raw = pid_file.read_text(encoding="utf-8").strip()
    if not raw.isdigit():
        return True
    pid = int(raw)
    return _wait_until(lambda: not run_detached_job.is_running(pid), timeout_s=timeout_s)


class TestDetachedJobLifecycle(unittest.TestCase):
    def test_start_records_pid_cmd_started_and_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = run_detached_job.start(
                "unit_a", [sys.executable, "-c", "print('hello')"], runtime_dir=tmp,
            )
            self.assertEqual(rc, 0)
            d = run_detached_job.job_dir("unit_a", tmp)
            for artifact in ("pid", "cmd", "started", "log"):
                self.assertTrue((d / artifact).is_file(), f"missing {artifact}")
            self.assertTrue((d / "pid").read_text(encoding="utf-8").strip().isdigit())
            _wait_for_job_exit(tmp, "unit_a")

    def test_child_output_is_captured_to_the_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_detached_job.start(
                "unit_b", [sys.executable, "-c", "print('MARKER_LINE', flush=True)"], runtime_dir=tmp,
            )
            log = run_detached_job.job_dir("unit_b", tmp) / "log"
            self.assertTrue(
                _wait_until(lambda: "MARKER_LINE" in log.read_text(encoding="utf-8", errors="replace")),
                "child stdout never reached the job log",
            )
            _wait_for_job_exit(tmp, "unit_b")

    def test_stderr_is_merged_into_the_same_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_detached_job.start(
                "unit_c",
                [sys.executable, "-c", "import sys; print('ERR_MARKER', file=sys.stderr, flush=True)"],
                runtime_dir=tmp,
            )
            log = run_detached_job.job_dir("unit_c", tmp) / "log"
            self.assertTrue(
                _wait_until(lambda: "ERR_MARKER" in log.read_text(encoding="utf-8", errors="replace")),
                "child stderr was not merged into the job log -- a silent crash would leave no trace",
            )
            _wait_for_job_exit(tmp, "unit_c")

    def test_refuses_to_start_a_second_copy_while_one_is_running(self):
        """The dangerous case this guards: two backfills writing the same
        CSVs concurrently."""
        with tempfile.TemporaryDirectory() as tmp:
            run_detached_job.start("unit_d", [sys.executable, "-c", "import time; time.sleep(20)"], runtime_dir=tmp)
            pid = int((run_detached_job.job_dir("unit_d", tmp) / "pid").read_text(encoding="utf-8").strip())
            try:
                self.assertTrue(_wait_until(lambda: run_detached_job.is_running(pid), timeout_s=10))
                rc = run_detached_job.start("unit_d", [sys.executable, "-c", "pass"], runtime_dir=tmp)
                self.assertEqual(rc, 1, "a second concurrent copy of the same job was allowed to start")
            finally:
                subprocess.run(
                    (["taskkill", "/PID", str(pid), "/F"] if sys.platform == "win32"
                     else ["kill", "-9", str(pid)]),
                    capture_output=True,
                )
                _wait_for_job_exit(tmp, "unit_d")

    def test_log_is_appended_across_restarts_not_truncated(self):
        """A resumed run's output must not erase the interrupted run's."""
        with tempfile.TemporaryDirectory() as tmp:
            run_detached_job.start("unit_e", [sys.executable, "-c", "print('FIRST_RUN', flush=True)"], runtime_dir=tmp)
            log = run_detached_job.job_dir("unit_e", tmp) / "log"
            self.assertTrue(_wait_until(lambda: "FIRST_RUN" in log.read_text(encoding="utf-8", errors="replace")))
            pid = int((log.parent / "pid").read_text(encoding="utf-8").strip())
            self.assertTrue(_wait_until(lambda: not run_detached_job.is_running(pid), timeout_s=20))

            run_detached_job.start("unit_e", [sys.executable, "-c", "print('SECOND_RUN', flush=True)"], runtime_dir=tmp)
            self.assertTrue(_wait_until(lambda: "SECOND_RUN" in log.read_text(encoding="utf-8", errors="replace")))
            body = log.read_text(encoding="utf-8", errors="replace")
            self.assertIn("FIRST_RUN", body, "restart truncated the earlier run's log")
            _wait_for_job_exit(tmp, "unit_e")

    def test_empty_command_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                run_detached_job.start("unit_f", [], runtime_dir=tmp)


class TestGuardFailsClosed(unittest.TestCase):
    """M1 (independent QA audit, Medium): the duplicate-job guard must fail
    CLOSED. `storage.merge_and_write` is read-modify-write with no
    inter-process lock, so two collectors on the same CSVs produce a
    silent lost update -- if we cannot tell whether the recorded job is
    alive, refusing to start is the only safe answer."""

    def setUp(self):
        self._real_run = subprocess.run

    def tearDown(self):
        subprocess.run = self._real_run

    def _break_the_probe(self):
        def failing(*a, **k):
            raise subprocess.TimeoutExpired(cmd="tasklist", timeout=15)
        subprocess.run = failing

    def test_liveness_is_unknown_when_the_probe_fails(self):
        import os
        self._break_the_probe()
        if os.name == "nt":
            self.assertEqual(run_detached_job.liveness(os.getpid(), ["python", "-c", "x"]),
                             run_detached_job.UNKNOWN)

    def test_start_refuses_when_liveness_cannot_be_determined(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            d = run_detached_job.job_dir("m1", tmp)
            d.mkdir(parents=True, exist_ok=True)
            (d / "pid").write_text(str(os.getpid()), encoding="utf-8")
            (d / "cmd").write_text('["python", "-m", "some.module"]', encoding="utf-8")
            self._break_the_probe()
            rc = run_detached_job.start("m1", [sys.executable, "-c", "pass"], runtime_dir=tmp)
            self.assertEqual(rc, 1, "guard failed OPEN -- a second concurrent copy was allowed")

    def test_a_refused_start_does_not_leave_the_lock_behind(self):
        """A refusal must not wedge the job so later legitimate starts fail."""
        import os
        with tempfile.TemporaryDirectory() as tmp:
            d = run_detached_job.job_dir("m1b", tmp)
            d.mkdir(parents=True, exist_ok=True)
            (d / "pid").write_text(str(os.getpid()), encoding="utf-8")
            (d / "cmd").write_text('["python", "-m", "some.module"]', encoding="utf-8")
            self._break_the_probe()
            run_detached_job.start("m1b", [sys.executable, "-c", "pass"], runtime_dir=tmp)
            subprocess.run = self._real_run
            self.assertFalse((d / "lock").exists(), "refusal left a stale lock behind")


class TestProcessIdentity(unittest.TestCase):
    """M2 (independent QA audit, Medium): a pid alone does not identify a
    job. An OS-recycled pid belonging to an unrelated process must not be
    reported as the job still running."""

    def test_recycled_pid_is_not_mistaken_for_the_job(self):
        import os
        # This test process is alive but is emphatically NOT the recorded job.
        state = run_detached_job.liveness(os.getpid(), ["python", "-m", "totally.different.module"])
        self.assertEqual(state, run_detached_job.RECYCLED)

    def test_matching_pid_and_argv_is_recognised_as_the_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_detached_job.start(
                "ident", [sys.executable, "-c", "import time; time.sleep(20)"], runtime_dir=tmp,
            )
            d = run_detached_job.job_dir("ident", tmp)
            pid = int((d / "pid").read_text(encoding="utf-8").strip())
            import json as _json
            argv = _json.loads((d / "cmd").read_text(encoding="utf-8"))
            try:
                self.assertEqual(run_detached_job.liveness(pid, argv),
                                 run_detached_job.ALIVE_AND_MATCHES)
            finally:
                subprocess.run(
                    (["taskkill", "/PID", str(pid), "/F"] if sys.platform == "win32"
                     else ["kill", "-9", str(pid)]),
                    capture_output=True,
                )
                _wait_for_job_exit(tmp, "ident")

    def test_a_recycled_pid_does_not_block_a_legitimate_restart(self):
        """The practical harm of M2: a dead job whose pid was recycled must
        still be restartable."""
        import os
        with tempfile.TemporaryDirectory() as tmp:
            d = run_detached_job.job_dir("m2", tmp)
            d.mkdir(parents=True, exist_ok=True)
            (d / "pid").write_text(str(os.getpid()), encoding="utf-8")  # unrelated live process
            (d / "cmd").write_text('["python", "-m", "the.real.job"]', encoding="utf-8")
            rc = run_detached_job.start("m2", [sys.executable, "-c", "print('resumed')"], runtime_dir=tmp)
            self.assertEqual(rc, 0, "a recycled pid wrongly blocked a legitimate restart")
            _wait_for_job_exit(tmp, "m2")

    def test_liveness_without_recorded_argv_is_unknown_not_a_match(self):
        import os
        self.assertEqual(run_detached_job.liveness(os.getpid(), None), run_detached_job.UNKNOWN)

    def test_dead_pid_is_gone_regardless_of_argv(self):
        self.assertEqual(run_detached_job.liveness(999_999_999, ["python"]), run_detached_job.GONE)


class TestStartLock(unittest.TestCase):
    """L1 (independent QA audit, Low): the guard reads the pid file before
    spawning and writes the new pid after, so without an atomic claim two
    near-simultaneous starts could both pass."""

    def test_a_held_lock_blocks_a_second_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = run_detached_job.job_dir("lock1", tmp)
            d.mkdir(parents=True, exist_ok=True)
            import os
            # A lock naming a live holder whose identity cannot be confirmed.
            (d / "lock").write_text(str(os.getpid()), encoding="utf-8")
            rc = run_detached_job.start("lock1", [sys.executable, "-c", "pass"], runtime_dir=tmp)
            self.assertEqual(rc, 1, "an actively held lock did not block a second start")

    def test_a_stale_lock_from_a_dead_holder_is_reclaimed(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = run_detached_job.job_dir("lock2", tmp)
            d.mkdir(parents=True, exist_ok=True)
            (d / "lock").write_text("999999999", encoding="utf-8")  # definitively dead
            rc = run_detached_job.start("lock2", [sys.executable, "-c", "print('ok')"], runtime_dir=tmp)
            self.assertEqual(rc, 0, "a stale lock from a dead holder wedged the job permanently")
            _wait_for_job_exit(tmp, "lock2")

    def test_successful_start_records_the_holder_in_the_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_detached_job.start("lock3", [sys.executable, "-c", "import time; time.sleep(5)"], runtime_dir=tmp)
            d = run_detached_job.job_dir("lock3", tmp)
            self.assertTrue((d / "lock").is_file())
            self.assertEqual((d / "lock").read_text(encoding="utf-8").strip(),
                             (d / "pid").read_text(encoding="utf-8").strip())
            pid = int((d / "pid").read_text(encoding="utf-8").strip())
            subprocess.run(
                (["taskkill", "/PID", str(pid), "/F"] if sys.platform == "win32"
                 else ["kill", "-9", str(pid)]),
                capture_output=True,
            )
            _wait_for_job_exit(tmp, "lock3")


class TestIsRunning(unittest.TestCase):
    def test_current_process_is_running(self):
        import os
        self.assertTrue(run_detached_job.is_running(os.getpid()))

    def test_absurd_pid_is_not_running_and_does_not_raise(self):
        self.assertFalse(run_detached_job.is_running(999_999_999))

    def test_invalid_pid_is_not_running(self):
        self.assertFalse(run_detached_job.is_running(-1))
        self.assertFalse(run_detached_job.is_running(0))


class TestJobStatusIsReadOnly(unittest.TestCase):
    def test_describe_unknown_job_returns_nonzero_without_creating_anything(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = job_status.describe("nope", tmp, lines=5)
            self.assertEqual(rc, 1)
            self.assertFalse((Path(tmp) / "jobs" / "nope").exists())

    def test_describe_does_not_modify_job_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_detached_job.start("unit_g", [sys.executable, "-c", "print('x')"], runtime_dir=tmp)
            d = run_detached_job.job_dir("unit_g", tmp)
            before = {p.name: p.read_bytes() for p in d.iterdir() if p.name != "log"}
            job_status.describe("unit_g", tmp, lines=5)
            after = {p.name: p.read_bytes() for p in d.iterdir() if p.name != "log"}
            self.assertEqual(before, after, "job_status mutated job state; it must be read-only")
            _wait_for_job_exit(tmp, "unit_g")

    def test_list_jobs_with_no_directory_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(job_status.list_jobs(tmp), 0)


def _write_liquidation_csv(path: Path, days, symbol="BTC"):
    header = ("observed_at_utc,symbol,price,size,side,direction,method,"
              "liquidated_user,mark_price,tid,source,source_detail,ingested_at_utc\n")
    lines = [header]
    tid = 1
    for day in days:
        for side, direction in (("B", "Close Short"), ("A", "Close Long")):
            lines.append(
                f"{day}T00:00:00.000000+00:00,{symbol},50000,0.1,{side},{direction},market,"
                f"0xabc,50001,{tid},hyperliquid_s3,k.lz4,2026-01-01T00:00:00+00:00\n"
            )
        tid += 1
    path.write_text("".join(lines), encoding="utf-8")


class TestLiquidationBackfillProgress(unittest.TestCase):
    def test_reports_contiguous_runs_and_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Two separate runs, exactly like the real pilot-plus-partial-backfill state.
            days = ["2025-07-27", "2025-07-28", "2026-06-01", "2026-06-02"]
            _write_liquidation_csv(root / "liquidation__BTC__hyperliquid_s3.csv", days)
            (root / ".liquidation_checkpoint.json").write_text(
                '{"last_processed_key": "node_fills_by_block/hourly/20250728/23.lz4"}', encoding="utf-8",
            )
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            rc = liquidation_backfill_progress.report(str(root), date(2025, 7, 27), date(2026, 7, 28))
            self.assertEqual(rc, 0)
            after = {p.name: p.read_bytes() for p in root.iterdir()}
            self.assertEqual(before, after, "progress reporter mutated data; it must be read-only")

    def test_missing_checkpoint_and_files_are_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                liquidation_backfill_progress.report(tmp, date(2025, 7, 27), date(2026, 7, 28)), 0,
            )

    def test_contiguous_runs_splits_on_gaps(self):
        runs = liquidation_backfill_progress._contiguous_runs(
            {date(2025, 1, 1), date(2025, 1, 2), date(2025, 3, 1)}
        )
        self.assertEqual(
            runs, [(date(2025, 1, 1), date(2025, 1, 2), 2), (date(2025, 3, 1), date(2025, 3, 1), 1)],
        )

    def test_contiguous_runs_empty_input(self):
        self.assertEqual(liquidation_backfill_progress._contiguous_runs(set()), [])

    def test_a_wholly_one_sided_series_is_flagged(self):
        """L3 (independent QA audit, Low): comparing only the side counts
        that happen to be PRESENT lets an entirely one-sided series pass --
        a single distinct count is trivially 'balanced'. Both A and B must
        be present and equal."""
        import io
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "liquidation__BTC__hyperliquid_s3.csv"
            header = ("observed_at_utc,symbol,price,size,side,direction,method,"
                      "liquidated_user,mark_price,tid,source,source_detail,ingested_at_utc\n")
            # 2 rows sharing one tid -- so rows/event is a clean 2.00 -- but
            # BOTH are side "B"; a real liquidation pair is always B and A.
            rows = "".join(
                f"2025-07-27T00:00:0{i}.000000+00:00,BTC,5,0.1,B,Close Short,market,0xa,5,1,"
                f"hyperliquid_s3,k.lz4,2026-01-01T00:00:00+00:00\n" for i in range(2)
            )
            path.write_text(header + rows, encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                liquidation_backfill_progress.report(str(root), date(2025, 7, 27), date(2026, 7, 28))
            out = buf.getvalue()
            self.assertIn("rows/event=2.00", out, "precondition: rows/event must look clean")
            self.assertIn("not a balanced A/B pair", out,
                          "a wholly one-sided series passed both sanity checks unflagged")

    def test_balanced_pair_produces_no_warning(self):
        import io
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_liquidation_csv(root / "liquidation__BTC__hyperliquid_s3.csv", ["2025-07-27"])
            buf = io.StringIO()
            with redirect_stdout(buf):
                liquidation_backfill_progress.report(str(root), date(2025, 7, 27), date(2026, 7, 28))
            self.assertNotIn("WARNING", buf.getvalue())

    def test_checkpoint_outside_the_expected_window_clamps_the_day_count(self):
        """I1: the percentage was already clamped, but the raw day count
        could print negative alongside it."""
        import io
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".liquidation_checkpoint.json").write_text(
                '{"last_processed_key": "node_fills_by_block/hourly/20250101/23.lz4"}', encoding="utf-8",
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                liquidation_backfill_progress.report(str(root), date(2025, 7, 27), date(2026, 7, 28))
            out = buf.getvalue()
            self.assertNotIn("-206/", out, "negative day count printed")
            self.assertIn("0/367 days", out)
            self.assertIn("outside the expected window", out)


if __name__ == "__main__":
    unittest.main()
