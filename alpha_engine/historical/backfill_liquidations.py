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
transient network outage without requiring a human to re-invoke the
script by hand -- it is a convenience, never a correctness mechanism.

Retry behaviour is configurable (see RetryPolicy and the --retry-*
flags) and bounded by BOTH an attempt count and a budget on time spent
BACKING OFF (not total runtime), so a deterministic failure -- which
surfaces as the same HistoricalDataError a network blip does -- can
never loop forever. Both bounds reset when the checkpoint advances,
since a failure after real progress is a fresh outage rather than a
stuck loop.

Run:
    python -m alpha_engine.historical.backfill_liquidations \
        --start 2025-07-27 --end 2026-07-27
    python -m alpha_engine.historical.backfill_liquidations \
        --symbols BTC ETH --start 2026-06-01 --end 2026-06-30 \
        --storage-root data/alpha_engine_historical
    python -m alpha_engine.historical.backfill_liquidations \
        --start 2025-07-27 --end 2026-07-27 \
        --retry-max-total-seconds 1800   # ride out a 30-minute outage
"""

import argparse
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from exchange_adapter import Symbol

from .errors import HistoricalDataError
from .pipeline import collect_liquidations
from .sources.hyperliquid_s3 import EARLIEST_MEASURED_DATE, read_checkpoint

# Retry defaults. The original hard-coded policy (6 attempts, uncapped
# 2**attempt backoff) spent a total of ~62s before giving up, which is
# shorter than the multi-minute connectivity outages observed in
# practice -- every real interruption of the Backlog 1.5 backfill to
# date has been transient (18 occurrences, all "Read timeout on endpoint
# URL" / "Could not connect to the endpoint URL"; zero deterministic
# failures), and each one required a human to re-invoke the script.
# These defaults ride out roughly 12 minutes of continuous outage.
#
# The backoff is CAPPED (unlike the original) so that adding attempts
# does not produce absurd single sleeps -- 12 uncapped attempts would
# end in a ~68-minute sleep. The separate total-time budget is what
# actually bounds the wait; attempts alone are a poor bound once the
# backoff is capped.
_DEFAULT_MAX_ATTEMPTS = 12
_DEFAULT_BACKOFF_BASE_SECONDS = 2.0
_DEFAULT_MAX_BACKOFF_SECONDS = 120.0
_DEFAULT_MAX_TOTAL_SECONDS = 900.0

_DEFAULT_SYMBOLS = (Symbol("BTC"), Symbol("ETH"), Symbol("SOL"))
_DEFAULT_STORAGE_ROOT = "data/alpha_engine_historical"


@dataclass(frozen=True)
class RetryPolicy:
    """How long to keep retrying a TRANSIENT collection failure.

    Deliberately bounded on BOTH axes: a deterministic failure (a
    validation error, a malformed archive object) raises
    HistoricalDataError just like a network blip does and is
    indistinguishable from one here, so the loop must always terminate.
    `max_attempts` bounds the number of calls; `max_total_seconds`
    bounds CUMULATIVE BACKOFF time (not total runtime -- a backfill
    legitimately runs for hours between blips). Whichever is reached
    first stops the retry.

    Retrying does not risk data: collect_liquidations() only advances
    the checkpoint after a day's rows are durably flushed, so a retry
    re-runs from the checkpoint and never duplicates or skips a row.
    """

    max_attempts: int = _DEFAULT_MAX_ATTEMPTS
    backoff_base_seconds: float = _DEFAULT_BACKOFF_BASE_SECONDS
    max_backoff_seconds: float = _DEFAULT_MAX_BACKOFF_SECONDS
    max_total_seconds: float = _DEFAULT_MAX_TOTAL_SECONDS

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise HistoricalDataError(f"max_attempts must be >= 1, got {self.max_attempts}")
        if self.backoff_base_seconds < 0:
            raise HistoricalDataError(
                f"backoff_base_seconds must be >= 0, got {self.backoff_base_seconds}"
            )
        if self.max_backoff_seconds < 0:
            raise HistoricalDataError(
                f"max_backoff_seconds must be >= 0, got {self.max_backoff_seconds}"
            )
        if self.max_total_seconds < 0:
            raise HistoricalDataError(
                f"max_total_seconds must be >= 0, got {self.max_total_seconds}"
            )

    def backoff_for(self, attempt: int) -> float:
        """Seconds to wait after `attempt` (1-based), capped. Matches the
        original 2/4/8/16/32... progression at the default base."""
        return min(self.backoff_base_seconds * (2 ** (attempt - 1)), self.max_backoff_seconds)


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def _checkpoint_marker(storage_root, checkpoint_path):
    """Best-effort read of the durable checkpoint, used ONLY to detect
    forward progress between retries.

    Never written, and never consulted for what to collect -- that stays
    entirely inside collect_liquidations(). An unreadable/absent
    checkpoint yields None, which is treated as "no progress observed":
    the conservative answer, since it can only shorten retrying, never
    extend it past the configured bounds.

    The default path mirrors collect_liquidations()'s own default (also
    stated in --checkpoint-path's help text). If that default ever
    diverged, this degrades to "no progress detected" -- retries become
    more conservative, never unbounded.
    """
    path = Path(checkpoint_path) if checkpoint_path is not None \
        else Path(storage_root) / ".liquidation_checkpoint.json"
    try:
        return read_checkpoint(path)
    except (HistoricalDataError, OSError, ValueError):
        return None


def _collect_with_retry(
    symbols, start, end, storage_root, force, checkpoint_path,
    policy=None, sleep=None,
):
    """Retries TRANSIENT failures only, bounded by attempts AND by time
    spent waiting.

    The budget measures time spent BACKING OFF, not total runtime. A
    backfill legitimately runs for hours before its first network blip;
    charging that successful work against the retry budget would make
    the very first failure look like an exhausted budget and give up
    without retrying at all.

    A failure that arrives AFTER the checkpoint advanced is a fresh
    outage, not a stuck loop, so the attempt counter and budget reset.
    That is what lets a multi-day backfill survive many independent
    outages instead of accumulating toward a cap that never resets.
    Termination is still guaranteed for the dangerous case: a
    deterministic failure makes no progress, so nothing resets and the
    attempt/budget bounds apply. Progress itself is finite (the
    requested date range), so resetting on progress cannot loop forever.

    Only HistoricalDataError is retried. KeyboardInterrupt, SystemExit
    and every other exception propagate immediately and untouched -- an
    operator pressing Ctrl-C must not have to wait out a backoff, and a
    genuine bug must not be masked as a network blip.
    """
    policy = policy if policy is not None else RetryPolicy()
    # Resolved at CALL time, not bound as argument defaults, so that
    # patching time.sleep on this module keeps working.
    sleep = sleep if sleep is not None else time.sleep

    marker = _checkpoint_marker(storage_root, checkpoint_path)
    attempt = 0
    slept = 0.0
    while True:
        attempt += 1
        try:
            return collect_liquidations(
                symbols, start, end, storage_root, force=force, checkpoint_path=checkpoint_path,
            )
        except HistoricalDataError as exc:
            current = _checkpoint_marker(storage_root, checkpoint_path)
            if current is not None and current != marker:
                # Forward progress since the last failure -> fresh outage.
                marker, attempt, slept = current, 1, 0.0
            if attempt >= policy.max_attempts:
                raise
            backoff = policy.backoff_for(attempt)
            if slept + backoff > policy.max_total_seconds:
                # Sleeping would overrun the budget; stop now rather than
                # after one more oversized wait.
                raise
            print(
                f"liquidations {start.isoformat()}..{end.isoformat()}: transient failure "
                f"(attempt {attempt}/{policy.max_attempts}, {slept:.0f}s of "
                f"{policy.max_total_seconds:.0f}s retry budget used), "
                f"retrying in {backoff:.0f}s: {exc}",
                flush=True,
            )
            sleep(backoff)
            slept += backoff


def run(
    symbols=_DEFAULT_SYMBOLS, start=None, end=None, storage_root=_DEFAULT_STORAGE_ROOT,
    force=False, checkpoint_path=None, policy=None,
) -> int:
    if start is None or end is None:
        raise HistoricalDataError("start and end dates are required")
    policy = policy if policy is not None else RetryPolicy()
    try:
        results = _collect_with_retry(
            symbols, start, end, storage_root, force, checkpoint_path, policy=policy,
        )
    except HistoricalDataError as exc:
        print(
            f"BACKFILL_FAILED after up to {policy.max_attempts} attempts / "
            f"{policy.max_total_seconds:.0f}s retry budget: {exc}",
            flush=True,
        )
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
    parser.add_argument(
        "--retry-max-attempts", type=int, default=_DEFAULT_MAX_ATTEMPTS,
        help=f"max collection attempts before giving up (default: {_DEFAULT_MAX_ATTEMPTS})",
    )
    parser.add_argument(
        "--retry-backoff-base-seconds", type=float, default=_DEFAULT_BACKOFF_BASE_SECONDS,
        help=f"first backoff; doubles each attempt (default: {_DEFAULT_BACKOFF_BASE_SECONDS})",
    )
    parser.add_argument(
        "--retry-max-backoff-seconds", type=float, default=_DEFAULT_MAX_BACKOFF_SECONDS,
        help=f"cap on any single backoff (default: {_DEFAULT_MAX_BACKOFF_SECONDS})",
    )
    parser.add_argument(
        "--retry-max-total-seconds", type=float, default=_DEFAULT_MAX_TOTAL_SECONDS,
        help="total wall-clock retry budget; whichever of this or "
             f"--retry-max-attempts is hit first stops the retry (default: {_DEFAULT_MAX_TOTAL_SECONDS})",
    )
    args = parser.parse_args(argv)
    symbols = tuple(Symbol(s) for s in args.symbols)
    policy = RetryPolicy(
        max_attempts=args.retry_max_attempts,
        backoff_base_seconds=args.retry_backoff_base_seconds,
        max_backoff_seconds=args.retry_max_backoff_seconds,
        max_total_seconds=args.retry_max_total_seconds,
    )
    return run(
        symbols=symbols, start=args.start, end=args.end, storage_root=args.storage_root,
        force=args.force, checkpoint_path=args.checkpoint_path, policy=policy,
    )


if __name__ == "__main__":
    sys.exit(main())
