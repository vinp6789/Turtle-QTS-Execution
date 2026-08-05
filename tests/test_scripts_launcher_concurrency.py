"""Concurrency regression tests for scripts/run_detached_job.py (H1/H2).

THE DEFECT THESE LOCK IN A FIX FOR: _acquire_lock created the lock file
EMPTY and only stamped it with the child's pid after the liveness probe
and Popen had completed. For that whole window (measured 0.25s to ~35s)
a second caller read an empty lock, could not identify a holder, fell
through to the steal path, and both callers spawned a child. Two
collectors on the same CSVs silently lose one writer's rows, because
storage.merge_and_write is read-modify-write with no inter-process lock.

These tests use REAL processes and REAL threads -- the previous test
suite had zero concurrency coverage, which is why the defect survived an
audit that claimed it fixed.
"""

import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_detached_job as rdj  # noqa: E402

_SLEEPER = [sys.executable, "-c", "import time; time.sleep(30)"]
_QUICK = [sys.executable, "-c", "pass"]


def _wait_gone(pid, timeout=15.0):
    end = time.time() + timeout
    while time.time() < end:
        if rdj.liveness(pid, None) == rdj.GONE:
            return True
        time.sleep(0.1)
    return False


def _kill(pid):
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, timeout=20)
        else:
            os.kill(pid, 9)
    except Exception:  # noqa: BLE001
        pass


class _JobTemp:
    """Temp runtime dir that always reaps any job it started."""

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self._started = []
        return self

    def pid_of(self, name):
        p = rdj.job_dir(name, self.root) / "pid"
        return int(p.read_text(encoding="utf-8").strip()) if p.is_file() else None

    def track(self, name):
        pid = self.pid_of(name)
        if pid:
            self._started.append(pid)
        return pid

    def __exit__(self, *exc):
        for pid in self._started:
            _kill(pid)
            _wait_gone(pid)
        for _ in range(10):
            try:
                self._tmp.cleanup()
                return
            except (PermissionError, OSError):
                time.sleep(0.3)


class TestLockMutualExclusion(unittest.TestCase):
    """The root cause, tested directly at the lock primitive."""

    def test_second_acquire_is_refused_while_first_holds(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            first = rdj._acquire_lock(d)
            second = rdj._acquire_lock(d)
            self.assertIsNotNone(first)
            self.assertIsNone(second, "second caller stole a held lock -- H1 regression")

    def test_lock_is_stamped_before_any_slow_work(self):
        """The fix: the lock names its holder the instant it exists."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            rdj._acquire_lock(d)
            self.assertEqual((d / "lock").read_text(encoding="utf-8").strip(), str(os.getpid()))

    def test_empty_lock_is_never_stolen(self):
        """An unstamped lock means a claimer is mid-syscall. Fail closed."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "lock").write_text("", encoding="utf-8")
            self.assertIsNone(rdj._acquire_lock(d))

    def test_garbage_lock_is_never_stolen(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "lock").write_text("not-a-pid", encoding="utf-8")
            self.assertIsNone(rdj._acquire_lock(d))

    def test_lock_held_by_a_dead_pid_is_reclaimed(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "lock").write_text("999999", encoding="utf-8")
            self.assertIsNotNone(rdj._acquire_lock(d))
            self.assertEqual((d / "lock").read_text(encoding="utf-8").strip(), str(os.getpid()))

    def test_lock_held_by_a_live_pid_is_not_reclaimed(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "lock").write_text(str(os.getpid()), encoding="utf-8")
            self.assertIsNone(rdj._acquire_lock(d))

    def test_release_allows_a_subsequent_acquire(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            lock = rdj._acquire_lock(d)
            rdj._release(lock)
            self.assertIsNotNone(rdj._acquire_lock(d))


class TestConcurrentLaunches(unittest.TestCase):
    """Real threads racing real start() calls."""

    def test_simultaneous_starts_spawn_exactly_one_child(self):
        with _JobTemp() as jt:
            results, pids, barrier = [], [], threading.Barrier(4)

            def go():
                barrier.wait()
                results.append(rdj.start("racer", _SLEEPER, jt.root))

            threads = [threading.Thread(target=go) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=90)

            jt.track("racer")
            self.assertEqual(len(results), 4)
            self.assertEqual(results.count(0), 1, f"expected exactly one winner, got {results}")
            self.assertEqual(results.count(1), 3)

    def test_rapid_repeated_launches_never_double_start(self):
        with _JobTemp() as jt:
            codes = [rdj.start("rapid", _SLEEPER, jt.root) for _ in range(5)]
            jt.track("rapid")
            self.assertEqual(codes[0], 0)
            self.assertTrue(all(c == 1 for c in codes[1:]), f"a duplicate slipped through: {codes}")

    def test_duplicate_job_name_while_running_is_refused(self):
        with _JobTemp() as jt:
            self.assertEqual(rdj.start("dup", _SLEEPER, jt.root), 0)
            pid = jt.track("dup")
            self.assertIsNotNone(pid)
            self.assertEqual(rdj.start("dup", _SLEEPER, jt.root), 1)
            self.assertEqual(jt.pid_of("dup"), pid, "pid file was overwritten by a refused start")

    def test_independent_job_names_coexist(self):
        with _JobTemp() as jt:
            self.assertEqual(rdj.start("job_a", _SLEEPER, jt.root), 0)
            self.assertEqual(rdj.start("job_b", _SLEEPER, jt.root), 0)
            a, b = jt.track("job_a"), jt.track("job_b")
            self.assertIsNotNone(a)
            self.assertIsNotNone(b)
            self.assertNotEqual(a, b)
            self.assertEqual(rdj.liveness(a, None) == rdj.GONE, False)
            self.assertEqual(rdj.liveness(b, None) == rdj.GONE, False)

    def test_three_independent_jobs_coexist(self):
        """A recorder alongside two collectors."""
        with _JobTemp() as jt:
            for name in ("recorder", "collector_1", "collector_2"):
                self.assertEqual(rdj.start(name, _SLEEPER, jt.root), 0)
                jt.track(name)
            pids = {jt.pid_of(n) for n in ("recorder", "collector_1", "collector_2")}
            self.assertEqual(len(pids), 3)


class TestRestartAndStaleState(unittest.TestCase):
    def test_restart_after_normal_exit_is_allowed(self):
        with _JobTemp() as jt:
            self.assertEqual(rdj.start("quick", _QUICK, jt.root), 0)
            pid = jt.track("quick")
            self.assertTrue(_wait_gone(pid), "child did not exit")
            self.assertEqual(rdj.start("quick", _QUICK, jt.root), 0)
            jt.track("quick")

    def test_restart_after_abnormal_termination_is_allowed(self):
        with _JobTemp() as jt:
            self.assertEqual(rdj.start("crashy", _SLEEPER, jt.root), 0)
            pid = jt.track("crashy")
            _kill(pid)
            self.assertTrue(_wait_gone(pid), "kill did not take effect")
            self.assertEqual(rdj.start("crashy", _SLEEPER, jt.root), 0,
                             "could not restart after abnormal termination")
            jt.track("crashy")

    def test_stale_pid_from_a_dead_process_does_not_block(self):
        with _JobTemp() as jt:
            d = rdj.job_dir("stale", jt.root)
            d.mkdir(parents=True)
            (d / "pid").write_text("999999", encoding="utf-8")
            self.assertEqual(rdj.start("stale", _SLEEPER, jt.root), 0)
            jt.track("stale")

    def test_interrupted_launch_leaves_no_lock_behind(self):
        """If start() raises after acquiring, the lock must be released --
        otherwise the job is permanently unstartable."""
        with _JobTemp() as jt:
            real = rdj._start_locked
            rdj._start_locked = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
            try:
                with self.assertRaises(RuntimeError):
                    rdj.start("interrupted", _SLEEPER, jt.root)
            finally:
                rdj._start_locked = real
            self.assertFalse((rdj.job_dir("interrupted", jt.root) / "lock").exists(),
                             "orphaned lock would block every future start")
            self.assertEqual(rdj.start("interrupted", _SLEEPER, jt.root), 0)
            jt.track("interrupted")

    def test_refused_start_does_not_leave_an_orphan_lock(self):
        with _JobTemp() as jt:
            self.assertEqual(rdj.start("orphan", _SLEEPER, jt.root), 0)
            jt.track("orphan")
            self.assertEqual(rdj.start("orphan", _SLEEPER, jt.root), 1)
            lock = rdj.job_dir("orphan", jt.root) / "lock"
            self.assertTrue(lock.is_file())
            self.assertEqual(lock.read_text(encoding="utf-8").strip(),
                             str(jt.pid_of("orphan")),
                             "lock should still name the running child, not a launcher")


class TestNoFalseRunning(unittest.TestCase):
    def test_liveness_of_a_dead_pid_is_gone(self):
        self.assertEqual(rdj.liveness(999999, None), rdj.GONE)

    def test_recycled_pid_is_not_reported_as_the_job(self):
        """A live pid whose command line does not match the recorded cmd
        must never read as ALIVE_AND_MATCHES."""
        self.assertNotEqual(
            rdj.liveness(os.getpid(), ["definitely", "not", "this", "process"]),
            rdj.ALIVE_AND_MATCHES,
        )

    def test_running_child_matches_its_recorded_argv(self):
        with _JobTemp() as jt:
            self.assertEqual(rdj.start("identity", _SLEEPER, jt.root), 0)
            pid = jt.track("identity")
            argv = rdj._recorded_argv(rdj.job_dir("identity", jt.root))
            self.assertEqual(rdj.liveness(pid, argv), rdj.ALIVE_AND_MATCHES)


if __name__ == "__main__":
    unittest.main()
