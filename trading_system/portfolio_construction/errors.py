"""Errors for portfolio construction."""

from ..errors import TradingSystemError


class PortfolioConstructionError(TradingSystemError):
    """Base for every portfolio-construction failure -- raised only for a
    caller argument-type problem. A candidate TradeIntent that cannot be
    sized or is not approved is never an exception: it is recorded in
    ConstructionResult.skipped/rejected instead (nothing is silently
    dropped, and one bad candidate never aborts the rest of the batch)."""
