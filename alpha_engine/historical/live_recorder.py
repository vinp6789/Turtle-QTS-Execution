"""Live Hyperliquid snapshot recorder (approved scope only).

Records the three venue-native metrics that CANNOT be reconstructed from
any archive -- Hyperliquid open interest, funding rate and mark price --
into the historical store, hourly, so that a future campaign has
DEX-native history to test against.

WHY THIS EXISTS (measured, not assumed): Hyperliquid's `/info` exposes
only the CURRENT snapshot via `metaAndAssetCtxs`; no historical
open-interest endpoint exists (live-verified, and the venue rejects a
guessed one -- see sources/hyperliquid.py). Backlog 3.2 then measured the
consequence: a funding campaign clears the power floor on Binance and
fails it on Hyperliquid, and Hyperliquid history cannot be extended
backwards past its venue launch. Data not captured now is unrecoverable.
This module exists to start that clock.

DELIBERATELY OUT OF SCOPE -- do not add: order book / L2 depth, trades or
market-wide fills, queue position, account state, positions, balances,
orders, WebSockets, or anything requiring credentials. The frozen
Execution Engine adapter is REST-only by its own declaration and is not
touched here.

DESIGN NOTES

  - ONE HTTP call per cycle, not one per symbol: `metaAndAssetCtxs`
    returns openInterest/funding/markPx for every asset at once
    (live-verified 2026-08-05). Symbols are located BY NAME, never by a
    fixed index -- SOL sits at index 5, not 2.
  - Its own `source` tag, "hyperliquid_live", so these series are
    SEPARATE files from the API-backfilled ones. Recording live funding
    into funding_rate__*__hyperliquid.csv would risk two rows for one
    settlement (live slot vs. fundingHistory's own millisecond stamp).
  - `observed_at_utc` is the TOP OF THE HOUR the sample belongs to; the
    precise fetch instant is preserved in `ingested_at_utc`. This makes a
    restart within the same hour IDEMPOTENT under storage's
    (symbol, observed_at_utc) dedup key, and matches the hourly grid the
    venue's own funding series already uses.
  - Fail-safe like the providers it sits beside: any fetch or parse
    problem is logged and skipped, never crashes the loop. A recorder
    that dies on one bad response defeats its own purpose.

Run:
    python -m alpha_engine.historical.live_recorder --once
    python -m alpha_engine.historical.live_recorder --interval-seconds 3600
"""

import argparse
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Dict, Sequence, Tuple, Union

from exchange_adapter import Symbol

from .._time import canonical_utc
from ..data_sources.open_interest import post_json
from . import storage
from .errors import HistoricalDataError
from .models import FundingRateObservation, MarkPriceObservation, OpenInterestObservation

_INFO_URL = "https://api.hyperliquid.xyz/info"
_SOURCE_NAME = "hyperliquid_live"
_DEFAULT_TIMEOUT_SECONDS = 15.0
_DEFAULT_INTERVAL_SECONDS = 3600
_DEFAULT_SYMBOLS = (Symbol("BTC"), Symbol("ETH"), Symbol("SOL"))
_DEFAULT_STORAGE_ROOT = "data/alpha_engine_historical"

# (assetCtx field, metric name, observation type)
_METRICS: Tuple[Tuple[str, str, Any], ...] = (
    ("openInterest", "open_interest", OpenInterestObservation),
    ("funding", "funding_rate", FundingRateObservation),
    ("markPx", "mark_price", MarkPriceObservation),
)

_logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hour_slot(instant_utc: str) -> str:
    """The top of the hour `instant_utc` falls in, canonicalized.

    Recording the slot rather than the exact instant is what makes a
    restart within the same hour idempotent: storage dedups on
    (symbol, observed_at_utc) and keeps the first-seen value."""
    dt = datetime.fromisoformat(instant_utc)
    return canonical_utc(dt.replace(minute=0, second=0, microsecond=0).isoformat())


def _asset_ctx(body: Any, symbol_name: str) -> Dict[str, Any]:
    """The assetCtxs entry for `symbol_name`, located BY NAME.

    Same navigation and same failure modes as
    data_sources.open_interest._parse_open_interest -- kept here rather
    than imported because that function returns only openInterest and
    this module needs three fields from the same entry."""
    if not isinstance(body, list) or len(body) < 2:
        raise HistoricalDataError("malformed metaAndAssetCtxs response: expected a two-element array")
    meta, asset_ctxs = body[0], body[1]
    if not isinstance(meta, dict) or not isinstance(meta.get("universe"), list):
        raise HistoricalDataError("malformed metaAndAssetCtxs response: meta['universe'] missing or not a list")
    if not isinstance(asset_ctxs, list):
        raise HistoricalDataError("malformed metaAndAssetCtxs response: assetCtxs missing or not a list")
    for index, asset in enumerate(meta["universe"]):
        if isinstance(asset, dict) and asset.get("name") == symbol_name:
            if index >= len(asset_ctxs) or not isinstance(asset_ctxs[index], dict):
                raise HistoricalDataError(f"no assetCtxs entry at index {index} for {symbol_name!r}")
            return asset_ctxs[index]
    raise HistoricalDataError(f"symbol {symbol_name!r} not found in venue universe")


def _decimal_field(ctx: Dict[str, Any], field_name: str, symbol_name: str) -> Decimal:
    raw = ctx.get(field_name)
    if not isinstance(raw, str):
        raise HistoricalDataError(f"{field_name} for {symbol_name!r} is not a string: {raw!r}")
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise HistoricalDataError(
            f"{field_name} value {raw!r} for {symbol_name!r} is not a valid decimal"
        ) from exc


@dataclass
class RecorderResult:
    observed_at_utc: str
    rows_added: Dict[str, int] = field(default_factory=dict)
    skipped: Tuple[str, ...] = ()
    error: str = ""


def fetch_snapshot(
    symbols: Sequence[Symbol] = _DEFAULT_SYMBOLS,
    *,
    transport: Callable[..., Any] = post_json,
    url: str = _INFO_URL,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    clock: Callable[[], str] = _now,
) -> Tuple[str, Dict[str, Tuple[Any, ...]], Tuple[str, ...]]:
    """One `metaAndAssetCtxs` call -> observations for every metric.

    Returns (observed_at_utc slot, {metric: observations}, skipped notes).
    A symbol whose entry is missing or malformed is SKIPPED and reported,
    never fabricated and never fatal to the other symbols."""
    fetched_at_utc = clock()
    observed_at_utc = hour_slot(fetched_at_utc)
    body = transport(url, {"type": "metaAndAssetCtxs"}, timeout_seconds)

    by_metric: Dict[str, list] = {metric: [] for _, metric, _ in _METRICS}
    skipped = []
    for symbol in symbols:
        try:
            ctx = _asset_ctx(body, symbol.value)
        except HistoricalDataError as exc:
            skipped.append(f"{symbol.value}: {exc}")
            continue
        for field_name, metric, obs_type in _METRICS:
            try:
                value = _decimal_field(ctx, field_name, symbol.value)
            except HistoricalDataError as exc:
                skipped.append(f"{symbol.value}/{metric}: {exc}")
                continue
            by_metric[metric].append(obs_type(
                symbol=symbol, observed_at_utc=observed_at_utc, value=value,
                source=_SOURCE_NAME, source_detail=f"metaAndAssetCtxs {field_name}",
                ingested_at_utc=fetched_at_utc,
            ))
    return observed_at_utc, {m: tuple(v) for m, v in by_metric.items()}, tuple(skipped)


def record_once(
    symbols: Sequence[Symbol] = _DEFAULT_SYMBOLS,
    storage_root: Union[str, Path] = _DEFAULT_STORAGE_ROOT,
    *,
    transport: Callable[..., Any] = post_json,
    url: str = _INFO_URL,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    clock: Callable[[], str] = _now,
) -> RecorderResult:
    """Fetch one snapshot and merge it into the store. Idempotent within
    an hour: re-running writes the same (symbol, hour) keys, which
    storage.merge_and_write coalesces (first-seen value kept)."""
    try:
        observed_at_utc, by_metric, skipped = fetch_snapshot(
            symbols, transport=transport, url=url,
            timeout_seconds=timeout_seconds, clock=clock,
        )
    except Exception as exc:  # noqa: BLE001 -- fail-safe: never kill the loop
        _logger.warning("live_recorder snapshot failed: %s: %s", type(exc).__name__, exc)
        return RecorderResult(observed_at_utc="", error=f"{type(exc).__name__}: {exc}")

    root = Path(storage_root)
    rows_added: Dict[str, int] = {}
    for _, metric, obs_type in _METRICS:
        observations = by_metric.get(metric, ())
        if not observations:
            continue
        by_symbol: Dict[Symbol, list] = {}
        for obs in observations:
            by_symbol.setdefault(obs.symbol, []).append(obs)
        for symbol, rows in by_symbol.items():
            path = root / storage.series_filename(metric, symbol, _SOURCE_NAME)
            result = storage.merge_and_write(path, obs_type, tuple(rows))
            rows_added[f"{metric}/{symbol.value}"] = result.added_count
    if skipped:
        _logger.warning("live_recorder skipped %d field(s): %s", len(skipped), "; ".join(skipped))
    return RecorderResult(observed_at_utc=observed_at_utc, rows_added=rows_added, skipped=skipped)


def run(
    symbols: Sequence[Symbol] = _DEFAULT_SYMBOLS,
    storage_root: Union[str, Path] = _DEFAULT_STORAGE_ROOT,
    *,
    interval_seconds: int = _DEFAULT_INTERVAL_SECONDS,
    max_cycles: int = 0,
    sleep: Callable[[float], None] = time.sleep,
    **kwargs: Any,
) -> int:
    """Record every `interval_seconds` until interrupted. `max_cycles > 0`
    bounds the loop (tests; also a way to run a fixed number of samples)."""
    cycles = 0
    try:
        while True:
            result = record_once(symbols, storage_root, **kwargs)
            if result.error:
                print(f"RECORD_FAILED {result.error}", flush=True)
            else:
                total = sum(result.rows_added.values())
                print(f"RECORDED {result.observed_at_utc} rows_added={total} "
                      f"detail={result.rows_added}", flush=True)
            cycles += 1
            if max_cycles and cycles >= max_cycles:
                return 0
            sleep(interval_seconds)
    except KeyboardInterrupt:
        print(f"RECORDER_STOPPED after {cycles} cycle(s)", flush=True)
        return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Record live Hyperliquid open interest / funding / mark price into the historical store.",
    )
    parser.add_argument("--symbols", nargs="+", default=[s.value for s in _DEFAULT_SYMBOLS])
    parser.add_argument("--storage-root", default=_DEFAULT_STORAGE_ROOT)
    parser.add_argument("--interval-seconds", type=int, default=_DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--once", action="store_true", help="record a single snapshot and exit")
    parser.add_argument("--max-cycles", type=int, default=0, help="stop after N cycles (0 = forever)")
    args = parser.parse_args(argv)
    symbols = tuple(Symbol(s) for s in args.symbols)
    if args.once:
        result = record_once(symbols, args.storage_root)
        if result.error:
            print(f"RECORD_FAILED {result.error}", flush=True)
            return 1
        print(f"RECORDED {result.observed_at_utc} detail={result.rows_added}", flush=True)
        return 0
    return run(symbols, args.storage_root, interval_seconds=args.interval_seconds,
               max_cycles=args.max_cycles)


if __name__ == "__main__":
    sys.exit(main())
