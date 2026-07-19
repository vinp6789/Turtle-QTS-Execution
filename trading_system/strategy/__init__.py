"""Pluggable strategy interface (Milestone 5).

Public API:
    Strategy         -- the ABC every concrete strategy implements
    StrategyContext   -- read-only bundle a Strategy decides from
    TradeIntent       -- a Strategy's expressed direction/conviction,
                         never a sized or risk-checked order
    StrategyError     -- this sub-package's error base

No concrete strategy is implemented here.
"""

from .errors import StrategyError
from .interface import Strategy
from .models import StrategyContext, TradeIntent

__all__ = ["Strategy", "StrategyContext", "TradeIntent", "StrategyError"]
