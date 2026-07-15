"""Portfolio Manager for the Turtle Execution Engine.

Owns portfolio-level state only: cash, margin, PnL, exposure, heat, and
the set of open positions. A single-lock ledger, not a lifecycle state
machine. Never generates signals, computes conviction/indicators, or
touches SigningBoundary/ExchangeAdapter -- it consumes only normalized
facts from Position Manager, Order Manager, and the Execution State
Machine (via whatever caller aggregates them).

Public API:
    PortfolioManager(store, pm_id="default")
    PortfolioSnapshot
"""

from .errors import (
    AccountingInvariantError,
    InsufficientFundsError,
    InsufficientMarginError,
    PortfolioManagerError,
    ReplayIntegrityError,
)
from .manager import PortfolioManager
from .snapshot import PortfolioSnapshot

__all__ = [
    "PortfolioManager",
    "PortfolioSnapshot",
    "PortfolioManagerError",
    "InsufficientFundsError",
    "InsufficientMarginError",
    "AccountingInvariantError",
    "ReplayIntegrityError",
]
