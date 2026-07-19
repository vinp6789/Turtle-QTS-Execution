"""Reporting (Milestone 9): human-readable text formatting over
monitoring's EngineSnapshot.

Public API:
    portfolio_summary       -- equity, cash, margin, exposure, heat, PnL
    execution_summary       -- what the last cycle's executions did
    cycle_summary           -- last cycle's approved/rejected/skipped/
                               executed counts
    risk_summary            -- kill-switch status + why trades were
                               rejected last cycle
    reconciliation_summary  -- current local-vs-venue reconciliation state
    ReportingError          -- this sub-package's error base

Every function returns a plain str. No HTML, no dashboard, no API server,
no UI -- and no new computation: everything displayed was already
computed by trading_system.monitoring. Depends on monitoring; monitoring
never depends on this package.
"""

from .errors import ReportingError
from .formatters import (
    cycle_summary,
    execution_summary,
    portfolio_summary,
    reconciliation_summary,
    risk_summary,
)

__all__ = [
    "portfolio_summary",
    "execution_summary",
    "cycle_summary",
    "risk_summary",
    "reconciliation_summary",
    "ReportingError",
]
