"""Resumable, chunked Funding Rate backfill driver for Research Campaign 02.

Mirrors research/campaign_01_open_interest/collect_backfill.py's pattern
exactly, adapted for funding rate instead of open interest/mark price:
alpha_engine.historical.pipeline.collect_funding_rate() only writes once,
at the end of whatever date range it is given, so a long single-range call
that is interrupted persists NOTHING. This driver collects ONE MONTH AT A
TIME per symbol so every completed month persists atomically -- an
interruption at any point keeps every already-collected month, and simply
re-running resumes (collect_funding_rate's own incremental-month-skip for
Binance, and its high-water-mark resume for Hyperliquid, mean a re-run
never re-fetches what is already on disk).

Also mirrors campaign 01's retry-with-exponential-backoff for transient
network failures (the same WinError 10054 connection resets observed
during Campaign 01's backfill are equally possible here) and its
record-and-continue behavior: one stubborn month must not abort the whole
backfill.

Run:
    python -m research.campaign_02_funding_rate.collect_backfill BTC binance
    python -m research.campaign_02_funding_rate.collect_backfill BTC hyperliquid
"""

import sys
import time
from datetime import date

from exchange_adapter import Symbol

from alpha_engine.historical import collect_funding_rate
from alpha_engine.historical.errors import HistoricalDataError

_MAX_ATTEMPTS = 6
_SYMBOLS = (Symbol("BTC"), Symbol("ETH"), Symbol("SOL"))
_STORAGE_ROOT = "data/alpha_engine_historical"


def _month_bounds(year: int, month: int):
    start = date(year, month, 1)
    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date.fromordinal(date(year, month + 1, 1).toordinal() - 1)
    return start, end


def _months(start_year, start_month, end_year, end_month):
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def _collect_month_with_retry(symbol, source, s, e):
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return collect_funding_rate(symbol, s, e, _STORAGE_ROOT, source=source)
        except HistoricalDataError as exc:
            if attempt == _MAX_ATTEMPTS:
                raise
            backoff = 2 ** attempt
            print(f"{symbol.value}/{source} {s.isoformat()[:7]}: transient failure "
                  f"(attempt {attempt}), retrying in {backoff}s: {exc}", flush=True)
            time.sleep(backoff)


def run(symbols=_SYMBOLS, source="binance",
        start_year=2023, start_month=7, end_year=2024, end_month=12):
    failed_months = []
    for symbol in symbols:
        for y, m in _months(start_year, start_month, end_year, end_month):
            s, e = _month_bounds(y, m)
            try:
                result = _collect_month_with_retry(symbol, source, s, e)
            except HistoricalDataError as exc:
                failed_months.append(f"{symbol.value}/{source} {y}-{m:02d}")
                print(f"{symbol.value}/{source} {y}-{m:02d}: FAILED after {_MAX_ATTEMPTS} attempts: {exc}",
                      flush=True)
                continue
            print(
                f"{symbol.value}/{source} {y}-{m:02d}: fetched={result.periods_fetched} "
                f"skipped={result.periods_skipped} unavailable={result.periods_unavailable} "
                f"rows_added={result.rows_added}",
                flush=True,
            )
    if failed_months:
        print(f"BACKFILL_INCOMPLETE failed_months={failed_months}", flush=True)
    else:
        print(f"BACKFILL_COMPLETE source={source} symbols={[s.value for s in symbols]}", flush=True)


if __name__ == "__main__":
    syms = (Symbol(sys.argv[1]),) if len(sys.argv) > 1 else _SYMBOLS
    src = sys.argv[2] if len(sys.argv) > 2 else "binance"
    run(symbols=syms, source=src)
