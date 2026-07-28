"""Hyperliquid's own public `/info` `fundingHistory` endpoint -- a
SECONDARY, venue-consistent source for historical funding rate (see
docs/HISTORICAL_DATA.md for the full comparison/recommendation).

Free, no API key. Verified live against the real endpoint during this
pipeline's design:

  - Hourly funding settlements, via POST https://api.hyperliquid.xyz/info
    {"type": "fundingHistory", "coin": <SYMBOL>, "startTime": <ms>,
     "endTime": <ms>}.
  - CAPPED AT 500 RECORDS PER CALL (live-verified) -- fetch_funding_rate_
    range() below paginates by advancing startTime to the last returned
    record's time + 1 until the range is exhausted or endTime is
    reached.
  - Coverage starts only when Hyperliquid itself began trading BTC (live-
    verified: empty before ~2023-06-01) -- MUCH SHORTER than Binance's
    multi-year archive, but the one source whose values are exactly what
    this project's own live execution venue (alpha_engine.data_sources.
    funding_rate.FundingRateProvider) actually pays/receives -- no
    cross-venue basis difference to reason about.

NO OPEN INTEREST HERE (documented limitation, not an oversight):
Hyperliquid's public API has no historical open-interest endpoint --
`metaAndAssetCtxs` (already used live by alpha_engine.data_sources.
open_interest) returns only the CURRENT snapshot, and no
"openInterestHistory"-shaped type exists (live-verified: the venue
rejects it). Binance's daily "metrics" archive (historical.sources.
binance) is the recommended practical alternative -- see
docs/HISTORICAL_DATA.md.

Deliberately stdlib-only (urllib, json), with its own small, independent
POST-JSON transport (the same shape as alpha_engine.data_sources.
open_interest.post_json, kept local rather than imported so this
sub-package is independently reviewable as its own unit -- see that
module's own docstring for the identical reasoning re: not importing
hyperliquid_adapter).
"""

import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, List, Tuple

from exchange_adapter import Symbol

from ..._time import canonical_utc
from ..errors import HistoricalDataError
from ..models import FundingRateObservation

_INFO_URL = "https://api.hyperliquid.xyz/info"
_SOURCE_NAME = "hyperliquid"
_PAGE_SIZE_CAP = 500  # live-verified: fundingHistory never returns more than this per call
_DEFAULT_TIMEOUT_SECONDS = 15.0

_logger = logging.getLogger(__name__)

TransportFn = Callable[[str, Dict[str, Any], float], Any]


def post_json(url: str, payload: Dict[str, Any], timeout_seconds: float) -> Any:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        body_bytes = response.read()
    return json.loads(body_bytes)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_funding_rate_range(
    symbol: Symbol,
    start_ms: int,
    end_ms: int,
    *,
    transport: TransportFn = post_json,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    clock: Callable[[], str] = _now,
) -> Tuple[FundingRateObservation, ...]:
    """Every hourly funding settlement for `symbol` in [start_ms, end_ms)
    (both Unix epoch milliseconds), paginating past the endpoint's
    500-record-per-call cap. Returns an empty tuple if Hyperliquid has no
    coverage in this range (before the venue's own launch, or a future
    range) -- normal, not an error. Raises HistoricalDataError for a
    malformed response or a non-HTTP-404 transport failure."""
    if not isinstance(symbol, Symbol):
        raise HistoricalDataError(f"symbol must be a Symbol, got {type(symbol).__name__}")
    if not isinstance(start_ms, int) or isinstance(start_ms, bool) or start_ms < 0:
        raise HistoricalDataError("start_ms must be a non-negative int")
    if not isinstance(end_ms, int) or isinstance(end_ms, bool) or end_ms < start_ms:
        raise HistoricalDataError("end_ms must be an int >= start_ms")

    ingested_at_utc = clock()
    observations: List[FundingRateObservation] = []
    cursor = start_ms
    while cursor < end_ms:
        payload = {"type": "fundingHistory", "coin": symbol.value, "startTime": cursor, "endTime": end_ms}
        try:
            body = transport(_INFO_URL, payload, timeout_seconds)
        except urllib.error.HTTPError as exc:
            raise HistoricalDataError(f"{_INFO_URL}: HTTP {exc.code}: {exc}") from exc
        except urllib.error.URLError as exc:
            raise HistoricalDataError(f"{_INFO_URL}: transport failure: {exc}") from exc

        if not isinstance(body, list):
            raise HistoricalDataError(f"{_INFO_URL}: expected a JSON array, got {type(body).__name__}")
        if len(body) == 0:
            break

        source_detail = f"fundingHistory coin={symbol.value} startTime={cursor} endTime={end_ms}"
        for row in body:
            try:
                observed_at_utc = canonical_utc(
                    datetime.fromtimestamp(row["time"] / 1000, tz=timezone.utc).isoformat()
                )
                value = Decimal(row["fundingRate"])
            except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
                raise HistoricalDataError(f"{source_detail}: malformed row {row!r}: {exc}") from exc
            observations.append(FundingRateObservation(
                symbol=symbol, observed_at_utc=observed_at_utc, value=value,
                source=_SOURCE_NAME, source_detail=source_detail, ingested_at_utc=ingested_at_utc,
            ))

        last_time = body[-1]["time"]
        next_cursor = last_time + 1
        if len(body) < _PAGE_SIZE_CAP or next_cursor <= cursor:
            break
        cursor = next_cursor

    if len(observations) == 0:
        _logger.info(
            "hyperliquid funding history empty for %s in [%d, %d) -- likely before venue coverage",
            symbol.value, start_ms, end_ms,
        )
    return tuple(observations)
