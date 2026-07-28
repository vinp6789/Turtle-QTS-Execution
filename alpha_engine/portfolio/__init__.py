"""Portfolio signal selection (Architecture v0.2 SS4; Alpha Engine R6 --
the minimal slice: WHICH approved opinions survive aggregation, never
HOW MUCH capital they get; sizing remains the Execution Engine's frozen
RiskManager/portfolio-construction stack's job).

Public API:
    select_signals  -- deterministic, conflict-refusing reduction of
                       approved candidates' signals (see selection.py's
                       policy docstring)
    PortfolioError  -- this sub-package's error base

Deliberately NOT built: capital allocation across hypotheses, heat/
correlation-aware weighting, and any multi-hypothesis arbitration beyond
conflict refusal -- each is named future work requiring governance-owned
policy (Architecture v0.2 SS7#2), not a silent default.
"""

from .errors import PortfolioError
from .selection import select_signals

__all__ = ["select_signals", "PortfolioError"]
