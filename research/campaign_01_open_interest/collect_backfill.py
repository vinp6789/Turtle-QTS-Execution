"""Resumable, chunked backfill driver for Research Campaign 01.

collect_metrics() writes its whole range in one atomic merge at the end,
so a long single call that is interrupted persists NOTHING. This driver
collects ONE MONTH AT A TIME per symbol — each month is a separate
collect_metrics call that writes on completion — so an interruption at any
point keeps every already-collected month, and simply re-running resumes
(incremental collection skips days already on disk).

Run: python -m research.campaign_01_open_interest.collect_backfill
Progress is printed (and flushed) per month so it can be monitored live.
"""

import sys
import time
from datetime import date

from exchange_adapter import Symbol

from alpha_engine.historical import collect_metrics
from alpha_engine.historical.errors import HistoricalDataError

_MAX_ATTEMPTS = 6  # transient network resets (WinError 10054) are common on long backfills

_SYMBOLS = (Symbol("BTC"), Symbol("ETH"), Symbol("SOL"))
_STORAGE_ROOT = "data/alpha_engine_historical"


def _month_bounds(year: int, month: int):
    start = date(year, month, 1)
    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 1, 1).toordinal() - 1
        end = date.fromordinal(end)
    return start, end


def _months(start_year, start_month, end_year, end_month):
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def _collect_month_with_retry(symbol, s, e):
    """Collect one month, retrying transient network failures with
    exponential backoff. A month is retried whole (collect_metrics writes
    only at end, so a failed month persisted nothing; incremental skip
    means any days a PRIOR successful run wrote are not re-downloaded).
    Returns (oi_res, mark_res) or raises after _MAX_ATTEMPTS."""
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return collect_metrics(symbol, s, e, _STORAGE_ROOT)
        except HistoricalDataError as exc:
            if attempt == _MAX_ATTEMPTS:
                raise
            backoff = 2 ** attempt
            print(f"{symbol.value} {s.isoformat()[:7]}: transient failure (attempt {attempt}), "
                  f"retrying in {backoff}s: {exc}", flush=True)
            time.sleep(backoff)


def run(symbols=_SYMBOLS, start_year=2023, start_month=7, end_year=2024, end_month=12):
    failed_months = []
    for symbol in symbols:
        for y, m in _months(start_year, start_month, end_year, end_month):
            s, e = _month_bounds(y, m)
            try:
                oi_res, mark_res = _collect_month_with_retry(symbol, s, e)
            except HistoricalDataError as exc:
                # One stubborn month must not abort the whole backfill; record
                # and continue (a re-run resumes it incrementally).
                failed_months.append(f"{symbol.value} {y}-{m:02d}")
                print(f"{symbol.value} {y}-{m:02d}: FAILED after {_MAX_ATTEMPTS} attempts: {exc}", flush=True)
                continue
            print(
                f"{symbol.value} {y}-{m:02d}: fetched={oi_res.periods_fetched} "
                f"skipped={oi_res.periods_skipped} unavailable={oi_res.periods_unavailable} "
                f"oi_added={oi_res.rows_added} mark_added={mark_res.rows_added}",
                flush=True,
            )
    if failed_months:
        print(f"BACKFILL_INCOMPLETE failed_months={failed_months}", flush=True)
    else:
        print(f"BACKFILL_COMPLETE {[s.value for s in symbols]}", flush=True)


if __name__ == "__main__":
    # Optional single-symbol arg for concurrent per-symbol runs (each writes
    # a distinct file, so concurrent symbols never race on the same CSV).
    syms = (Symbol(sys.argv[1]),) if len(sys.argv) > 1 else _SYMBOLS
    run(symbols=syms)
