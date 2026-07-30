"""Report liquidation-backfill progress from DURABLE ON-DISK STATE ONLY.

Answers "how far along is the backfill, and is the data sane?" without
attaching to any process, without the chat's background monitor, and
without the job having to still be running. Everything it reads
(checkpoint + collected CSVs) survives a chat disconnect, a terminal
close, and a reboot -- so progress is always recoverable from any new
session.

Deliberately READ-ONLY: it never writes, never signals a process, and
never touches collected data or checkpoints. Safe to run at any time,
including while a backfill is mid-flight, and from several sessions at
once.

It reads the SAME checkpoint the pipeline itself writes; it does not
reimplement or reinterpret checkpoint semantics. `--expected-start` /
`--expected-end` are display-only hints for the completion percentage --
they never influence what the collector does.

Usage:
    python scripts/liquidation_backfill_progress.py
    python scripts/liquidation_backfill_progress.py --expected-end 2026-07-28
"""

import argparse
import csv
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

_DEFAULT_ROOT = "data/alpha_engine_historical"
_CHECKPOINT_NAME = ".liquidation_checkpoint.json"
_SYMBOLS = ("BTC", "ETH", "SOL")


def _parse_iso(value: str) -> date:
    return date.fromisoformat(value)


def _contiguous_runs(days):
    if not days:
        return []
    days = sorted(days)
    runs, current = [], [days[0]]
    for prev, nxt in zip(days, days[1:]):
        if (nxt - prev).days == 1:
            current.append(nxt)
        else:
            runs.append((current[0], current[-1], len(current)))
            current = [nxt]
    runs.append((current[0], current[-1], len(current)))
    return runs


def report(root: str, expected_start: date, expected_end: date) -> int:
    root_path = Path(root)

    cp_path = root_path / _CHECKPOINT_NAME
    if cp_path.is_file():
        import json
        try:
            key = json.loads(cp_path.read_text(encoding="utf-8")).get("last_processed_key", "")
        except ValueError:
            key = "(unreadable)"
        print(f"checkpoint: {key}")
        digits = "".join(ch for ch in key.split("/")[-2] if ch.isdigit()) if "/" in key else ""
        if len(digits) == 8:
            cp_day = date(int(digits[:4]), int(digits[4:6]), int(digits[6:]))
            total = (expected_end - expected_start).days + 1
            # Clamp the count as well as the percentage: a checkpoint
            # outside the expected window (e.g. a narrower --expected-start
            # than the run actually used) otherwise prints a negative or
            # over-total day count next to a correctly-clamped percentage.
            done = max(0, min(total, (cp_day - expected_start).days + 1))
            pct = (done / total * 100) if total > 0 else 0.0
            print(f"            last completed day = {cp_day}  ({done}/{total} days, {pct:.1f}%)")
            if not (expected_start <= cp_day <= expected_end):
                print(f"            NOTE: checkpoint is outside the expected window "
                      f"{expected_start}..{expected_end} -- counts are clamped for display")
            if cp_day < expected_end:
                print(f"            next day to fetch  = {cp_day + timedelta(days=1)}")
            else:
                print("            checkpoint has reached the requested end date")
    else:
        print(f"checkpoint: (none at {cp_path}) -- backfill has not started, or uses a different path")

    print()
    grand_rows = 0
    for symbol in _SYMBOLS:
        path = root_path / f"liquidation__{symbol}__hyperliquid_s3.csv"
        if not path.is_file():
            print(f"{symbol}: (no file yet)")
            continue
        days, tids, rows, sides = set(), set(), 0, Counter()
        with open(path, "r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                rows += 1
                days.add(row["observed_at_utc"][:10])
                tids.add(row["tid"])
                sides[row["side"]] += 1
        grand_rows += rows
        as_dates = {date.fromisoformat(d) for d in days}
        ratio = rows / len(tids) if tids else 0.0
        size_mb = path.stat().st_size / (1024 * 1024)
        print(f"{symbol}: rows={rows:,}  events={len(tids):,}  rows/event={ratio:.2f}  "
              f"days={len(days)}  {size_mb:,.1f} MB")
        if abs(ratio - 2.0) > 1e-9:
            print(f"    WARNING: rows/event is {ratio:.4f}, expected exactly 2.00 "
                  f"(one liquidation = two paired fills sharing a tid)")
        # Both sides must be PRESENT and equal. Checking only the counts
        # that happen to appear would silently pass a wholly one-sided
        # series (e.g. every "A" row lost), since a single distinct count
        # is trivially "balanced".
        if rows and (set(sides) != {"A", "B"} or len(set(sides.values())) > 1):
            print(f"    WARNING: side counts are not a balanced A/B pair: {dict(sides)}")
        for start, end, count in _contiguous_runs(as_dates):
            print(f"    {start} .. {end}  ({count} days)")

    print()
    print(f"total rows across symbols: {grand_rows:,}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Report liquidation-backfill progress from durable on-disk state (read-only).",
    )
    parser.add_argument("--root", default=_DEFAULT_ROOT)
    parser.add_argument("--expected-start", type=_parse_iso, default=date(2025, 7, 27),
                        help="display-only, for the %% complete figure (default: archive start 2025-07-27)")
    parser.add_argument("--expected-end", type=_parse_iso, default=date(2026, 7, 28),
                        help="display-only, for the %% complete figure")
    args = parser.parse_args(argv)
    return report(args.root, args.expected_start, args.expected_end)


if __name__ == "__main__":
    sys.exit(main())
