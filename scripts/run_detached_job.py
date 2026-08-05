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


def _recorded_argv(d: Path):
    """The argv recorded for this job's last start, or None."""
    try:
        return json.loads((d / "cmd").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _claim(lock_path: Path) -> Path:
    """Create the lock and stamp it with THIS process's pid in one step.

    O_CREAT|O_EXCL guarantees exactly one caller creates the file; writing
    the pid immediately means every other caller either loses the create
    or reads an identifiable holder. Raises FileExistsError if the lock
    already exists (the caller decides whether it may be reclaimed)."""
    fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, str(os.getpid()).encode("utf-8"))
    finally:
        os.close(fd)
    return lock_path


def _acquire_lock(d: Path):
    """Atomically claim the right to start this job, or return None.

    Closes the check-then-start race: the guard below reads the pid file
    and only writes the new pid AFTER the child is spawned, so without
    this two near-simultaneous invocations (two shells, two Claude
    sessions) could both pass the guard. O_CREAT|O_EXCL makes claiming
    the lock a single atomic step that exactly one caller can win.

    A lock left behind by a job that has since exited is reclaimed, but
    ONLY when its holder is provably gone -- never when liveness is
    merely undeterminable.

    The lock is STAMPED WITH THE CLAIMING PROCESS'S OWN PID as part of
    creating it. That is what makes the exclusion real: the original
    implementation created the lock empty and only stamped it with the
    child's pid after the liveness probe and Popen had finished, so for
    the whole of that window (measured at 0.25s to ~35s) a second caller
    read an empty lock, could not identify a holder, and stole it -- both
    callers then spawned a child. Stamping happens before any slow work,
    so the only unstamped window is between one os.open and one os.write.
    """
    lock_path = d / "lock"
    try:
        return _claim(lock_path)
    except FileExistsError:
        pass
    except OSError:
        return None

    holder_raw = ""
    try:
        holder_raw = lock_path.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    if not holder_raw.isdigit():
        # An unstamped lock means another caller created it microseconds
        # ago and has not yet written its pid. Fail CLOSED -- stealing
        # here is exactly the defect described above. (A lock left empty
        # by a process killed inside that one-syscall window has to be
        # removed by hand; the message in start() says so.)
        return None
    holder_pid = int(holder_raw)
    if liveness(holder_pid, _recorded_argv(d)) != GONE:
        return None  # a live (or unverifiable) holder -- do not steal the lock
    try:
        lock_path.unlink()
        return _claim(lock_path)
    except OSError:
        return None


def start(name: str, argv, runtime_dir: str = _DEFAULT_RUNTIME_DIR) -> int:
    if not argv:
        raise SystemExit("no command given after `--`")
    d = job_dir(name, runtime_dir)
    d.mkdir(parents=True, exist_ok=True)

    lock_path = _acquire_lock(d)
    if lock_path is None:
        print(
            f"job {name!r}: another start is in progress, or a previous run still holds the lock "
            f"and its state could not be confirmed -- refusing to start.\n"
            f"Use `python scripts/job_status.py {name}` to inspect it.",
            file=sys.stderr,
        )
        return 1

    try:
        return _start_locked(name, argv, d, lock_path)
    except BaseException:
        _release(lock_path)
        raise


def _release(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except OSError:
        pass


def _start_locked(name: str, argv, d: Path, lock_path: Path) -> int:
    pid_file = d / "pid"
    if pid_file.is_file():
        existing = pid_file.read_text(encoding="utf-8").strip()
        if existing.isdigit():
            state = liveness(int(existing), _recorded_argv(d))
            if state == ALIVE_AND_MATCHES:
                _release(lock_path)
                print(
                    f"job {name!r} already running as pid {existing} -- refusing to start a second copy.\n"
                    f"Use `python scripts/job_status.py {name}` to inspect it.",
                    file=sys.stderr,
                )
                return 1
            if state == UNKNOWN:
                # Cannot confirm the recorded pid is gone. Starting anyway
                # could put two collectors on the same CSVs, so refuse.
                _release(lock_path)
                print(
                    f"job {name!r}: could not determine whether pid {existing} is still running "
                    f"(process probe failed) -- refusing to start rather than risk a second "
                    f"concurrent copy writing the same data.\n"
                    f"Re-run once the machine is responsive, or confirm by hand and remove\n"
                    f"  {pid_file}\n"
                    f"if that pid is definitely gone.",
                    file=sys.stderr,
                )
                return 1
            # GONE or RECYCLED -> the recorded job is not running; safe to start.

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

    # cmd BEFORE pid: the identity check reads `cmd` to decide whether a
    # live pid really is this job, so it must never see a new pid paired
    # with the previous run's argv.
    (d / "cmd").write_text(json.dumps(argv), encoding="utf-8")
    (d / "started").write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    pid_file.write_text(str(proc.pid), encoding="utf-8")
    # The lock now names its holder, so a later start() can tell a live
    # holder from one left behind by a job that has since exited.
    lock_path.write_text(str(proc.pid), encoding="utf-8")

    print(f"started job {name!r} as pid {proc.pid}, detached from this shell")
    print(f"  log:    {log_path}")
    print(f"  status: python scripts/job_status.py {name}")
    return 0


def is_running(pid: int) -> bool:
    """True if `pid` is a live process, False if not or if UNDETERMINABLE.

    DISPLAY-ONLY. `job_status.py` uses this to render RUNNING / NOT
    RUNNING, where guessing "not running" on a probe failure is harmless.

    **Never use this to decide whether it is safe to start a job.** It
    cannot distinguish "definitely dead" from "could not tell", and it
    does not check process IDENTITY -- a recycled pid belonging to an
    unrelated process reads as alive. `liveness()` below answers both of
    those questions properly; `start()` uses it, not this.
    """
    return _probe_alive(pid) is True


def _probe_alive(pid: int):
    """Tri-state liveness: True (alive), False (definitely gone), None
    (could not determine -- the probe itself failed)."""
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, timeout=15,
            )
            text = out.stdout.decode("utf-8", "ignore")
            if "No tasks are running" in text:
                return False
            # Match the pid as its own whitespace-delimited column, not as a
            # bare substring -- a memory figure like "14,356 K" must not be
            # mistaken for the pid.
            for line in text.splitlines():
                fields = line.split()
                if len(fields) >= 2 and fields[1] == str(pid):
                    return True
            return False
        os.kill(pid, 0)  # signal 0 = existence check only
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Exists but owned by another user -- definitively alive.
        return True
    except (OSError, subprocess.SubprocessError, ValueError):
        return None  # probe failed; caller must NOT assume "dead"


def _command_line(pid: int):
    """The live process's full command line, or None if undeterminable."""
    try:
        if os.name == "nt":
            out = subprocess.run(
                ["wmic", "process", "where", f"ProcessId={pid}", "get", "CommandLine", "/format:list"],
                capture_output=True, timeout=20,
            )
            text = out.stdout.decode("utf-8", "ignore")
            if "CommandLine=" not in text:
                return None
            value = text.split("CommandLine=", 1)[1].strip()
            return value or None
        proc_cmdline = Path("/proc") / str(pid) / "cmdline"
        if proc_cmdline.is_file():
            raw = proc_cmdline.read_bytes().replace(b"\0", b" ").decode("utf-8", "ignore").strip()
            return raw or None
        out = subprocess.run(
            ["ps", "-p", str(pid), "-o", "args="], capture_output=True, timeout=20,
        )
        value = out.stdout.decode("utf-8", "ignore").strip()
        return value or None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


# liveness() outcomes
ALIVE_AND_MATCHES = "alive_and_matches"     # this pid IS the recorded job -> refuse to start
GONE = "gone"                               # definitively not running -> safe to start
RECYCLED = "recycled"                       # pid alive but is a DIFFERENT process -> safe to start
UNKNOWN = "unknown"                         # could not determine -> refuse to start (fail closed)


def liveness(pid: int, expected_argv=None) -> str:
    """Is `pid` still the job we recorded? Tri-state plus identity.

    WHY THIS IS SEPARATE FROM is_running(): `start()`'s duplicate guard
    protects against the one genuinely dangerous mistake in this workflow
    -- two collection jobs writing the same CSVs at once, which
    `storage.merge_and_write` (read-modify-write, no inter-process lock)
    would turn into a silent lost update. A guard for that must fail
    CLOSED: if we cannot tell whether the job is alive, we must refuse to
    start, never assume it is safe. It must also verify IDENTITY, because
    an OS-recycled pid belonging to an unrelated process would otherwise
    read as "the job is still running" forever.
    """
    alive = _probe_alive(pid)
    if alive is None:
        return UNKNOWN
    if alive is False:
        return GONE
    if not expected_argv:
        # Alive, but we have nothing to compare against -- cannot rule out
        # a recycled pid, so do not claim a match. Fail closed.
        return UNKNOWN
    actual = _command_line(pid)
    if actual is None:
        # Alive but identity unverifiable -- fail closed rather than risk
        # a duplicate collection run.
        return UNKNOWN
    # Skip argv[0] (the interpreter): it may be recorded as a bare name
    # but reported as an absolute path, or vice versa.
    tokens = [t for t in list(expected_argv)[1:] if t]
    if tokens and all(token in actual for token in tokens):
        return ALIVE_AND_MATCHES
    return RECYCLED


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
