"""Historical data collection pipeline (Alpha Engine, post-R8 research
transition).

Backfills Open Interest and Funding Rate history for BTC/ETH/SOL from
free, public sources into a research-friendly, incrementally-rerunnable
local CSV store -- see docs/HISTORICAL_DATA.md for the full source
comparison/recommendation, update frequency, limitations, point-in-time
considerations, and known biases.

This is BACKFILL/RESEARCH infrastructure, entirely separate from
alpha_engine.data_sources (the LIVE, fail-safe providers the execution
bridge consumes): a historical archive either has a file for a given
period or it doesn't (handled by skipping, logged, never a fabricated
value); it never needs data_sources' available/reason live-fetch
discipline. Nothing here is wired into the execution bridge, and nothing
in alpha_engine.data_sources depends on this package.

Public API:
    FundingRateObservation, OpenInterestObservation
                             -- one historical data point, typed,
                                canonical-UTC-validated (models.py)
    assess_quality           -- pure duplicate/ordering/gap report over a
                                collected series (validation.py)
    DataQualityReport        -- assess_quality()'s outcome
    verify_checksum           -- SHA-256 integrity check
    series_filename           -- deterministic (metric, symbol, source)
                                CSV filename
    load, merge_and_write, MergeResult
                             -- incremental CSV storage (storage.py)
    collect_open_interest, collect_funding_rate, collect_liquidations,
    CollectionResult         -- the pipeline entry points (pipeline.py)
    HistoricalDataError      -- this package's error base

    historical.sources.binance         -- primary source client
    historical.sources.hyperliquid     -- secondary (venue-consistent) source client
    historical.sources.hyperliquid_s3  -- official Hyperliquid S3 fill/liquidation archive (RD-10/RD-12)
"""

from .errors import HistoricalDataError
from .models import (
    FundingRateObservation,
    LiquidationObservation,
    MarkPriceObservation,
    OpenInterestObservation,
)
from .pipeline import (
    CollectionResult,
    collect_funding_rate,
    collect_liquidations,
    collect_mark_price,
    collect_metrics,
    collect_open_interest,
)
from .storage import MergeResult, load, merge_and_write, series_filename
from .validation import DataQualityReport, assess_quality, verify_checksum

__all__ = [
    "FundingRateObservation",
    "LiquidationObservation",
    "OpenInterestObservation",
    "MarkPriceObservation",
    "assess_quality",
    "DataQualityReport",
    "verify_checksum",
    "series_filename",
    "load",
    "merge_and_write",
    "MergeResult",
    "collect_open_interest",
    "collect_mark_price",
    "collect_metrics",
    "collect_funding_rate",
    "collect_liquidations",
    "CollectionResult",
    "HistoricalDataError",
]
