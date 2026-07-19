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
"""

from composition_root import Engine
from exchange_adapter import FundingRate, MarkPrice, Symbol


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

    def __repr__(self) -> str:
        return f"MarketDataView(adapter={self._adapter!r})"

    __str__ = __repr__
