"""The historical collection pipeline: ties one of historical.sources.*
together with historical.validation and historical.storage into a single,
incrementally-rerunnable entry point per metric.

INCREMENTAL BY DESIGN, not merely idempotent: before fetching a given
period, each collection function checks whether that period is ALREADY
present in the on-disk series and, if so, skips the network call
entirely (pass `force=True` to re-fetch and re-verify anyway). This is a
genuine incremental pipeline -- re-running it over a range that mostly
overlaps what has already been collected only fetches the missing
tail/gaps, not the whole range again. (storage.merge_and_write is ALSO
idempotent on its own -- a forced re-fetch or an accidental double-fetch
never duplicates a row -- but the skip-ahead behavior here is what makes
re-running the pipeline cheap, not just safe.)

Binance (day/month-file source): "already present" means at least one
row already exists for that exact calendar day (open interest) or
calendar month (funding rate) -- a safe proxy given each collection call
ingests one whole day/month's file as a single atomic merge.

Hyperliquid (continuous-range source): "already present" means a
high-water mark -- the latest observed_at_utc already on disk for this
(symbol, source) -- and the next fetch resumes from there (never
earlier than the caller's own requested start, so a caller's explicit
start_date is always honored as a floor).

Every collection function returns a CollectionResult carrying a
DataQualityReport (historical.validation.assess_quality) computed over
the FULL resulting on-disk series, not just the newly-fetched rows --
research code should always be able to trust "the file for this
(metric, symbol, source) reflects the quality of everything in it," not
just of the latest run.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from exchange_adapter import Symbol

from .._time import parse_utc
from . import storage
from .errors import HistoricalDataError
from .models import (
    FundingRateObservation, LiquidationObservation, MarkPriceObservation, OpenInterestObservation,
)
from .sources import binance, hyperliquid, hyperliquid_s3
from .validation import DataQualityReport, assess_quality

_logger = logging.getLogger(__name__)

_OI_EXPECTED_INTERVAL_SECONDS = 300           # Binance metrics: 5-minute resolution
_BINANCE_FUNDING_EXPECTED_INTERVAL_SECONDS = 8 * 3600   # Binance's historical native cadence
_HYPERLIQUID_FUNDING_EXPECTED_INTERVAL_SECONDS = 3600   # Hyperliquid's native cadence
_HYPERLIQUID_DAILY_CANDLE_INTERVAL_SECONDS = 24 * 3600  # one candle per day (Backlog 1.4)

_SUPPORTED_OPEN_INTEREST_SOURCES = ("binance",)
_SUPPORTED_MARK_PRICE_SOURCES = ("binance", "hyperliquid")
_SUPPORTED_FUNDING_RATE_SOURCES = ("binance", "hyperliquid")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class CollectionResult:
    """One collect_*() call's outcome."""

    metric: str
    symbol_value: str
    source: str
    path: str
    periods_requested: int
    periods_fetched: int   # periods actually fetched over the network this run
    periods_skipped: int   # periods already present on disk, not re-fetched (force=False)
    periods_unavailable: int  # periods fetched but the source had no data for them
    rows_added: int
    quality_report: Optional[DataQualityReport]
    collected_at_utc: str

    def __post_init__(self) -> None:
        for field_name in (
            "periods_requested", "periods_fetched", "periods_skipped",
            "periods_unavailable", "rows_added",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise HistoricalDataError(f"CollectionResult.{field_name} must be a non-negative int")


def _existing_days_covered(existing: Tuple[Any, ...]) -> Set[date]:
    days = set()
    for obs in existing:
        days.add(parse_utc(obs.observed_at_utc).date())
    return days


def _existing_months_covered(existing: Tuple[Any, ...]) -> Set[Tuple[int, int]]:
    months = set()
    for obs in existing:
        dt = parse_utc(obs.observed_at_utc)
        months.add((dt.year, dt.month))
    return months


def _month_range(start_date: date, end_date: date):
    year, month = start_date.year, start_date.month
    while (year, month) <= (end_date.year, end_date.month):
        yield year, month
        month += 1
        if month > 12:
            month = 1
            year += 1


def collect_open_interest(
    symbol: Symbol,
    start_date: date,
    end_date: date,
    storage_root: Union[str, Path],
    *,
    source: str = "binance",
    force: bool = False,
    transport: Optional[binance.TransportFn] = None,
    timeout_seconds: float = 30.0,
    clock: Callable[[], str] = _now,
) -> CollectionResult:
    """Collects daily open-interest series for `symbol` over
    [start_date, end_date] (inclusive) from `source` into
    storage_root/series_filename(...), skipping days already on disk
    unless force=True.

    Raises HistoricalDataError for `source` other than "binance" --
    Hyperliquid has no free historical open-interest API (see
    docs/HISTORICAL_DATA.md); this is a documented limitation, not an
    oversight, so the pipeline refuses the request explicitly rather than
    silently doing nothing."""
    if source not in _SUPPORTED_OPEN_INTEREST_SOURCES:
        raise HistoricalDataError(
            f"unsupported open_interest source {source!r}; supported: {_SUPPORTED_OPEN_INTEREST_SOURCES} "
            "-- Hyperliquid has no free historical open-interest API (docs/HISTORICAL_DATA.md)"
        )
    if not isinstance(start_date, date) or not isinstance(end_date, date) or end_date < start_date:
        raise HistoricalDataError("start_date/end_date must be date instances with end_date >= start_date")

    fetch_kwargs = {"timeout_seconds": timeout_seconds, "clock": clock}
    if transport is not None:
        fetch_kwargs["transport"] = transport

    path = Path(storage_root) / storage.series_filename("open_interest", symbol, source)
    existing = storage.load(path, OpenInterestObservation)
    covered_days = _existing_days_covered(existing) if not force else set()

    requested = 0
    fetched = 0
    skipped = 0
    unavailable = 0
    new_observations = []
    current = start_date
    while current <= end_date:
        requested += 1
        if current in covered_days:
            skipped += 1
            current += timedelta(days=1)
            continue
        fetched += 1
        day_result = binance.fetch_open_interest_day(symbol, current, **fetch_kwargs)
        if day_result is None:
            unavailable += 1
        else:
            new_observations.extend(day_result)
        current += timedelta(days=1)

    merge_result = storage.merge_and_write(path, OpenInterestObservation, tuple(new_observations))
    if merge_result.conflict_keys:
        _logger.warning(
            "open_interest merge for %s/%s found %d conflicting duplicate key(s); existing values kept: %s",
            symbol.value, source, len(merge_result.conflict_keys), merge_result.conflict_keys,
        )

    full_series = storage.load(path, OpenInterestObservation)
    quality_report = (
        assess_quality(full_series, expected_interval_seconds=_OI_EXPECTED_INTERVAL_SECONDS)
        if full_series else None
    )

    return CollectionResult(
        metric="open_interest", symbol_value=symbol.value, source=source, path=str(path),
        periods_requested=requested, periods_fetched=fetched, periods_skipped=skipped,
        periods_unavailable=unavailable, rows_added=merge_result.added_count,
        quality_report=quality_report, collected_at_utc=clock(),
    )


def collect_mark_price(
    symbol: Symbol,
    start_date: date,
    end_date: date,
    storage_root: Union[str, Path],
    *,
    source: str = "binance",
    force: bool = False,
    transport: Optional[Any] = None,
    timeout_seconds: Optional[float] = None,
    clock: Callable[[], str] = _now,
) -> CollectionResult:
    """Collects daily mark-price series for `symbol` over [start_date,
    end_date] inclusive, from `source` ("binance" or "hyperliquid", Backlog
    1.4) into storage_root/series_filename(...).

    Binance: derived from the daily metrics file's value/OI ratio, skips
    days already on disk unless force=True (structurally identical to
    collect_open_interest() -- same daily-file, skip-covered-days,
    atomic-merge, quality-report flow, since both draw from the same
    daily metrics files).
    Hyperliquid: a daily candle's CLOSE price (sources.hyperliquid.
    fetch_daily_candles -- see that function's own derivation-scope note,
    RD-11 A: a daily close is not the same quantity as Binance's
    point-in-time mark price). Resumes from the latest observed_at_utc
    already on disk (a high-water mark), never earlier than the caller's
    own start_date -- the same continuous-range pattern
    collect_funding_rate already uses for this venue.

    Required for forward-return outcomes in return-based research."""
    if source not in _SUPPORTED_MARK_PRICE_SOURCES:
        raise HistoricalDataError(
            f"unsupported mark_price source {source!r}; supported: {_SUPPORTED_MARK_PRICE_SOURCES}"
        )
    if not isinstance(start_date, date) or not isinstance(end_date, date) or end_date < start_date:
        raise HistoricalDataError("start_date/end_date must be date instances with end_date >= start_date")

    path = Path(storage_root) / storage.series_filename("mark_price", symbol, source)
    existing = storage.load(path, MarkPriceObservation)

    if source == "binance":
        return _collect_mark_price_binance(
            symbol, start_date, end_date, path, existing, force, transport, timeout_seconds, clock,
        )
    return _collect_mark_price_hyperliquid(
        symbol, start_date, end_date, path, existing, force, transport, timeout_seconds, clock,
    )


def _collect_mark_price_binance(
    symbol, start_date, end_date, path, existing, force, transport, timeout_seconds, clock,
) -> CollectionResult:
    fetch_kwargs = {"clock": clock}
    fetch_kwargs["timeout_seconds"] = timeout_seconds if timeout_seconds is not None else 30.0
    if transport is not None:
        fetch_kwargs["transport"] = transport

    covered_days = _existing_days_covered(existing) if not force else set()

    requested = fetched = skipped = unavailable = 0
    new_observations = []
    current = start_date
    while current <= end_date:
        requested += 1
        if current in covered_days:
            skipped += 1
            current += timedelta(days=1)
            continue
        fetched += 1
        day_result = binance.fetch_mark_price_day(symbol, current, **fetch_kwargs)
        if day_result is None:
            unavailable += 1
        else:
            new_observations.extend(day_result)
        current += timedelta(days=1)

    merge_result = storage.merge_and_write(path, MarkPriceObservation, tuple(new_observations))
    if merge_result.conflict_keys:
        _logger.warning(
            "mark_price merge for %s/binance found %d conflicting duplicate key(s); existing values kept: %s",
            symbol.value, len(merge_result.conflict_keys), merge_result.conflict_keys,
        )

    full_series = storage.load(path, MarkPriceObservation)
    quality_report = (
        assess_quality(full_series, expected_interval_seconds=_OI_EXPECTED_INTERVAL_SECONDS)
        if full_series else None
    )
    return CollectionResult(
        metric="mark_price", symbol_value=symbol.value, source="binance", path=str(path),
        periods_requested=requested, periods_fetched=fetched, periods_skipped=skipped,
        periods_unavailable=unavailable, rows_added=merge_result.added_count,
        quality_report=quality_report, collected_at_utc=clock(),
    )


def _collect_mark_price_hyperliquid(
    symbol, start_date, end_date, path, existing, force, transport, timeout_seconds, clock,
) -> CollectionResult:
    fetch_kwargs = {"clock": clock}
    fetch_kwargs["timeout_seconds"] = timeout_seconds if timeout_seconds is not None else 15.0
    if transport is not None:
        fetch_kwargs["transport"] = transport

    start_ms = int(datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc).timestamp() * 1000)
    # -1ms, NOT the "+1 day, exclusive" pattern collect_funding_rate uses:
    # live-verified (2026-07-29) that candleSnapshot's endTime is INCLUSIVE
    # of a candle whose own start time == endTime exactly. A daily candle's
    # start time always lands precisely on a day boundary, so the funding
    # pattern's "midnight of end_date+1" would itself be a valid candle
    # start and silently pull in one extra day beyond what the caller
    # asked for (harmless for hourly funding settlements, which almost
    # never land exactly on that boundary -- not safe to copy verbatim
    # for daily data).
    end_ms = int(
        (datetime(end_date.year, end_date.month, end_date.day, tzinfo=timezone.utc) + timedelta(days=1)).timestamp()
        * 1000
    ) - 1

    if not force and existing:
        high_water_ms = max(int(parse_utc(obs.observed_at_utc).timestamp() * 1000) for obs in existing)
        cursor_ms = max(start_ms, high_water_ms + 1)
    else:
        cursor_ms = start_ms

    if cursor_ms > end_ms:
        new_observations: Tuple[MarkPriceObservation, ...] = ()
        fetched = 0
    else:
        new_observations = hyperliquid.fetch_daily_candles(symbol, cursor_ms, end_ms, **fetch_kwargs)
        fetched = 1

    merge_result = storage.merge_and_write(path, MarkPriceObservation, tuple(new_observations))
    if merge_result.conflict_keys:
        _logger.warning(
            "mark_price merge for %s/hyperliquid found %d conflicting duplicate key(s); existing values kept: %s",
            symbol.value, len(merge_result.conflict_keys), merge_result.conflict_keys,
        )

    full_series = storage.load(path, MarkPriceObservation)
    quality_report = (
        assess_quality(full_series, expected_interval_seconds=_HYPERLIQUID_DAILY_CANDLE_INTERVAL_SECONDS)
        if full_series else None
    )
    return CollectionResult(
        metric="mark_price", symbol_value=symbol.value, source="hyperliquid", path=str(path),
        periods_requested=1, periods_fetched=fetched, periods_skipped=(1 - fetched),
        periods_unavailable=(1 if fetched and len(new_observations) == 0 else 0),
        rows_added=merge_result.added_count, quality_report=quality_report, collected_at_utc=clock(),
    )


def collect_metrics(
    symbol: Symbol,
    start_date: date,
    end_date: date,
    storage_root: Union[str, Path],
    *,
    force: bool = False,
    transport: Optional[binance.TransportFn] = None,
    timeout_seconds: float = 30.0,
    clock: Callable[[], str] = _now,
) -> Tuple[CollectionResult, CollectionResult]:
    """Collects BOTH the open-interest and mark-price daily series in a
    SINGLE download pass per day (via binance.fetch_metrics_day), writing
    both series atomically. Halves the request volume vs. calling
    collect_open_interest + collect_mark_price separately. Returns
    (open_interest_result, mark_price_result). Skip-decisions use the OI
    series' coverage (both series are written together, so coverage is
    symmetric)."""
    if not isinstance(start_date, date) or not isinstance(end_date, date) or end_date < start_date:
        raise HistoricalDataError("start_date/end_date must be date instances with end_date >= start_date")

    fetch_kwargs = {"timeout_seconds": timeout_seconds, "clock": clock}
    if transport is not None:
        fetch_kwargs["transport"] = transport

    oi_path = Path(storage_root) / storage.series_filename("open_interest", symbol, "binance")
    mark_path = Path(storage_root) / storage.series_filename("mark_price", symbol, "binance")
    existing_oi = storage.load(oi_path, OpenInterestObservation)
    covered_days = _existing_days_covered(existing_oi) if not force else set()

    requested = fetched = skipped = unavailable = 0
    new_oi: list = []
    new_mark: list = []
    current = start_date
    while current <= end_date:
        requested += 1
        if current in covered_days:
            skipped += 1
            current += timedelta(days=1)
            continue
        fetched += 1
        day_result = binance.fetch_metrics_day(symbol, current, **fetch_kwargs)
        if day_result is None:
            unavailable += 1
        else:
            oi_rows, mark_rows = day_result
            new_oi.extend(oi_rows)
            new_mark.extend(mark_rows)
        current += timedelta(days=1)

    oi_merge = storage.merge_and_write(oi_path, OpenInterestObservation, tuple(new_oi))
    mark_merge = storage.merge_and_write(mark_path, MarkPriceObservation, tuple(new_mark))

    oi_full = storage.load(oi_path, OpenInterestObservation)
    mark_full = storage.load(mark_path, MarkPriceObservation)
    oi_report = CollectionResult(
        metric="open_interest", symbol_value=symbol.value, source="binance", path=str(oi_path),
        periods_requested=requested, periods_fetched=fetched, periods_skipped=skipped,
        periods_unavailable=unavailable, rows_added=oi_merge.added_count,
        quality_report=(assess_quality(oi_full, expected_interval_seconds=_OI_EXPECTED_INTERVAL_SECONDS)
                        if oi_full else None),
        collected_at_utc=clock(),
    )
    mark_report = CollectionResult(
        metric="mark_price", symbol_value=symbol.value, source="binance", path=str(mark_path),
        periods_requested=requested, periods_fetched=fetched, periods_skipped=skipped,
        periods_unavailable=unavailable, rows_added=mark_merge.added_count,
        quality_report=(assess_quality(mark_full, expected_interval_seconds=_OI_EXPECTED_INTERVAL_SECONDS)
                        if mark_full else None),
        collected_at_utc=clock(),
    )
    return oi_report, mark_report


def collect_funding_rate(
    symbol: Symbol,
    start_date: date,
    end_date: date,
    storage_root: Union[str, Path],
    *,
    source: str = "binance",
    force: bool = False,
    transport: Optional[Any] = None,
    timeout_seconds: Optional[float] = None,
    clock: Callable[[], str] = _now,
) -> CollectionResult:
    """Collects funding-rate settlements for `symbol` over
    [start_date, end_date] (inclusive) from `source` ("binance" or
    "hyperliquid") into storage_root/series_filename(...).

    Binance: skips whole months already on disk unless force=True (one
    month = one archive file = one atomic merge, so "any row present in
    that month" is a safe proxy for "already collected").
    Hyperliquid: resumes from the latest observed_at_utc already on disk
    (a high-water mark), never earlier than the caller's own start_date.
    """
    if source not in _SUPPORTED_FUNDING_RATE_SOURCES:
        raise HistoricalDataError(
            f"unsupported funding_rate source {source!r}; supported: {_SUPPORTED_FUNDING_RATE_SOURCES}"
        )
    if not isinstance(start_date, date) or not isinstance(end_date, date) or end_date < start_date:
        raise HistoricalDataError("start_date/end_date must be date instances with end_date >= start_date")

    path = Path(storage_root) / storage.series_filename("funding_rate", symbol, source)
    existing = storage.load(path, FundingRateObservation)

    if source == "binance":
        result = _collect_funding_rate_binance(
            symbol, start_date, end_date, path, existing, force, transport, timeout_seconds, clock,
        )
    else:
        result = _collect_funding_rate_hyperliquid(
            symbol, start_date, end_date, path, existing, force, transport, timeout_seconds, clock,
        )
    return result


def _collect_funding_rate_binance(
    symbol, start_date, end_date, path, existing, force, transport, timeout_seconds, clock,
) -> CollectionResult:
    fetch_kwargs = {"clock": clock}
    fetch_kwargs["timeout_seconds"] = timeout_seconds if timeout_seconds is not None else 30.0
    if transport is not None:
        fetch_kwargs["transport"] = transport

    covered_months = _existing_months_covered(existing) if not force else set()

    requested = 0
    fetched = 0
    skipped = 0
    unavailable = 0
    new_observations = []
    for year, month in _month_range(start_date, end_date):
        requested += 1
        if (year, month) in covered_months:
            skipped += 1
            continue
        fetched += 1
        month_result = binance.fetch_funding_rate_month(symbol, year, month, **fetch_kwargs)
        if month_result is None:
            unavailable += 1
        else:
            new_observations.extend(month_result)

    merge_result = storage.merge_and_write(path, FundingRateObservation, tuple(new_observations))
    if merge_result.conflict_keys:
        _logger.warning(
            "funding_rate merge for %s/binance found %d conflicting duplicate key(s); existing values kept: %s",
            symbol.value, len(merge_result.conflict_keys), merge_result.conflict_keys,
        )

    full_series = storage.load(path, FundingRateObservation)
    quality_report = (
        assess_quality(full_series, expected_interval_seconds=_BINANCE_FUNDING_EXPECTED_INTERVAL_SECONDS)
        if full_series else None
    )
    return CollectionResult(
        metric="funding_rate", symbol_value=symbol.value, source="binance", path=str(path),
        periods_requested=requested, periods_fetched=fetched, periods_skipped=skipped,
        periods_unavailable=unavailable, rows_added=merge_result.added_count,
        quality_report=quality_report, collected_at_utc=clock(),
    )


def _collect_funding_rate_hyperliquid(
    symbol, start_date, end_date, path, existing, force, transport, timeout_seconds, clock,
) -> CollectionResult:
    fetch_kwargs = {"clock": clock}
    fetch_kwargs["timeout_seconds"] = timeout_seconds if timeout_seconds is not None else 15.0
    if transport is not None:
        fetch_kwargs["transport"] = transport

    start_ms = int(datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int(
        (datetime(end_date.year, end_date.month, end_date.day, tzinfo=timezone.utc) + timedelta(days=1)).timestamp()
        * 1000
    )

    if not force and existing:
        high_water_ms = max(int(parse_utc(obs.observed_at_utc).timestamp() * 1000) for obs in existing)
        cursor_ms = max(start_ms, high_water_ms + 1)
    else:
        cursor_ms = start_ms

    if cursor_ms >= end_ms:
        new_observations: Tuple[FundingRateObservation, ...] = ()
        fetched = 0
    else:
        new_observations = hyperliquid.fetch_funding_rate_range(symbol, cursor_ms, end_ms, **fetch_kwargs)
        fetched = 1

    merge_result = storage.merge_and_write(path, FundingRateObservation, tuple(new_observations))
    if merge_result.conflict_keys:
        _logger.warning(
            "funding_rate merge for %s/hyperliquid found %d conflicting duplicate key(s); existing values kept: %s",
            symbol.value, len(merge_result.conflict_keys), merge_result.conflict_keys,
        )

    full_series = storage.load(path, FundingRateObservation)
    quality_report = (
        assess_quality(full_series, expected_interval_seconds=_HYPERLIQUID_FUNDING_EXPECTED_INTERVAL_SECONDS)
        if full_series else None
    )
    return CollectionResult(
        metric="funding_rate", symbol_value=symbol.value, source="hyperliquid", path=str(path),
        periods_requested=1, periods_fetched=fetched, periods_skipped=(1 - fetched),
        periods_unavailable=(1 if fetched and len(new_observations) == 0 else 0),
        rows_added=merge_result.added_count, quality_report=quality_report, collected_at_utc=clock(),
    )


def collect_liquidations(
    symbols: Tuple[Symbol, ...],
    start_date: date,
    end_date: date,
    storage_root: Union[str, Path],
    *,
    checkpoint_path: Optional[Union[str, Path]] = None,
    bucket: str = hyperliquid_s3.DEFAULT_BUCKET,
    prefix: str = hyperliquid_s3.DEFAULT_PREFIX,
    region: str = hyperliquid_s3.DEFAULT_REGION,
    force: bool = False,
    clock: Callable[[], str] = _now,
) -> Tuple[CollectionResult, ...]:
    """Collects liquidation events for `symbols` over [start_date,
    end_date] (inclusive) from the official Hyperliquid S3 fill archive
    (`sources.hyperliquid_s3`) into one series file per symbol.

    Deliberately diverges from the day/month-skip pattern of every
    sibling collect_*() above -- this is intentional, not an
    inconsistency (see RD-13, `docs/PROJECT_STATE.md` Known Risks
    "two-resume-mechanism divergence"). The underlying archive is one
    object per HOUR (`sources.hyperliquid_s3.list_hour_keys`), and resume
    uses the source module's own key-ordered checkpoint
    (`read_checkpoint`/`write_checkpoint`), not a day-covered proxy --
    checkpointing every hour keeps an interrupted multi-day backfill from
    ever re-downloading a day's worth of Requester-Pays data it already
    processed. `checkpoint_path` defaults to
    `storage_root/.liquidation_checkpoint.json`, mirroring where the
    bounded pilot backfill kept it. `force=True` ignores any existing
    checkpoint and reprocesses the whole range (storage.merge_and_write
    is idempotent, so this cannot duplicate rows).

    DURABILITY INVARIANT: the checkpoint may never advance past data that
    is not yet durably on disk. Decoded rows for a calendar day are held
    in memory only until every hour requested for that day has been
    fetched; ONLY THEN are they merge_and_write'n to disk, and ONLY AFTER
    that write succeeds does the checkpoint advance -- to the last key of
    that day, written once. If fetch_hour raises partway through a day,
    nothing is written and the checkpoint does not move: the ENTIRE day
    is safely retried from scratch on the next call (merge_and_write is
    idempotent, so re-fetching already-decoded hours costs a re-download,
    never a duplicate row).

    An earlier version of this function wrote the checkpoint per HOUR,
    inside the fetch loop, while still batching the disk write to once
    per day -- a process killed between an hour's checkpoint write and
    the day's eventual flush left the checkpoint durably pointing at
    hours whose rows existed only in memory, and resume then skipped
    those hours forever without ever persisting them. Found by
    independent QA review before Backlog 1.5 (the full 12-month
    backfill) ran; fixed by moving the checkpoint write to strictly after
    the flush, once per day. See
    `test_mid_day_interruption_does_not_advance_checkpoint_past_unpersisted_rows`.

    `symbols` is plural, unlike every sibling collector's single
    `symbol` -- also intentional: one hourly object contains ALL symbols'
    fills, so `sources.hyperliquid_s3.fetch_hour` already decodes and
    filters every requested symbol from a single download. Returns one
    CollectionResult per symbol, in the given order; each result's
    periods_requested/fetched/skipped are HOUR counts (matching the
    checkpoint's own granularity), and periods_unavailable counts whole
    DAYS the archive had no object for at all (e.g. before
    `sources.hyperliquid_s3.EARLIEST_MEASURED_DATE`)."""
    if not isinstance(symbols, tuple) or not symbols or not all(isinstance(s, Symbol) for s in symbols):
        raise HistoricalDataError("symbols must be a non-empty tuple of Symbol")
    if not isinstance(start_date, date) or not isinstance(end_date, date) or end_date < start_date:
        raise HistoricalDataError("start_date/end_date must be date instances with end_date >= start_date")

    root = Path(storage_root)
    cp_path = Path(checkpoint_path) if checkpoint_path is not None else root / ".liquidation_checkpoint.json"
    checkpoint = None if force else hyperliquid_s3.read_checkpoint(cp_path)
    # One client for the whole call, not one per list/fetch: both
    # sources.hyperliquid_s3 functions already accept `client` for exactly
    # this reuse (the pilot driver did the same). Constructing it here
    # also fails fast if boto3 is missing, rather than on the first day.
    client = hyperliquid_s3._client(region)

    paths = {
        s.value: root / storage.series_filename("liquidation", s, hyperliquid_s3.SOURCE_NAME) for s in symbols
    }
    requested = fetched = skipped = unavailable = 0
    rows_added: Dict[str, int] = {s.value: 0 for s in symbols}
    current = start_date
    while current <= end_date:
        date_str = current.strftime("%Y%m%d")
        keys = hyperliquid_s3.list_hour_keys(
            date=date_str, bucket=bucket, prefix=prefix, region=region, client=client,
        )
        if not keys:
            unavailable += 1
            current += timedelta(days=1)
            continue
        todo = hyperliquid_s3.keys_after_checkpoint(keys, checkpoint)
        requested += len(keys)
        skipped += len(keys) - len(todo)

        day_new_by_symbol: Dict[str, List[LiquidationObservation]] = {s.value: [] for s in symbols}
        for key in todo:
            fetched += 1
            obs = hyperliquid_s3.fetch_hour(key, bucket=bucket, region=region, symbols=symbols, client=client)
            for o in obs:
                day_new_by_symbol[o.symbol.value].append(o)

        # Flush this day's decoded rows, THEN advance the checkpoint --
        # never the reverse. See the DURABILITY INVARIANT note above: if
        # fetch_hour raised above, this block never runs, no checkpoint
        # update happens for this day, and the whole day is safely
        # retried on the next call.
        if todo:
            for symbol in symbols:
                day_rows = tuple(day_new_by_symbol[symbol.value])
                if not day_rows:
                    continue
                merge_result = storage.merge_and_write(paths[symbol.value], LiquidationObservation, day_rows)
                rows_added[symbol.value] += merge_result.added_count
                if merge_result.conflict_keys:
                    _logger.warning(
                        "liquidation merge for %s/%s found %d conflicting duplicate key(s) on %s; "
                        "existing values kept: %s",
                        symbol.value, hyperliquid_s3.SOURCE_NAME, len(merge_result.conflict_keys),
                        date_str, merge_result.conflict_keys,
                    )
            hyperliquid_s3.write_checkpoint(cp_path, todo[-1])
            checkpoint = todo[-1]
        current += timedelta(days=1)

    results = []
    for symbol in symbols:
        path = paths[symbol.value]
        full_series = storage.load(path, LiquidationObservation)
        # No expected_interval_seconds: liquidations are event-driven, not
        # periodic, so a fixed-cadence gap check would be meaningless. The
        # duplicate/ordering checks below are still meaningful, EXCEPT
        # that assess_quality's (symbol, observed_at_utc) key will report
        # the two legitimate paired rows of every single liquidation
        # (see models.LiquidationObservation) as a "duplicate" -- that is
        # a known, structural false-positive of this general-purpose
        # check against this one observation type's real key
        # (symbol, observed_at_utc, tid, side), already correctly used by
        # storage._dedup_key. Reported as-is rather than building a
        # liquidation-specific quality check for one call site.
        quality_report = assess_quality(full_series) if full_series else None
        results.append(CollectionResult(
            metric="liquidation", symbol_value=symbol.value, source=hyperliquid_s3.SOURCE_NAME, path=str(path),
            periods_requested=requested, periods_fetched=fetched, periods_skipped=skipped,
            periods_unavailable=unavailable, rows_added=rows_added[symbol.value],
            quality_report=quality_report, collected_at_utc=clock(),
        ))
    return tuple(results)
