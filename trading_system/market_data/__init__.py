"""Read-only market-data facade (Milestone 5).

Public API:
    MarketDataView -- wraps an Engine's ExchangeAdapter, exposing only
                      get_mark_price()/get_funding_rate(). No caching, no
                      polling, no scheduling.
"""

from .facade import MarketDataView

__all__ = ["MarketDataView"]
