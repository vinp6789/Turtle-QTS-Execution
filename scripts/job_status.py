"""Inspect (or follow) a job started by scripts/run_detached_job.py.

This is the "reattach" path. A detached job has no controlling terminal by
design, so you never reattach to the PROCESS -- you reattach to its
observable state: its pid, its append-only log, and, for collection jobs,
the pipeline's own durable checkpoint. All three survive the chat session,
the terminal, the browser, and a reboot.

Deliberately READ-ONLY. It never writes to the job, never signals it, and
never touches collected data or checkpoints -- so running it can never
disturb a job in flight, and it is safe to run from any number of parallel
sessions at once.

Usage:
    python scripts/job_status.py                     # list all known jobs
    python scripts/job_status.py liq_backfill        # one job's status
    python scripts/job_status.py liq_backfill --follow
    python scripts/job_status.py liq_backfill --lines 50
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_detached_job import _DEFAULT_RUNTIME_DIR, is_running, job_dir  # noqa: E402


def _read(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return default


def describe(name: str, runtime_dir: str, lines: int) -> int:
    d = job_dir(name, runtime_dir)
    if not d.is_dir():
        print(f"no such job: {name!r} (looked in {d})", file=sys.stderr)
        return 1

    pid_raw = _read(d / "pid")
    pid = int(pid_raw) if pid_raw.isdigit() else -1
    alive = is_running(pid)

    print(f"job:     {name}")
    print(f"pid:     {pid_raw or '(unknown)'}  -- {'RUNNING' if alive else 'NOT RUNNING'}")
    print(f"started: {_read(d / 'started') or '(unknown)'}")
    cmd_raw = _read(d / "cmd")
    if cmd_raw:
        try:
            print(f"cmd:     {' '.join(json.loads(cmd_raw))}")
        except ValueError:
            print(f"cmd:     {cmd_raw}")

    log_path = d / "log"
    if log_path.is_file():
        print(f"log:     {log_path}")
        tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        shown = [ln for ln in tail if ln.strip()][-lines:]
        if shown:
            print(f"--- last {len(shown)} non-empty log line(s) ---")
            for ln in shown:
                print(f"  {ln}")
        else:
            print("  (log is empty -- for a collection job this is normal until it finishes,")
            print("   since the CLI reports only at the end; use the checkpoint for progress)")

    if not alive:
        print()
        print("NOT RUNNING. If no completion line appears above, it was interrupted rather")
        print("than finished. Re-running the SAME command resumes from the last durable")
        print("checkpoint -- never restart from scratch and never pass --force to recover.")
    return 0


def follow(name: str, runtime_dir: str) -> int:
    d = job_dir(name, runtime_dir)
    log_path = d / "log"
    if not log_path.is_file():
        print(f"no log yet for job {name!r}", file=sys.stderr)
        return 1
    print(f"following {log_path} (Ctrl-C to stop; this does NOT affect the job)")
    with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
        handle.seek(0, 2)
        while True:
            line = handle.readline()
            if line:
                print(line.rstrip())
                continue
            pid_raw = _read(d / "pid")
            if not (pid_raw.isdigit() and is_running(int(pid_raw))):
                print("(job is no longer running)")
                return 0
            time.sleep(2)


def list_jobs(runtime_dir: str) -> int:
    root = Path(runtime_dir) / "jobs"
    if not root.is_dir():
        print(f"no jobs directory yet ({root})")
        return 0
    names = sorted(p.name for p in root.iterdir() if p.is_dir())
    if not names:
        print("no jobs recorded")
        return 0
    for name in names:
        pid_raw = _read(job_dir(name, runtime_dir) / "pid")
        alive = pid_raw.isdigit() and is_running(int(pid_raw))
        print(f"  {name:24s} pid={pid_raw or '?':>8}  {'RUNNING' if alive else 'not running'}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Inspect a detached job's status and log (read-only).")
    parser.add_argument("name", nargs="?", help="job name; omit to list all jobs")
    parser.add_argument("--runtime-dir", default=_DEFAULT_RUNTIME_DIR)
    parser.add_argument("--follow", action="store_true", help="stream new log lines until the job exits")
    parser.add_argument("--lines", type=int, default=20, help="how many trailing log lines to show (default 20)")
    args = parser.parse_args(argv)

    if not args.name:
        return list_jobs(args.runtime_dir)
    if args.follow:
        return follow(args.name, args.runtime_dir)
    return describe(args.name, args.runtime_dir, args.lines)


if __name__ == "__main__":
    sys.exit(main())
