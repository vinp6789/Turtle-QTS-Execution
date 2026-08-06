"""Health check for the live recorder, from DURABLE ON-DISK STATE ONLY.

STRICTLY READ-ONLY -- never writes, never signals a process, never
touches collected data. Safe to run at any time, from any session, while
the recorder is mid-flight. Same discipline as
scripts/liquidation_backfill_progress.py.

Not a daemon and not a framework: one script, run it when you want an
answer, or from any scheduler. Exit code 0 = healthy, 1 = degraded, so it
composes with anything.

Detects every failure mode the deployment review called for:

  running but writing nothing  -> process ALIVE but newest row is older
                                  than --max-lag-minutes
  stale timestamps             -> same check, reported per series
  repeated unavailable readings-> counts `skipped` warnings in the log
  transport failures           -> counts RECORD_FAILED lines in the log.
                                  These are FAILED POLLS, not lost data:
                                  the recorder polls 4x per hourly slot, so
                                  a transient HTTP/DNS error costs nothing.
                                  Reported as a NOTE when the series are
                                  contiguous; escalated to a problem only
                                  when a gap/duplicate/staleness check also
                                  fires.
  disk write failures          -> surface as an unexpected process exit
                                  (merge_and_write raises; the loop dies)
                                  and are caught by the process check
  storage corruption           -> storage.load() raises; reported per file
  duplicate timestamps         -> duplicate (symbol, observed_at_utc) keys
  excessive gaps               -> consecutive rows more than
                                  --max-gap-hours apart
  unexpected process exit      -> pid GONE while the log has no clean
                                  RECORDER_STOPPED line

Usage:
    python scripts/recorder_health.py
    python scripts/recorder_health.py --name live_recorder --max-lag-minutes 90
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from run_detached_job import ALIVE_AND_MATCHES, GONE, _recorded_argv, job_dir, liveness  # noqa: E402

from exchange_adapter import Symbol  # noqa: E402

from alpha_engine.historical import storage  # noqa: E402
from alpha_engine.historical.models import (  # noqa: E402
    FundingRateObservation,
    MarkPriceObservation,
    OpenInterestObservation,
)

_SOURCE = "hyperliquid_live"
_SYMBOLS = ("BTC", "ETH", "SOL")
_METRICS = (
    ("open_interest", OpenInterestObservation),
    ("funding_rate", FundingRateObservation),
    ("mark_price", MarkPriceObservation),
)


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def check(name, runtime_dir, storage_root, max_lag_minutes, max_gap_hours, log_lines=400):
    """Returns (healthy: bool, lines: list[str])."""
    now = datetime.now(timezone.utc)
    out, problems = [], []

    # ---- process
    d = job_dir(name, runtime_dir)
    pid_file = d / "pid"
    log_file = d / "log"
    pid = None
    if pid_file.is_file():
        raw = pid_file.read_text(encoding="utf-8").strip()
        pid = int(raw) if raw.isdigit() else None
    if pid is None:
        out.append(f"process   : NO PID FILE at {pid_file}")
        problems.append("no pid file -- recorder was never started under this name")
    else:
        state = liveness(pid, _recorded_argv(d))
        out.append(f"process   : pid {pid} -- {state}")
        if state != ALIVE_AND_MATCHES:
            clean = False
            if log_file.is_file():
                clean = "RECORDER_STOPPED" in log_file.read_text(encoding="utf-8", errors="replace")[-4000:]
            if state == GONE and not clean:
                problems.append(f"UNEXPECTED PROCESS EXIT (pid {pid} gone, no clean RECORDER_STOPPED)")
            elif state == GONE:
                problems.append(f"recorder stopped cleanly (pid {pid} gone)")
            else:
                problems.append(f"process state {state} -- cannot confirm the recorder is running")

    # ---- log signals
    if log_file.is_file():
        tail = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-log_lines:]
        failed = sum(1 for line in tail if "RECORD_FAILED" in line)
        skipped = sum(1 for line in tail if "skipped" in line)
        recorded = sum(1 for line in tail if line.startswith("RECORDED"))
        out.append(f"log       : last {len(tail)} line(s): RECORDED={recorded} "
                   f"RECORD_FAILED={failed} skipped-warnings={skipped}")
        # A RECORD_FAILED is a FAILED POLL, not lost data. The recorder polls
        # four times per hourly slot precisely so one transport failure does
        # not cost that hour's sample (RD-18 section B). Whether data was
        # actually lost is decided by the gap/duplicate/staleness checks over
        # the series themselves, below -- so the count is held here and
        # classified after those run. Escalating on the count alone produces
        # a permanently-red monitor on self-healed transients, which is the
        # alert-fatigue failure mode the deployment review warned about.
        transport_failures = failed
        if skipped:
            problems.append(f"{skipped} skipped-field warning(s) -- repeated unavailable readings")
        if pid is not None and recorded == 0:
            problems.append("no RECORDED line in the log tail -- running but writing nothing")
    else:
        out.append(f"log       : (none at {log_file})")
        transport_failures = 0

    # ---- series
    root = Path(storage_root)
    out.append("")
    out.append(f"{'series':38} {'rows':>6} {'last observed':26} {'lag':>9} {'dups':>5} {'gaps':>5}")
    total_rows = 0
    for metric, obs_type in _METRICS:
        for sym in _SYMBOLS:
            path = root / storage.series_filename(metric, Symbol(sym), _SOURCE)
            label = f"{metric}/{sym}"
            if not path.is_file():
                out.append(f"{label:38} {'-':>6} {'(no file yet)':26}")
                problems.append(f"{label}: no file -- symbol never recorded")
                continue
            try:
                rows = storage.load(path, obs_type)
            except Exception as exc:  # noqa: BLE001 -- a corrupt series must not crash the check
                out.append(f"{label:38} {'ERR':>6} {type(exc).__name__}")
                problems.append(f"{label}: STORAGE CORRUPTION -- {type(exc).__name__}: {exc}")
                continue
            total_rows += len(rows)
            if not rows:
                out.append(f"{label:38} {0:>6} {'(empty)':26}")
                problems.append(f"{label}: file exists but is empty")
                continue
            times = sorted(_parse(r.observed_at_utc) for r in rows)
            keys = [(r.symbol.value, r.observed_at_utc) for r in rows]
            dups = len(keys) - len(set(keys))
            gaps = sum(1 for a, b in zip(times, times[1:])
                       if (b - a) > timedelta(hours=max_gap_hours))
            lag_min = (now - times[-1]).total_seconds() / 60
            out.append(f"{label:38} {len(rows):>6} {times[-1].isoformat()[:25]:26} "
                       f"{lag_min:>7.1f}m {dups:>5} {gaps:>5}")
            if dups:
                problems.append(f"{label}: {dups} DUPLICATE timestamp key(s)")
            if gaps:
                problems.append(f"{label}: {gaps} gap(s) longer than {max_gap_hours}h")
            if lag_min > max_lag_minutes:
                problems.append(f"{label}: STALE -- newest row is {lag_min:.0f} min old "
                                f"(limit {max_lag_minutes})")
    out.append("")
    out.append(f"total rows across all live series: {total_rows:,}")

    # Classify the transport failures now that the data itself has been
    # checked. Failures alongside a real data defect are corroborating
    # evidence and escalate; failures with intact, contiguous series are
    # the retry design working as intended.
    notes = []
    if transport_failures:
        if problems:
            problems.append(
                f"{transport_failures} RECORD_FAILED line(s) alongside the data "
                f"defect(s) above -- transport failure cost real samples")
        else:
            notes.append(
                f"{transport_failures} RECORD_FAILED line(s) -- transport failures "
                f"(HTTP/DNS), absorbed by the 4-polls-per-slot design: no gap, no "
                f"duplicate, no stale series. Informational, not degradation.")

    out.append("")
    if problems:
        out.append("VERDICT: DEGRADED")
        for p in problems:
            out.append(f"  - {p}")
    elif notes:
        out.append("VERDICT: HEALTHY (with notes)")
        for n in notes:
            out.append(f"  - {n}")
    else:
        out.append("VERDICT: HEALTHY")
    return (not problems), out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only health check for the live recorder (exit 0 healthy, 1 degraded).",
    )
    parser.add_argument("--name", default="live_recorder")
    parser.add_argument("--runtime-dir", default="data/runtime")
    parser.add_argument("--storage-root", default="data/alpha_engine_historical")
    parser.add_argument("--max-lag-minutes", type=float, default=90.0,
                        help="newest row older than this is stale (default 90 = one missed hourly slot)")
    parser.add_argument("--max-gap-hours", type=float, default=2.0)
    args = parser.parse_args(argv)
    healthy, lines = check(args.name, args.runtime_dir, args.storage_root,
                           args.max_lag_minutes, args.max_gap_hours)
    print("\n".join(lines))
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
