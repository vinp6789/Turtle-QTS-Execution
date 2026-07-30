"""Resumable, chunked deep-history backfill driver (Backlog 2.1).

Extends funding-rate and OI/mark-price coverage back to the earliest
dates confirmed available on Binance's public archive, per
docs/ROADMAP.md Section 1.2:

    funding rate -> 2020-01 (BTC/ETH), 2020-09 (SOL)
    OI + mark-price metrics -> 2021-01 (BTC), 2022-01 (ETH/SOL)

Per-symbol start dates are asymmetric BY DESIGN (SOL's Binance futures
listing postdates BTC/ETH; see docs/ROADMAP.md Section 1.2) -- this
driver does not choose or adjust them. Any campaign that later uses this
deep window must declare, as `known_limitations` under RD-11 A:
survivorship bias, non-stationarity, and the asymmetric-start
compositional break -- this driver only collects the data; it does not
decide how it may be used.

This is orthogonal to Campaign 06 (the liquidation campaign) and does
not gate it -- it gates only the next funding/OI campaign
(docs/ROADMAP.md Section 1.2).

Mirrors research/campaign_01_open_interest/collect_backfill.py and
research/campaign_02_funding_rate/collect_backfill.py exactly:
collect_funding_rate() and collect_metrics() each write their whole
requested range in one atomic merge, so a long single-range call that is
interrupted persists NOTHING. This driver collects ONE MONTH AT A TIME
per symbol so every completed month persists atomically -- an
interruption at any point keeps every already-collected month, and
simply re-running resumes. Running across months already on disk (e.g.
2023-07 onward) is intentional, not wasted work: both collectors skip
any month/day already covered, so this driver can be re-run over the
full range at any time without re-downloading existing coverage.

Run:
    python -m research.deep_history_backfill.collect_backfill
    python -m research.deep_history_backfill.collect_backfill funding
    python -m research.deep_history_backfill.collect_backfill metrics
"""

import sys
import time
from datetime import date

from exchange_adapter import Symbol

from alpha_engine.historical import collect_funding_rate, collect_metrics
from alpha_engine.historical.errors import HistoricalDataError

_MAX_ATTEMPTS = 6  # transient network resets (WinError 10054) are common on long backfills
_STORAGE_ROOT = "data/alpha_engine_historical"

# docs/ROADMAP.md Section 1.2 -- do not adjust without a corresponding ROADMAP update.
_FUNDING_DEEP_START = {"BTC": (2020, 1), "ETH": (2020, 1), "SOL": (2020, 9)}
_METRICS_DEEP_START = {"BTC": (2021, 1), "ETH": (2022, 1), "SOL": (2022, 1)}
_END_YEAR, _END_MONTH = 2026, 7  # current month; both collectors report unavailable, not error, on partial months


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


def _collect_funding_month_with_retry(symbol, s, e):
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return collect_funding_rate(symbol, s, e, _STORAGE_ROOT, source="binance")
        except HistoricalDataError as exc:
            if attempt == _MAX_ATTEMPTS:
                raise
            backoff = 2 ** attempt
            print(f"funding {symbol.value} {s.isoformat()[:7]}: transient failure "
                  f"(attempt {attempt}), retrying in {backoff}s: {exc}", flush=True)
            time.sleep(backoff)


def _collect_metrics_month_with_retry(symbol, s, e):
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return collect_metrics(symbol, s, e, _STORAGE_ROOT)
        except HistoricalDataError as exc:
            if attempt == _MAX_ATTEMPTS:
                raise
            backoff = 2 ** attempt
            print(f"metrics {symbol.value} {s.isoformat()[:7]}: transient failure "
                  f"(attempt {attempt}), retrying in {backoff}s: {exc}", flush=True)
            time.sleep(backoff)


def run(target: str = "all") -> None:
    if target not in ("all", "funding", "metrics"):
        raise ValueError(f"target must be 'all', 'funding', or 'metrics', got {target!r}")

    failed = []

    if target in ("all", "funding"):
        for symbol_name, (start_year, start_month) in _FUNDING_DEEP_START.items():
            symbol = Symbol(symbol_name)
            for year, month in _months(start_year, start_month, _END_YEAR, _END_MONTH):
                s, e = _month_bounds(year, month)
                try:
                    result = _collect_funding_month_with_retry(symbol, s, e)
                except HistoricalDataError as exc:
                    failed.append(f"funding/{symbol.value} {year}-{month:02d}")
                    print(f"funding {symbol.value} {year}-{month:02d}: FAILED after "
                          f"{_MAX_ATTEMPTS} attempts: {exc}", flush=True)
                    continue
                print(f"funding {symbol.value} {year}-{month:02d}: fetched={result.periods_fetched} "
                      f"skipped={result.periods_skipped} unavailable={result.periods_unavailable} "
                      f"rows_added={result.rows_added}", flush=True)

    if target in ("all", "metrics"):
        for symbol_name, (start_year, start_month) in _METRICS_DEEP_START.items():
            symbol = Symbol(symbol_name)
            for year, month in _months(start_year, start_month, _END_YEAR, _END_MONTH):
                s, e = _month_bounds(year, month)
                try:
                    oi_res, mark_res = _collect_metrics_month_with_retry(symbol, s, e)
                except HistoricalDataError as exc:
                    failed.append(f"metrics/{symbol.value} {year}-{month:02d}")
                    print(f"metrics {symbol.value} {year}-{month:02d}: FAILED after "
                          f"{_MAX_ATTEMPTS} attempts: {exc}", flush=True)
                    continue
                print(f"metrics {symbol.value} {year}-{month:02d}: fetched={oi_res.periods_fetched} "
                      f"skipped={oi_res.periods_skipped} unavailable={oi_res.periods_unavailable} "
                      f"oi_added={oi_res.rows_added} mark_added={mark_res.rows_added}", flush=True)

    if failed:
        print(f"BACKFILL_INCOMPLETE failed={failed}", flush=True)
    else:
        print(f"BACKFILL_COMPLETE target={target}", flush=True)


if __name__ == "__main__":
    run(target=sys.argv[1] if len(sys.argv) > 1 else "all")
