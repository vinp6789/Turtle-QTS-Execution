"""Portfolio-level filtering/prioritization across multiple TradeIntents
(Milestone 6).

Public API:
    construct_trade_requests -- accepts multiple TradeIntents + a
        StrategyContext, filters/deduplicates/prioritizes them, sizes
        each survivor (trading_system.sizing), evaluates each through the
        real RiskManager, and returns a ConstructionResult. Never calls
        OrderManager.
    ConstructionResult, RejectedTrade, SkippedIntent -- result types;
        every input intent's fate is traceable in exactly one of them.
    PortfolioConstructionError -- this sub-package's error base.
"""

from .constructor import construct_trade_requests
from .errors import PortfolioConstructionError
from .models import ConstructionResult, RejectedTrade, SkippedIntent

__all__ = [
    "construct_trade_requests",
    "ConstructionResult",
    "RejectedTrade",
    "SkippedIntent",
    "PortfolioConstructionError",
]
