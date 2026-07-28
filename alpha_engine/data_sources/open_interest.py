"""Open Interest provider (Alpha Engine Milestone 1.2; Architecture v0.2
SS4 Candidate Data Sources).

The second Candidate Data Source, and the first genuinely independent of
the Execution Engine. FundingRateProvider (Milestone 1.1) wraps the
already-available trading_system.market_data.MarketDataView -- a
sanctioned, existing Execution Engine seam. No such seam exists for Open
Interest anywhere in the Execution Engine, and extending the frozen
hyperliquid_adapter to add one is off the table: modifying a frozen
module requires explicit authorization this project has not given (and
was not asked for here). This module therefore talks to Hyperliquid's
public /info endpoint directly, using a small, independent, stdlib-only
HTTP client. It does NOT import hyperliquid_adapter, exchange_adapter, or
anything else from the Execution Engine's forbidden package set (see
tests/test_alpha_engine_scaffold.py's _FORBIDDEN_EXECUTION_ENGINE_
PACKAGES, which scans every alpha_engine file and would fail if this
module imported any of them). This is a deliberate, structural proof of
"the Alpha Engine remains independent from the Execution Engine," not
merely a convenience: this provider works whether or not any Execution
Engine process exists at all, and would work unchanged for a future
non-Hyperliquid venue.

Candidate source only (Architecture v0.2 constraint #1): Open Interest is
NOT assumed to carry predictive edge -- the Research repository named it
only as the highest-priority UNTESTED orthogonal source
(05_Research_Findings.md: "No Open Interest data has been loaded, tested,
or evaluated... There is no finding to report; this remains future
work"). This provider's only job is to surface it, honestly; whether it
is predictive is a question for the validation gate (Milestone 4.x), not
this module.

RESPONSE SHAPE -- VERIFIED (2026-07-22), not assumed: the parsing in
_parse_open_interest() matches Hyperliquid's public
{"type": "metaAndAssetCtxs"} /info response, confirmed two ways -- (1)
official documentation (hyperliquid.gitbook.io, "Info endpoint /
Perpetuals") and (2) a live POST to https://api.hyperliquid.xyz/info in
this session. Both confirm: a two-element array [meta, assetCtxs], where
meta["universe"][i]["name"] is the asset symbol (the same shape
venue_rules.py already relies on elsewhere in this repository for
szDecimals) and assetCtxs[i]["openInterest"] is a string-encoded decimal
open-interest figure at the same index (live response example:
assetCtxs[0] = {"funding": ..., "openInterest": "36376.50236", ...} for
universe[0] = {"name": "BTC", "szDecimals": 5, ...}). No correction to
_parse_open_interest was needed. If Hyperliquid's response shape ever
changes, only this one function needs to change -- every other piece of
this module (the provider, the reading type, its fail-safe behavior) is
independent of the exact parsing details.

No staleness policy (an honest difference from FundingRateProvider, not
an inconsistency): every fetch() call reaches the network fresh (no
caching, same "no caching... every call reaches the venue fresh"
discipline as MarketDataView and FundingRateProvider), and Hyperliquid's
metaAndAssetCtxs response carries no independent per-asset "as of"
timestamp for open interest to compare against the way funding rate
carries its own timestamp_utc. The reading's observed_at_utc IS the
fetch time, by construction -- there is nothing else to compare it
against for a staleness check.

Observability (audit finding B4): the degrade-to-unavailable path now
logs a WARNING (module logger, standard `logging`) before returning, so
a network/parse problem is visible in ops logs even though fetch() never
raises for it -- mirrors FundingRateProvider's identical B4 fix.
"""

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, Optional

from exchange_adapter import Symbol

from .errors import DataSourceError

_DEFAULT_BASE_URL = "https://api.hyperliquid.xyz"
_DEFAULT_TIMEOUT_SECONDS = 10.0

_logger = logging.getLogger(__name__)

TransportFn = Callable[[str, Dict[str, Any], float], Any]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def post_json(url: str, payload: Dict[str, Any], timeout_seconds: float) -> Any:
    """Minimal, independent stdlib HTTP POST returning the parsed JSON
    body. Deliberately NOT a reuse of hyperliquid_adapter.transport.
    post_json (see module docstring on why importing anything from
    hyperliquid_adapter is off-limits here) -- a small amount of
    duplication is the bounded cost of a genuinely independent data
    source. Raises on any failure; OpenInterestProvider.fetch() catches
    broadly, mirroring FundingRateProvider's own fail-safe discipline."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        body_bytes = response.read()
    return json.loads(body_bytes)


def _parse_open_interest(body: Any, symbol_name: str) -> Decimal:
    """See module docstring's UNVERIFIED RESPONSE SHAPE note -- this is
    the one function to correct if Hyperliquid's actual response shape
    differs from what is assumed here."""
    if not isinstance(body, list) or len(body) < 2:
        raise DataSourceError("malformed metaAndAssetCtxs response: expected a two-element array")
    meta, asset_ctxs = body[0], body[1]
    if not isinstance(meta, dict) or not isinstance(meta.get("universe"), list):
        raise DataSourceError("malformed metaAndAssetCtxs response: meta['universe'] missing or not a list")
    if not isinstance(asset_ctxs, list):
        raise DataSourceError("malformed metaAndAssetCtxs response: assetCtxs missing or not a list")

    index = None
    for i, asset in enumerate(meta["universe"]):
        if isinstance(asset, dict) and asset.get("name") == symbol_name:
            index = i
            break
    if index is None:
        raise DataSourceError(f"symbol {symbol_name!r} not found in venue universe")
    if index >= len(asset_ctxs) or not isinstance(asset_ctxs[index], dict):
        raise DataSourceError(f"no assetCtxs entry at index {index} for {symbol_name!r}")

    raw = asset_ctxs[index].get("openInterest")
    if not isinstance(raw, str):
        raise DataSourceError(f"openInterest for {symbol_name!r} is not a string: {raw!r}")
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise DataSourceError(f"openInterest value {raw!r} for {symbol_name!r} is not a valid decimal") from exc


@dataclass(frozen=True)
class OpenInterestReading:
    """Mirrors FundingRateReading's availability discipline exactly
    (Milestone 1.1): available=True requires value and observed_at_utc,
    forbids reason; available=False forbids value, requires reason."""

    symbol: Symbol
    fetched_at_utc: str
    available: bool
    value: Optional[Decimal] = None
    observed_at_utc: Optional[str] = None
    reason: Optional[str] = None

    def __post_init__(self):
        if not isinstance(self.symbol, Symbol):
            raise DataSourceError(f"OpenInterestReading.symbol must be a Symbol, got {type(self.symbol).__name__}")
        if not isinstance(self.fetched_at_utc, str) or not self.fetched_at_utc.strip():
            raise DataSourceError("OpenInterestReading.fetched_at_utc must be a non-empty string")
        if not isinstance(self.available, bool):
            raise DataSourceError("OpenInterestReading.available must be a bool")
        if self.available:
            if not isinstance(self.value, Decimal):
                raise DataSourceError("OpenInterestReading.value must be a Decimal when available is True")
            if self.observed_at_utc is None:
                raise DataSourceError("OpenInterestReading.observed_at_utc must be set when available is True")
            if self.reason is not None:
                raise DataSourceError("OpenInterestReading.reason must be None when available is True")
        else:
            if self.value is not None:
                raise DataSourceError(
                    "OpenInterestReading.value must be None when available is False -- never fabricate a value"
                )
            if not isinstance(self.reason, str) or not self.reason.strip():
                raise DataSourceError("OpenInterestReading.reason must be a non-empty string when available is False")


class OpenInterestProvider:
    """One instance per deployment. Stateless beyond its configuration --
    every fetch() call is independent; no caching, no polling, no
    background thread (same discipline as FundingRateProvider)."""

    def __init__(
        self,
        base_url: str = _DEFAULT_BASE_URL,
        transport: TransportFn = post_json,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        clock: Callable[[], str] = _now,
    ):
        if not isinstance(base_url, str) or not base_url.strip():
            raise DataSourceError("base_url must be a non-empty string")
        if not callable(transport):
            raise DataSourceError("transport must be callable")
        if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) \
                or timeout_seconds <= 0:
            raise DataSourceError("timeout_seconds must be a positive number")
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._timeout_seconds = float(timeout_seconds)
        self._clock = clock

    def fetch(self, symbol: Symbol) -> OpenInterestReading:
        """Never raises for a data problem -- any failure (network
        error, malformed response, unknown symbol) becomes an
        unavailable OpenInterestReading instead, exactly like
        FundingRateProvider.fetch(). Still raises DataSourceError for a
        caller's own programming error (wrong argument type)."""
        if not isinstance(symbol, Symbol):
            raise DataSourceError(f"symbol must be a Symbol, got {type(symbol).__name__}")

        fetched_at_utc = self._clock()
        try:
            body = self._transport(f"{self._base_url}/info", {"type": "metaAndAssetCtxs"}, self._timeout_seconds)
            value = _parse_open_interest(body, symbol.value)
        except Exception as exc:  # noqa: BLE001 -- fail-safe: ANY problem is "no data," never a crash
            reason = f"{type(exc).__name__}: {exc}"
            _logger.warning(
                "open_interest fetch degraded to unavailable: symbol=%s reason=%s", symbol.value, reason,
            )
            return OpenInterestReading(
                symbol=symbol, fetched_at_utc=fetched_at_utc, available=False,
                reason=reason,
            )

        return OpenInterestReading(
            symbol=symbol, fetched_at_utc=fetched_at_utc, available=True,
            value=value, observed_at_utc=fetched_at_utc,
        )

    def __repr__(self) -> str:
        return f"OpenInterestProvider(base_url={self._base_url!r})"

    __str__ = __repr__
