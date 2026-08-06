"""Read-only market-data facade over an Engine's ExchangeAdapter.

Exposes only genuinely public market data (mark price, funding rate) --
never account/venue state (positions, balances, orders), which stays
sourced from PositionManager/PortfolioManager/orchestration's own
reconciliation, not re-fetched from the adapter here (fetching the same
facts through a second path would risk exactly the kind of duplicated
synchronization this layer must not introduce).

No caching, no polling, no background refresh, no timer, no thread: every
call reaches engine.adapter fresh, every time. Whether that is a real
network round-trip or an in-memory read depends entirely on which adapter
composition_root.build_engine() wired in (paper vs live) -- this facade
does not know or care which.

WHY THE NO-CACHING RULE DOES NOT FORBID HISTORICAL CANDLES (D6 context
extension). The rule above exists because "fetching the same facts through
a second path would risk exactly the kind of duplicated synchronization
this layer must not introduce" -- that hazard is specific to MUTABLE venue
state (orders, balances, positions), where a stale copy can disagree with
reconciliation and cause a wrong capital decision. A CLOSED historical
candle is immutable: it cannot change after observation, there is no second
path to disagree with, and nothing to synchronize. get_candles() therefore
remains consistent with this facade's intent. Should a future caller ever
want to cache candles, that is permitted for the same reason -- but the
in-progress bar must never be cached or returned, because it IS mutable.
"""

from typing import Tuple

from composition_root import Engine
from exchange_adapter import (
    Candle,
    CandleInterval,
    CandleSource,
    FundingRate,
    MarkPrice,
    Symbol,
)


class MarketDataView:
    """Wraps engine.adapter only. Never touches engine.order_manager,
    engine.risk_manager, engine.position_manager, or engine.portfolio_manager
    -- this facade has no path to place, amend, cancel, or evaluate
    anything."""

    def __init__(self, engine: Engine):
        if not isinstance(engine, Engine):
            raise TypeError(f"engine must be a composition_root.Engine, got {type(engine).__name__}")
        self._adapter = engine.adapter

    def get_mark_price(self, symbol: Symbol) -> MarkPrice:
        return self._adapter.get_mark_price(symbol)

    def get_funding_rate(self, symbol: Symbol) -> FundingRate:
        return self._adapter.get_funding_rate(symbol)

    def supports_candles(self) -> bool:
        """Whether the wired adapter implements the OPTIONAL CandleSource
        capability. Callers feature-detect with this rather than catching
        an exception on the hot path."""
        return isinstance(self._adapter, CandleSource)

    def get_candles(
        self, symbol: Symbol, interval: CandleInterval, limit: int
    ) -> Tuple[Candle, ...]:
        """Read-only historical OHLCV (D6 context extension).

        Guarantees, so a strategy may treat the result as a pure input:
          - CLOSED bars only -- never the in-progress bar.
          - Ordered OLDEST -> NEWEST by open_time_utc.
          - No duplicate open_time_utc.
          - Immutable (Candle is a frozen dataclass).
          - At most `limit` bars; FEWER is legal -- a caller that needs N
            bars must check len() and decline to signal when short, never
            pad, extrapolate, or assume.

        Raises TypeError when the wired adapter has no candle capability --
        loudly, never an empty tuple, because an empty tuple is
        indistinguishable from "no history" and would silently suppress
        every signal.
        """
        if not isinstance(self._adapter, CandleSource):
            raise TypeError(
                f"{type(self._adapter).__name__} does not implement CandleSource; "
                "this engine cannot serve historical candles"
            )
        return self._adapter.get_candles(symbol, interval, limit)

    def __repr__(self) -> str:
        return f"MarketDataView(adapter={self._adapter!r})"

    __str__ = __repr__
