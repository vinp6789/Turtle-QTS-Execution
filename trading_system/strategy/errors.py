"""Errors for the strategy interface."""

from ..errors import TradingSystemError


class StrategyError(TradingSystemError):
    """Base for every strategy-layer failure -- currently raised only by
    TradeIntent/StrategyContext's own structural validation
    (models.py), mirroring the frozen modules' convention of a
    dataclass raising its own module's error from __post_init__ (e.g.
    risk_manager.TradeRequest raises RiskManagerConfigurationError)."""
