"""Run a long-running collection job DETACHED from the calling shell, so
it survives the parent exiting.

WHY THIS EXISTS (measured, not theoretical): the Backlog 1.5 liquidation
backfill was launched as a child of an interactive session. When that
session ended, the job was torn down with it -- after 49 of 367 days, with
an EMPTY output file: no BACKFILL_COMPLETE, no BACKFILL_FAILED, no
traceback. Nothing was corrupted (the checkpoint's own durability
guarantees held perfectly, and re-running resumed exactly where it left
off), but ~9 hours of wall-clock transfer had to be re-run. The defect was
never in the pipeline -- it was that the job's LIFETIME was coupled to a
chat session's lifetime.

WHAT THIS CHANGES: nothing inside the collection pipeline. This is a
process-lifetime wrapper only. It does not touch storage, checkpoint
semantics, retry logic, or research logic -- it starts the exact same
`python -m <module> <args>` the operator would run by hand, and gets out
of the way. Resumability, idempotency and durability all continue to come
from the pipeline itself (`storage.merge_and_write` + the source module's
key-ordered checkpoint), NOT from anything here.

Platform independence (Constitution SS5): uses only stdlib `subprocess`
with a documented per-platform detach flag. This is the one place a
platform difference is unavoidable -- POSIX detaches via `start_new_session`,
Windows via CREATE_NEW_PROCESS_GROUP|DETACHED_PROCESS -- because the two
OSes genuinely have different process-group models. Both branches produce
the same observable result (a process whose lifetime is independent of
this one), and no business logic differs between them.

Usage:
    python scripts/run_detached_job.py --name liq_backfill -- \
        python -m alpha_engine.historical.backfill_liquidations \
            --symbols BTC ETH SOL --start 2025-07-27 --end 2026-07-28

    python scripts/job_status.py liq_backfill          # check on it
    python scripts/job_status.py liq_backfill --follow # tail its log

Writes, under <runtime-dir>/jobs/<name>/:
    pid       -- the detached process id
    cmd       -- the exact argv, so a later reader knows what is running
    started   -- ISO-8601 UTC start time
    log       -- combined stdout+stderr, append-only across restarts
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_RUNTIME_DIR = "data/runtime"


def job_dir(name: str, runtime_dir: str = _DEFAULT_RUNTIME_DIR) -> Path:
    return Path(runtime_dir) / "jobs" / name


def _detach_kwargs() -> dict:
    """Per-OS flags that make the child outlive this process.

    The ONLY platform-conditional code in this repository's business or
    operational path, and it is unavoidable: POSIX and Windows have
    different process-group models. Observable behaviour is identical.
    """
    if os.name == "nt":
        # DETACHED_PROCESS (0x8) -> no inherited console, so closing the
        # terminal cannot deliver CTRL_CLOSE_EVENT to the child.
        # CREATE_NEW_PROCESS_GROUP (0x200) -> Ctrl-C in the parent's
        # console is not broadcast to the child.
        return {"creationflags": 0x00000008 | 0x00000200}
    return {"start_new_session": True}


def start(name: str, argv, runtime_dir: str = _DEFAULT_RUNTIME_DIR) -> int:
    if not argv:
        raise SystemExit("no command given after `--`")
    d = job_dir(name, runtime_dir)
    d.mkdir(parents=True, exist_ok=True)

    pid_file = d / "pid"
    if pid_file.is_file():
        existing = pid_file.read_text(encoding="utf-8").strip()
        if existing.isdigit() and is_running(int(existing)):
            print(
                f"job {name!r} already running as pid {existing} -- refusing to start a second copy.\n"
                f"Use `python scripts/job_status.py {name}` to inspect it.",
                file=sys.stderr,
            )
            return 1

    log_path = d / "log"
    # Append, never truncate: a resumed run's output belongs with the
    # earlier attempts' output, so the whole history stays in one place.
    #
    # The parent CLOSES its own handle as soon as the child has inherited
    # one (the `with` block below). Holding it open would leak a
    # descriptor for the life of the parent and, on Windows, keep the file
    # locked against readers and cleanup -- the child keeps its own
    # inherited handle either way, so nothing is lost by letting go here.
    with open(log_path, "a", encoding="utf-8", buffering=1) as log:
        log.write(
            f"\n===== detached start {datetime.now(timezone.utc).isoformat()} ====="
            f"\n===== argv: {argv!r}\n"
        )
        log.flush()
        proc = subprocess.Popen(
            argv,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            cwd=os.getcwd(),
            **_detach_kwargs(),
        )

    pid_file.write_text(str(proc.pid), encoding="utf-8")
    (d / "cmd").write_text(json.dumps(argv), encoding="utf-8")
    (d / "started").write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")

    print(f"started job {name!r} as pid {proc.pid}, detached from this shell")
    print(f"  log:    {log_path}")
    print(f"  status: python scripts/job_status.py {name}")
    return 0


def is_running(pid: int) -> bool:
    """True if `pid` is a live process. Best-effort and never raises."""
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, timeout=15,
            )
            return str(pid) in out.stdout.decode("utf-8", "ignore")
        os.kill(pid, 0)  # signal 0 = existence check only
        return True
    except (OSError, subprocess.SubprocessError, ValueError):
        return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a command detached from this shell, so it survives the parent exiting.",
    )
    parser.add_argument("--name", required=True, help="short job name (directory key under <runtime>/jobs/)")
    parser.add_argument(
        "--runtime-dir", default=_DEFAULT_RUNTIME_DIR,
        help=f"where to keep pid/log/cmd state (default: {_DEFAULT_RUNTIME_DIR})",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER, help="-- followed by the command to run")
    args = parser.parse_args(argv)

    cmd = args.command
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    return start(args.name, cmd, args.runtime_dir)


if __name__ == "__main__":
    sys.exit(main())
