"""CLI entry point for `pipeline.collect_liquidations()` (Constitution §5:
every long-running component exposes a CLI entry point so any scheduler
invokes the exact same executable; RD-13/PROJECT_STATE.md Backlog 1.3).

Retires the scratchpad-only driver the one-month pilot backfill used --
that script lived outside the repository, with machine-local absolute
paths, and was never runnable on Railway/Docker/a VPS.

Unlike research/campaign_0*/collect_backfill.py's own day/month-chunking
retry loop, THIS driver does not need to chunk the requested range itself:
collect_liquidations() already flushes decoded rows to disk once per
calendar day and advances a durable, key-ordered checkpoint every hour
(see pipeline.py's own DURABILITY docstring section), so a single call
over an arbitrarily long range is already safely interruptible and
resumable -- re-running this script after any failure, transient or not,
picks up exactly where the checkpoint left off and never re-downloads or
duplicates a row. The bounded retry below exists only to ride out a
single transient network blip without requiring a human to re-invoke the
script by hand.

Run:
    python -m alpha_engine.historical.backfill_liquidations \
        --start 2025-07-27 --end 2026-07-27
    python -m alpha_engine.historical.backfill_liquidations \
        --symbols BTC ETH --start 2026-06-01 --end 2026-06-30 \
        --storage-root data/alpha_engine_historical
"""

import argparse
import sys
import time
from datetime import date, datetime

from exchange_adapter import Symbol

from .errors import HistoricalDataError
from .pipeline import collect_liquidations
from .sources.hyperliquid_s3 import EARLIEST_MEASURED_DATE

_MAX_ATTEMPTS = 6
_DEFAULT_SYMBOLS = (Symbol("BTC"), Symbol("ETH"), Symbol("SOL"))
_DEFAULT_STORAGE_ROOT = "data/alpha_engine_historical"


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def _collect_with_retry(symbols, start, end, storage_root, force, checkpoint_path):
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return collect_liquidations(
                symbols, start, end, storage_root, force=force, checkpoint_path=checkpoint_path,
            )
        except HistoricalDataError as exc:
            if attempt == _MAX_ATTEMPTS:
                raise
            backoff = 2 ** attempt
            print(
                f"liquidations {start.isoformat()}..{end.isoformat()}: transient failure "
                f"(attempt {attempt}), retrying in {backoff}s: {exc}",
                flush=True,
            )
            time.sleep(backoff)


def run(
    symbols=_DEFAULT_SYMBOLS, start=None, end=None, storage_root=_DEFAULT_STORAGE_ROOT,
    force=False, checkpoint_path=None,
) -> int:
    if start is None or end is None:
        raise HistoricalDataError("start and end dates are required")
    try:
        results = _collect_with_retry(symbols, start, end, storage_root, force, checkpoint_path)
    except HistoricalDataError as exc:
        print(f"BACKFILL_FAILED after {_MAX_ATTEMPTS} attempts: {exc}", flush=True)
        return 1

    for result in results:
        print(
            f"{result.symbol_value}: hours_requested={result.periods_requested} "
            f"hours_fetched={result.periods_fetched} hours_skipped={result.periods_skipped} "
            f"days_unavailable={result.periods_unavailable} rows_added={result.rows_added}",
            flush=True,
        )
    print(
        f"BACKFILL_COMPLETE symbols={[s.value for s in symbols]} "
        f"range={start.isoformat()}..{end.isoformat()}",
        flush=True,
    )
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill Hyperliquid S3 liquidation history into the local historical store.",
    )
    parser.add_argument(
        "--symbols", nargs="+", default=[s.value for s in _DEFAULT_SYMBOLS],
        help="watchlist symbols to collect (default: BTC ETH SOL)",
    )
    parser.add_argument(
        "--start", type=_parse_date, required=True,
        help=f"start date, YYYY-MM-DD (archive begins {EARLIEST_MEASURED_DATE})",
    )
    parser.add_argument("--end", type=_parse_date, required=True, help="end date, YYYY-MM-DD, inclusive")
    parser.add_argument(
        "--storage-root", default=_DEFAULT_STORAGE_ROOT,
        help=f"historical data root (default: {_DEFAULT_STORAGE_ROOT})",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="ignore any existing checkpoint and reprocess the whole range "
             "(storage.merge_and_write is idempotent, so this cannot duplicate rows)",
    )
    parser.add_argument(
        "--checkpoint-path", default=None,
        help="override the checkpoint file location (default: <storage-root>/.liquidation_checkpoint.json)",
    )
    args = parser.parse_args(argv)
    symbols = tuple(Symbol(s) for s in args.symbols)
    return run(
        symbols=symbols, start=args.start, end=args.end, storage_root=args.storage_root,
        force=args.force, checkpoint_path=args.checkpoint_path,
    )


if __name__ == "__main__":
    sys.exit(main())
