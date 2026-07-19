"""Errors for the sizing calculator."""

from ..errors import TradingSystemError


class SizingError(TradingSystemError):
    """Base for every sizing failure -- raised only when sizing cannot
    responsibly produce a TradeRequest (e.g. conviction_weighted sizing
    with no conviction given, vol_targeted sizing with no volatility
    given, or a degenerate zero/negative sizing distance). Never silently
    substituted with a guessed value: unknown input means sizing refuses,
    mirroring RiskManager's own "unknown equals unsafe" precedent."""
