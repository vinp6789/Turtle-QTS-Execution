"""Backlog 3.6 — collect the Hyperliquid-native HOURLY outcome series.

Backlog 3.5 APPROVED an hourly Campaign 06 specification but found the
outcome series missing: `mark_price__*__hyperliquid.csv` holds daily
candles only, and Binance's 5-minute series is cross-venue and therefore
never promotion-eligible under Constitution Section 6.

TIME-SENSITIVE. The venue retains 1h candles for only ~210 days
(binary-searched 2026-08-05: present at -210d, empty at -213d), while
daily candles reach the archive start. One more day ages out every day
this waits. That is the entire reason this runs now rather than when the
campaign is written.

Writes under source `hyperliquid_1h`, a DISTINCT series from the daily
`hyperliquid` mark price. They are different quantities -- an hourly
close is not a daily close -- and RD-11 A requires the derivation scope
be explicit rather than merged.

Zero new collection machinery: reuses
`sources.hyperliquid.fetch_daily_candles(..., interval="1h")` (which
carries the still-forming-candle guard unchanged) and
`storage.merge_and_write` (idempotent, dedup-keyed on
(symbol, observed_at_utc)). Re-running is safe and adds nothing.

Run: python -m research.campaign_06_liquidations.collect_hourly_outcomes
"""

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from exchange_adapter import Symbol

from alpha_engine.historical import storage
from alpha_engine.historical.models import MarkPriceObservation
from alpha_engine.historical.sources.hyperliquid import fetch_daily_candles

_SYMBOLS = (Symbol("BTC"), Symbol("ETH"), Symbol("SOL"))
_STORAGE_ROOT = "data/alpha_engine_historical"
_SOURCE = "hyperliquid_1h"
_INTERVAL = "1h"
# Start slightly before the measured ~210-day retention edge; the venue
# simply returns nothing for out-of-retention hours, so over-requesting
# costs one request and never fabricates data.
_LOOKBACK_DAYS = 215
_CHUNK_DAYS = 30  # keeps each response well under any page cap


def run(symbols=_SYMBOLS, storage_root=_STORAGE_ROOT, lookback_days=_LOOKBACK_DAYS):
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=lookback_days)
    root = Path(storage_root)
    print(f"collecting {_INTERVAL} candles {start.date()} -> {now.date()} "
          f"({lookback_days}d lookback; venue retention ~210d)")

    for symbol in symbols:
        t0 = time.perf_counter()
        collected = []
        cursor = start
        while cursor < now:
            chunk_end = min(cursor + timedelta(days=_CHUNK_DAYS), now)
            rows = fetch_daily_candles(
                symbol,
                int(cursor.timestamp() * 1000),
                int(chunk_end.timestamp() * 1000),
                interval=_INTERVAL,
            )
            collected.extend(rows)
            cursor = chunk_end
        # Re-stamp the source so these never collide with the daily series.
        observations = tuple(
            MarkPriceObservation(
                symbol=o.symbol, observed_at_utc=o.observed_at_utc, value=o.value,
                source=_SOURCE, source_detail=o.source_detail,
                ingested_at_utc=o.ingested_at_utc,
            )
            for o in collected
        )
        path = root / storage.series_filename("mark_price", symbol, _SOURCE)
        result = storage.merge_and_write(path, MarkPriceObservation, observations)
        full = storage.load(path, MarkPriceObservation)
        times = sorted(o.observed_at_utc for o in full)
        print(f"  {symbol.value}: fetched={len(observations):,} added={result.rows_added if hasattr(result,'rows_added') else result.added_count:,} "
              f"total={len(full):,}  {times[0][:16]} .. {times[-1][:16]}  "
              f"({time.perf_counter()-t0:.1f}s)")
    print("HOURLY_OUTCOME_COLLECTION_COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(run())
