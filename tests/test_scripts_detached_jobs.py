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


if __name__ == "__main__":
    unittest.main()
