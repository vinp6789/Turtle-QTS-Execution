"""Binance USDⓈ-M Futures public bulk historical archive
(data.binance.vision) -- the PRIMARY historical source for both open
interest and funding rate (see docs/HISTORICAL_DATA.md for the full
source comparison and recommendation).

Free, no API key, no rate limiting (static file downloads from a
CloudFront-backed archive), SHA-256 checksummed per file. Verified live
against the real archive during this pipeline's design:

  - Daily "metrics" files (contain open interest, among other columns)
    at 5-minute resolution:
      https://data.binance.vision/data/futures/um/daily/metrics/
        {SYMBOL}/{SYMBOL}-metrics-{YYYY-MM-DD}.zip (+ .CHECKSUM)
    Earliest coverage differs per symbol (BTCUSDT ~2020-09, ETHUSDT and
    SOLUSDT ~late 2021/2022 -- Binance began publishing this specific
    data type well after each symbol's own listing date). A date before
    a symbol's earliest coverage, or not yet published, 404s -- treated
    here as "unavailable for this date," never an error.
  - Monthly "fundingRate" files, at Binance's own native funding cadence
    (historically 8-hourly for these three symbols; the file's own
    `funding_interval_hours` column records this per-row rather than
    assuming it):
      https://data.binance.vision/data/futures/um/monthly/fundingRate/
        {SYMBOL}/{SYMBOL}-fundingRate-{YYYY-MM}.zip (+ .CHECKSUM)
    Earliest coverage: BTCUSDT/ETHUSDT from 2020-01, SOLUSDT from
    2020-09 (SOLUSDT's Binance futures listing).

THIS IS BINANCE DATA, NOT HYPERLIQUID DATA -- the Alpha Engine's live
execution venue is Hyperliquid (alpha_engine.data_sources). Binance
funding/OI reflect Binance's own mark-price formula, funding cadence, and
trader population, not Hyperliquid's. See docs/HISTORICAL_DATA.md's
"known biases" section before treating a Binance-derived research
conclusion as directly transferable to live Hyperliquid trading.

Symbol mapping is fixed and narrow, matching only what this pipeline
targets (BTC, ETH, SOL against their USDT-margined perpetual): Symbol
"BTC" -> "BTCUSDT". Extending to a different quote asset or a symbol
outside this project's current watchlist is future work, not silently
guessed here.

Deliberately stdlib-only (urllib, zipfile, csv, io) -- no new third-party
dependency, matching alpha_engine.data_sources.open_interest's own
"small, independent, stdlib-only HTTP client" precedent. A TransportFn
seam (mirroring that same module's TransportFn pattern) makes every
function here testable without a real network call.
"""

import csv
import io
import logging
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Callable, Optional, Tuple

from exchange_adapter import Symbol

from ..._time import canonical_utc
from ..errors import HistoricalDataError
from ..models import FundingRateObservation, MarkPriceObservation, OpenInterestObservation
from ..validation import verify_checksum

_BASE_URL = "https://data.binance.vision/data/futures/um"
_SOURCE_NAME = "binance"
_DEFAULT_TIMEOUT_SECONDS = 30.0

_logger = logging.getLogger(__name__)

# TransportFn: (url, timeout_seconds) -> raw response bytes. Raises
# urllib.error.HTTPError (with .code) for a non-2xx response, or
# urllib.error.URLError for a connection-level failure. A stall on an
# already-open connection (the read of the response status line/body
# itself timing out) is NOT wrapped into URLError by urlopen -- it
# surfaces as a bare TimeoutError -- so _fetch_zip_csv below must catch
# that separately.
TransportFn = Callable[[str, float], bytes]


def http_get(url: str, timeout_seconds: float) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
        return response.read()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _binance_symbol(symbol: Symbol) -> str:
    if not isinstance(symbol, Symbol):
        raise HistoricalDataError(f"symbol must be a Symbol, got {type(symbol).__name__}")
    return f"{symbol.value}USDT"


def _fetch_zip_csv(
    zip_url: str, checksum_url: str, transport: TransportFn, timeout_seconds: float,
) -> Optional[bytes]:
    """Downloads zip_url + checksum_url, verifies integrity, and returns
    the single CSV member's raw bytes. Returns None if zip_url 404s (the
    file is not available -- before the symbol's earliest coverage, or
    not yet published). Raises HistoricalDataError for a checksum
    mismatch or any non-404 transport failure (a transient/network
    condition the caller should see, not one this function silently
    absorbs as "no data")."""
    try:
        zip_bytes = transport(zip_url, timeout_seconds)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise HistoricalDataError(f"{zip_url}: HTTP {exc.code}: {exc}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        # TimeoutError (a stalled read on an already-open connection) is
        # not a urllib.error.URLError -- see the TransportFn comment above.
        raise HistoricalDataError(f"{zip_url}: transport failure: {exc}") from exc

    try:
        checksum_bytes = transport(checksum_url, timeout_seconds)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise HistoricalDataError(f"{checksum_url}: could not fetch checksum: {exc}") from exc
    expected_hex = checksum_bytes.decode("utf-8").split()[0]
    if not verify_checksum(zip_bytes, expected_hex):
        raise HistoricalDataError(
            f"{zip_url}: downloaded content failed checksum verification against {checksum_url}"
        )

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        names = archive.namelist()
        if len(names) != 1:
            raise HistoricalDataError(f"{zip_url}: expected exactly one archive member, found {names!r}")
        return archive.read(names[0])


def fetch_open_interest_day(
    symbol: Symbol,
    day: date,
    *,
    transport: TransportFn = http_get,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    clock: Callable[[], str] = _now,
) -> Optional[Tuple[OpenInterestObservation, ...]]:
    """One day's 5-minute-resolution open-interest series for `symbol`
    (mapped to its Binance USDT-margined perpetual). Returns None if this
    date is not available from Binance's archive (before the symbol's
    earliest coverage, or not yet published) -- a normal, expected
    condition, not an error."""
    if not isinstance(day, date):
        raise HistoricalDataError(f"day must be a date, got {type(day).__name__}")
    binance_symbol = _binance_symbol(symbol)
    date_str = day.isoformat()
    zip_url = f"{_BASE_URL}/daily/metrics/{binance_symbol}/{binance_symbol}-metrics-{date_str}.zip"
    checksum_url = zip_url + ".CHECKSUM"
    source_detail = f"{binance_symbol}-metrics-{date_str}.zip"

    csv_bytes = _fetch_zip_csv(zip_url, checksum_url, transport, timeout_seconds)
    if csv_bytes is None:
        _logger.info("binance open interest unavailable for %s on %s (%s)", symbol.value, date_str, zip_url)
        return None

    ingested_at_utc = clock()
    observations = []
    reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8")))
    for row in reader:
        try:
            observed_at_utc = canonical_utc(row["create_time"].replace(" ", "T") + "Z")
            value = Decimal(row["sum_open_interest"])
        except (KeyError, ValueError, InvalidOperation) as exc:
            raise HistoricalDataError(f"{source_detail}: malformed row {row!r}: {exc}") from exc
        observations.append(OpenInterestObservation(
            symbol=symbol, observed_at_utc=observed_at_utc, value=value,
            source=_SOURCE_NAME, source_detail=source_detail, ingested_at_utc=ingested_at_utc,
        ))
    return tuple(observations)


def fetch_mark_price_day(
    symbol: Symbol,
    day: date,
    *,
    transport: TransportFn = http_get,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    clock: Callable[[], str] = _now,
) -> Optional[Tuple[MarkPriceObservation, ...]]:
    """One day's 5-minute-resolution mark-price series for `symbol`,
    derived from the SAME daily metrics file as fetch_open_interest_day()
    via price = sum_open_interest_value / sum_open_interest (the OI units
    cancel, recovering the venue mark). Returns None if the date is not
    available. A row with zero open interest (no valuation basis for a
    price) is skipped rather than fabricated -- it cannot yield a mark.

    Downloads the metrics file independently of fetch_open_interest_day():
    a research backfill collecting both series therefore fetches each
    small (~10 KB) file twice on the first pass, then serves both from the
    local CSV cache on every rerun. Kept deliberately simple (two focused
    functions) rather than a combined fetch, to avoid refactoring the
    already-frozen-and-tested OI path."""
    if not isinstance(day, date):
        raise HistoricalDataError(f"day must be a date, got {type(day).__name__}")
    binance_symbol = _binance_symbol(symbol)
    date_str = day.isoformat()
    zip_url = f"{_BASE_URL}/daily/metrics/{binance_symbol}/{binance_symbol}-metrics-{date_str}.zip"
    checksum_url = zip_url + ".CHECKSUM"
    source_detail = f"{binance_symbol}-metrics-{date_str}.zip (price=value/oi)"

    csv_bytes = _fetch_zip_csv(zip_url, checksum_url, transport, timeout_seconds)
    if csv_bytes is None:
        _logger.info("binance mark price unavailable for %s on %s (%s)", symbol.value, date_str, zip_url)
        return None

    ingested_at_utc = clock()
    observations = []
    reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8")))
    for row in reader:
        try:
            observed_at_utc = canonical_utc(row["create_time"].replace(" ", "T") + "Z")
            oi = Decimal(row["sum_open_interest"])
            oi_value = Decimal(row["sum_open_interest_value"])
        except (KeyError, ValueError, InvalidOperation) as exc:
            raise HistoricalDataError(f"{source_detail}: malformed row {row!r}: {exc}") from exc
        if oi <= 0:
            continue  # no valuation basis -> no derivable mark; skip, never fabricate
        price = oi_value / oi
        observations.append(MarkPriceObservation(
            symbol=symbol, observed_at_utc=observed_at_utc, value=price,
            source=_SOURCE_NAME, source_detail=source_detail, ingested_at_utc=ingested_at_utc,
        ))
    return tuple(observations)


def fetch_metrics_day(
    symbol: Symbol,
    day: date,
    *,
    transport: TransportFn = http_get,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    clock: Callable[[], str] = _now,
) -> Optional[Tuple[Tuple[OpenInterestObservation, ...], Tuple[MarkPriceObservation, ...]]]:
    """Both the open-interest series AND the derived mark-price series for
    one day, from a SINGLE download of the metrics file (vs. calling
    fetch_open_interest_day + fetch_mark_price_day, which download it
    twice). This halves the request volume of a combined backfill --
    material for a multi-year, multi-symbol collection. Returns None if
    the date is not available. Requires both the open-interest and value
    columns (every real Binance metrics file has them)."""
    if not isinstance(day, date):
        raise HistoricalDataError(f"day must be a date, got {type(day).__name__}")
    binance_symbol = _binance_symbol(symbol)
    date_str = day.isoformat()
    zip_url = f"{_BASE_URL}/daily/metrics/{binance_symbol}/{binance_symbol}-metrics-{date_str}.zip"
    checksum_url = zip_url + ".CHECKSUM"
    oi_detail = f"{binance_symbol}-metrics-{date_str}.zip"
    mark_detail = f"{oi_detail} (price=value/oi)"

    csv_bytes = _fetch_zip_csv(zip_url, checksum_url, transport, timeout_seconds)
    if csv_bytes is None:
        _logger.info("binance metrics unavailable for %s on %s (%s)", symbol.value, date_str, zip_url)
        return None

    ingested_at_utc = clock()
    oi_observations = []
    mark_observations = []
    reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8")))
    for row in reader:
        try:
            observed_at_utc = canonical_utc(row["create_time"].replace(" ", "T") + "Z")
            oi = Decimal(row["sum_open_interest"])
            oi_value = Decimal(row["sum_open_interest_value"])
        except (KeyError, ValueError, InvalidOperation) as exc:
            raise HistoricalDataError(f"{oi_detail}: malformed row {row!r}: {exc}") from exc
        oi_observations.append(OpenInterestObservation(
            symbol=symbol, observed_at_utc=observed_at_utc, value=oi,
            source=_SOURCE_NAME, source_detail=oi_detail, ingested_at_utc=ingested_at_utc,
        ))
        if oi > 0:
            mark_observations.append(MarkPriceObservation(
                symbol=symbol, observed_at_utc=observed_at_utc, value=oi_value / oi,
                source=_SOURCE_NAME, source_detail=mark_detail, ingested_at_utc=ingested_at_utc,
            ))
    return tuple(oi_observations), tuple(mark_observations)


def fetch_funding_rate_month(
    symbol: Symbol,
    year: int,
    month: int,
    *,
    transport: TransportFn = http_get,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    clock: Callable[[], str] = _now,
) -> Optional[Tuple[FundingRateObservation, ...]]:
    """One month's funding-settlement series for `symbol` (mapped to its
    Binance USDT-margined perpetual). Returns None if this month is not
    available (before the symbol's earliest coverage, or not yet
    published)."""
    if not isinstance(year, int) or isinstance(year, bool):
        raise HistoricalDataError(f"year must be an int, got {type(year).__name__}")
    if not isinstance(month, int) or isinstance(month, bool) or not (1 <= month <= 12):
        raise HistoricalDataError(f"month must be an int in [1, 12], got {month!r}")
    binance_symbol = _binance_symbol(symbol)
    month_str = f"{year:04d}-{month:02d}"
    zip_url = f"{_BASE_URL}/monthly/fundingRate/{binance_symbol}/{binance_symbol}-fundingRate-{month_str}.zip"
    checksum_url = zip_url + ".CHECKSUM"
    source_detail = f"{binance_symbol}-fundingRate-{month_str}.zip"

    csv_bytes = _fetch_zip_csv(zip_url, checksum_url, transport, timeout_seconds)
    if csv_bytes is None:
        _logger.info("binance funding rate unavailable for %s in %s (%s)", symbol.value, month_str, zip_url)
        return None

    ingested_at_utc = clock()
    observations = []
    reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8")))
    for row in reader:
        try:
            observed_at_ms = int(row["calc_time"])
            observed_at_utc = canonical_utc(
                datetime.fromtimestamp(observed_at_ms / 1000, tz=timezone.utc).isoformat()
            )
            value = Decimal(row["last_funding_rate"])
        except (KeyError, ValueError, InvalidOperation) as exc:
            raise HistoricalDataError(f"{source_detail}: malformed row {row!r}: {exc}") from exc
        observations.append(FundingRateObservation(
            symbol=symbol, observed_at_utc=observed_at_utc, value=value,
            source=_SOURCE_NAME, source_detail=source_detail, ingested_at_utc=ingested_at_utc,
        ))
    return tuple(observations)
