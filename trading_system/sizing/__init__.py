"""Position sizing (Milestone 6).

Public API:
    size_intent -- converts one TradeIntent into a fully-specified
                   risk_manager.TradeRequest, implementing
                   RiskProfileParams.sizing_mode. Pure arithmetic; never
                   calls RiskManager or OrderManager, never submits
                   anything.
    SizingError -- this sub-package's error base.
"""

from .calculator import size_intent
from .errors import SizingError

__all__ = ["size_intent", "SizingError"]
