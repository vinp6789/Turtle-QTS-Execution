"""Funding-rate provider (Alpha Engine Milestone 1.1; Architecture v0.2
SS4 Candidate Data Sources).

Wraps the Execution Engine's existing, already-available read-only
`trading_system.market_data.MarketDataView.get_funding_rate` -- the ONLY
Execution Engine seam this file touches. No frozen module is modified;
this consumes MarketDataView exactly as any Strategy already would.

Candidate source only (Architecture v0.2 constraint #1): funding rate is
NOT assumed to carry predictive edge here. This provider's only job is to
surface it, honestly, to a future alpha_engine.features transform
(Milestone 2.x) -- whether it is predictive is a question for the
validation gate (Milestone 4.x), not this module.

Deliberately minimal, per project direction to reach the first vertical
slice (Provider -> Feature -> Candidate -> Validation -> Evidence
Package) before adding provider sophistication: one fetch method, one
staleness policy, no caching, no retries, no background polling --
mirrors MarketDataView's own documented discipline ("No caching, no
polling, no background refresh... every call reaches engine.adapter
fresh, every time").

Fail-safe philosophy (Architecture v0.2 SS8): ANY problem -- a raised
adapter error, a stale timestamp, a nonsensical (future) timestamp --
degrades fetch() to an unavailable FundingRateReading, never a raised
exception and never a fabricated or silently-stale value.

Observability (audit finding B4): a degrade-to-unavailable is a normal,
non-exceptional outcome by design (see above) -- which is exactly why it
previously had zero trace outside the returned reading's own `reason`
field. Each degrade path now also logs a WARNING (module logger,
standard `logging`) before returning, so a fetch-layer problem is visible
in ops logs even though nothing raised and no caller is forced to
inspect every reading it receives.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Optional

from exchange_adapter import FundingRate, Symbol
from trading_system.market_data import MarketDataView

from .errors import DataSourceError

_DEFAULT_MAX_STALENESS_SECONDS = 300.0  # 5 minutes -- generous relative to
# Hyperliquid's hourly funding cadence; a caller with a tighter cadence
# requirement passes its own value.

_logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _age_seconds(fetched_at_utc: str, observed_at_utc: str) -> float:
    """Pure comparison of two ISO timestamps -- mirrors risk_manager's own
    staleness-check pattern (manager.py's _parse_utc/_age_seconds, the F4
    fix's mechanism), applied here to a single data-source reading rather
    than the whole portfolio snapshot."""
    return (_parse_utc(fetched_at_utc) - _parse_utc(observed_at_utc)).total_seconds()


@dataclass(frozen=True)
class FundingRateReading:
    """One fetch() attempt's outcome. available=False covers every
    failure mode uniformly (adapter error, stale data, nonsensical
    timestamp) -- a caller branches on `available` alone to decide
    behavior; `reason` exists purely for observability/logging, never
    for control flow."""

    symbol: Symbol
    fetched_at_utc: str
    available: bool
    value: Optional[Decimal] = None
    observed_at_utc: Optional[str] = None
    reason: Optional[str] = None

    def __post_init__(self):
        if not isinstance(self.symbol, Symbol):
            raise DataSourceError(f"FundingRateReading.symbol must be a Symbol, got {type(self.symbol).__name__}")
        if not isinstance(self.fetched_at_utc, str) or not self.fetched_at_utc.strip():
            raise DataSourceError("FundingRateReading.fetched_at_utc must be a non-empty string")
        if not isinstance(self.available, bool):
            raise DataSourceError("FundingRateReading.available must be a bool")
        if self.available:
            if not isinstance(self.value, Decimal):
                raise DataSourceError("FundingRateReading.value must be a Decimal when available is True")
            if self.observed_at_utc is None:
                raise DataSourceError("FundingRateReading.observed_at_utc must be set when available is True")
            if self.reason is not None:
                raise DataSourceError("FundingRateReading.reason must be None when available is True")
        else:
            if self.value is not None:
                raise DataSourceError(
                    "FundingRateReading.value must be None when available is False -- never fabricate a value"
                )
            if not isinstance(self.reason, str) or not self.reason.strip():
                raise DataSourceError("FundingRateReading.reason must be a non-empty string when available is False")


class FundingRateProvider:
    """One instance per (deployment, market data view). Stateless beyond
    its configuration -- every fetch() call is independent; no caching,
    no polling, no background thread."""

    def __init__(
        self,
        market_data: MarketDataView,
        max_staleness_seconds: float = _DEFAULT_MAX_STALENESS_SECONDS,
        clock: Callable[[], str] = _now,
    ):
        if not isinstance(market_data, MarketDataView):
            raise DataSourceError(
                f"market_data must be a trading_system.market_data.MarketDataView, "
                f"got {type(market_data).__name__}"
            )
        if not isinstance(max_staleness_seconds, (int, float)) or isinstance(max_staleness_seconds, bool) \
                or max_staleness_seconds <= 0:
            raise DataSourceError("max_staleness_seconds must be a positive number")
        self._market_data = market_data
        self._max_staleness_seconds = float(max_staleness_seconds)
        self._clock = clock

    def fetch(self, symbol: Symbol) -> FundingRateReading:
        """Never raises for a data problem -- every failure mode (adapter
        error, stale data, future-dated data) becomes an unavailable
        FundingRateReading instead. This is the provider-layer half of
        Architecture v0.2's fail-safe philosophy: a caller can always
        call this and get a well-formed answer, never an exception to
        handle. Still raises DataSourceError for a caller's own
        programming error (wrong argument type) -- that is a bug to
        surface immediately, not a data condition to degrade past."""
        if not isinstance(symbol, Symbol):
            raise DataSourceError(f"symbol must be a Symbol, got {type(symbol).__name__}")

        fetched_at_utc = self._clock()
        try:
            funding: FundingRate = self._market_data.get_funding_rate(symbol)
        except Exception as exc:  # noqa: BLE001 -- fail-safe: ANY read problem is "no data," never a crash
            reason = f"{type(exc).__name__}: {exc}"
            _logger.warning(
                "funding_rate fetch degraded to unavailable: symbol=%s reason=%s", symbol.value, reason,
            )
            return FundingRateReading(
                symbol=symbol, fetched_at_utc=fetched_at_utc, available=False,
                reason=reason,
            )

        age = _age_seconds(fetched_at_utc, funding.timestamp_utc)
        if age < 0:
            # Observed timestamp is in the future relative to fetch time --
            # a clock-skew/data-integrity signal, not something to trust
            # silently (mirrors this codebase's "never silently accept
            # nonsensical data" discipline, e.g. the F4 staleness fix).
            reason = (
                f"funding rate timestamp {funding.timestamp_utc!r} is in the future "
                f"relative to fetch time {fetched_at_utc!r}"
            )
            _logger.warning(
                "funding_rate fetch degraded to unavailable: symbol=%s reason=%s", symbol.value, reason,
            )
            return FundingRateReading(
                symbol=symbol, fetched_at_utc=fetched_at_utc, available=False,
                reason=reason,
            )
        if age > self._max_staleness_seconds:
            reason = (
                f"stale: funding rate observed {age:.1f}s ago, exceeds "
                f"max_staleness_seconds={self._max_staleness_seconds:.1f}"
            )
            _logger.warning(
                "funding_rate fetch degraded to unavailable: symbol=%s reason=%s", symbol.value, reason,
            )
            return FundingRateReading(
                symbol=symbol, fetched_at_utc=fetched_at_utc, available=False,
                reason=reason,
            )

        return FundingRateReading(
            symbol=symbol, fetched_at_utc=fetched_at_utc, available=True,
            value=funding.rate, observed_at_utc=funding.timestamp_utc,
        )

    def __repr__(self) -> str:
        return f"FundingRateProvider(max_staleness_seconds={self._max_staleness_seconds})"

    __str__ = __repr__
