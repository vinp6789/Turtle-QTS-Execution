"""Shared error base for the Trading System layer.

Each sub-package (strategy, market_data, and future siblings) defines its
own narrow subclass of TradingSystemError, mirroring the closed-hierarchy
convention already used by composition_root and orchestration. Catching
TradingSystemError catches any trading_system failure without also
catching a frozen module's own exception hierarchy.
"""


class TradingSystemError(Exception):
    """Base for every trading_system failure, across all sub-packages."""
