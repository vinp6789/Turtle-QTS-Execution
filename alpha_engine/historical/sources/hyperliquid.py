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

DAILY CANDLES (`fetch_daily_candles`, Backlog 1.4): a second, independent
endpoint on the same venue -- POST https://api.hyperliquid.xyz/info
{"type": "candleSnapshot", "req": {"coin": <SYMBOL>, "interval": "1d",
"startTime": <ms>, "endTime": <ms>}}. Live-verified (2026-07-29): all
price fields are string-encoded decimals; a 368-day single request
returned every row with no pagination cap (unlike fundingHistory's
500-record cap, no paging loop is needed here); `endTime` is INCLUSIVE
of a candle whose own `t` equals `endTime` exactly (the range is
`[start_ms, end_ms]`, a CLOSED interval on both ends -- NOT the
half-open `[start_ms, end_ms)` `fetch_funding_rate_range` above uses;
copying that notation verbatim caused a real one-day-leak bug, fixed in
`pipeline.py::_collect_mark_price_hyperliquid` with a -1ms adjustment).
A repeated call against an already-closed historical day returned
byte-identical data across a 2-second gap.

STILL-FORMING CANDLES ARE NEVER RETURNED (found by independent QA
review, Backlog 1.4 M1, after the boundary fix above): the endpoint
happily returns today's not-yet-closed candle, which mutates as the day
progresses. collect_mark_price's Hyperliquid path resumes from a
high-water mark, so an in-progress candle collected once would
otherwise be permanently frozen at its partial value -- storage.
merge_and_write keeps the first-seen value on conflict, and the
high-water mark means that timestamp is never requested again once
stored. fetch_daily_candles compares each row's close time (`T`) against
`clock()` and silently drops any row whose candle has not yet closed;
this is normal (the caller may be asking for a still-in-progress day),
never an error. See test_excludes_a_still_forming_candle.

Decoded into MarkPriceObservation using the candle's CLOSE -- this is a
DAILY CLOSE, not a point-in-time mark price (derivation-scope
declaration, RD-11 A); reused as the same type because it is structurally
identical (one Decimal value per symbol per timestamp), not because the
two quantities mean the same thing. This is the DEX-first PRIMARY outcome
series for research using Hyperliquid-native data (Constitution SS4/SS6);
Binance's own mark-price derivation (historical.sources.binance) remains
the secondary cross-venue check.

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

from ..._time import canonical_utc, parse_utc
from ..errors import HistoricalDataError
from ..models import FundingRateObservation, MarkPriceObservation

_INFO_URL = "https://api.hyperliquid.xyz/info"
_SOURCE_NAME = "hyperliquid"
_PAGE_SIZE_CAP = 500  # live-verified: fundingHistory never returns more than this per call
_DEFAULT_TIMEOUT_SECONDS = 15.0

_logger = logging.getLogger(__name__)

# TransportFn: (url, payload, timeout_seconds) -> decoded JSON. Raises
# urllib.error.HTTPError for a non-2xx response, or urllib.error.URLError
# for a connection-level failure. A stall on an already-open connection
# (the read of the response itself timing out) is NOT wrapped into
# URLError by urlopen -- it surfaces as a bare TimeoutError -- so every
# call site below must catch that separately. Same contract, and the
# same fix, as sources/binance.py.
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
        except (urllib.error.URLError, TimeoutError) as exc:
            # TimeoutError (a stalled read on an already-open connection)
            # is not a urllib.error.URLError -- see the TransportFn note.
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


def fetch_daily_candles(
    symbol: Symbol,
    start_ms: int,
    end_ms: int,
    *,
    interval: str = "1d",
    transport: TransportFn = post_json,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    clock: Callable[[], str] = _now,
) -> Tuple[MarkPriceObservation, ...]:
    """Every CLOSED daily candle's CLOSE price for `symbol` in
    [start_ms, end_ms] -- a CLOSED interval (INCLUSIVE of end_ms; see
    this module's own docstring, "DAILY CANDLES", for why this differs
    from fetch_funding_rate_range's half-open range above) -- via POST
    https://api.hyperliquid.xyz/info {"type": "candleSnapshot", "req":
    {"coin": <SYMBOL>, "interval": "1d", "startTime": <ms>,
    "endTime": <ms>}}.

    `interval` defaults to "1d" -- the original and only behaviour until
    Backlog 3.6 -- and may be set to any interval the venue supports
    (e.g. "1h"). Every guarantee below holds unchanged at any interval;
    only the bucket width differs. NOTE the venue retains finer
    intervals for a SHORTER history than daily: 1h was measured
    (2026-08-05) to reach back only ~210 days, while 1d reaches the
    archive start. An out-of-retention request returns an empty tuple,
    not an error.

    A candle whose close time (`T`) has not yet passed `clock()` is
    STILL FORMING and is silently excluded -- never returned, never an
    error (see this module's docstring, "STILL-FORMING CANDLES ARE NEVER
    RETURNED", for why: an in-progress candle collected once would
    otherwise be permanently frozen at its partial value by
    collect_mark_price's high-water-mark resume).

    Returns an empty tuple if Hyperliquid has no CLOSED coverage in this
    range (before the venue's own launch, a future range, or every
    candle in range is still forming) -- normal, not an error. Raises
    HistoricalDataError for a malformed response or a non-HTTP-404
    transport failure."""
    if not isinstance(symbol, Symbol):
        raise HistoricalDataError(f"symbol must be a Symbol, got {type(symbol).__name__}")
    if not isinstance(start_ms, int) or isinstance(start_ms, bool) or start_ms < 0:
        raise HistoricalDataError("start_ms must be a non-negative int")
    if not isinstance(end_ms, int) or isinstance(end_ms, bool) or end_ms < start_ms:
        raise HistoricalDataError("end_ms must be an int >= start_ms")

    ingested_at_utc = clock()
    now_ms = int(parse_utc(ingested_at_utc).timestamp() * 1000)
    payload = {
        "type": "candleSnapshot",
        "req": {"coin": symbol.value, "interval": interval, "startTime": start_ms, "endTime": end_ms},
    }
    try:
        body = transport(_INFO_URL, payload, timeout_seconds)
    except urllib.error.HTTPError as exc:
        raise HistoricalDataError(f"{_INFO_URL}: HTTP {exc.code}: {exc}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        # TimeoutError (a stalled read on an already-open connection) is
        # not a urllib.error.URLError -- see the TransportFn note.
        raise HistoricalDataError(f"{_INFO_URL}: transport failure: {exc}") from exc

    if not isinstance(body, list):
        raise HistoricalDataError(f"{_INFO_URL}: expected a JSON array, got {type(body).__name__}")

    source_detail = f"candleSnapshot coin={symbol.value} interval={interval} startTime={start_ms} endTime={end_ms}"
    observations: List[MarkPriceObservation] = []
    for row in body:
        try:
            candle_close_ms = row["T"]
            if not isinstance(candle_close_ms, int):
                raise TypeError(f"T must be an int, got {type(candle_close_ms).__name__}")
        except (KeyError, TypeError) as exc:
            raise HistoricalDataError(f"{source_detail}: malformed row {row!r}: {exc}") from exc
        if candle_close_ms >= now_ms:
            continue  # still forming -- not yet valid historical data (see docstring)
        try:
            observed_at_utc = canonical_utc(
                datetime.fromtimestamp(row["t"] / 1000, tz=timezone.utc).isoformat()
            )
            value = Decimal(row["c"])
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise HistoricalDataError(f"{source_detail}: malformed row {row!r}: {exc}") from exc
        observations.append(MarkPriceObservation(
            symbol=symbol, observed_at_utc=observed_at_utc, value=value,
            source=_SOURCE_NAME, source_detail=source_detail, ingested_at_utc=ingested_at_utc,
        ))

    if len(observations) == 0:
        _logger.info(
            "hyperliquid daily candles empty (no closed candles) for %s in [%d, %d] "
            "-- likely before venue coverage, or every candle in range is still forming",
            symbol.value, start_ms, end_ms,
        )
    return tuple(observations)
