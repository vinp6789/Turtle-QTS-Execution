"""Execution bridge (Architecture v0.2 SS4.4; Alpha Engine R6): the ONE
sub-package that imports the Execution Engine's public Strategy seam
(trading_system.strategy) -- the sanctioned exception every scaffold-
level coupling test documents.

Public API:
    ApprovedFundingAlphaStrategy -- concrete Strategy evaluating
                                    governance-approved funding-family
                                    specifications live via the
                                    sanctioned StrategyContext surface
    load_approved_specifications -- rebuilds typed specifications for
                                    the currently-approved, bridge-
                                    servable experiments from the
                                    registry
    STRATEGY_NAME                -- the bridge strategy's stable name
    ExecutionBridgeError         -- this sub-package's error base

Deliberately NOT done here: wiring into the app entrypoint
(AppState.create(strategies=...)). With zero genuinely-approved
hypotheses, deploying the bridge would be dead code in production; the
deployment checklist documents the wiring step for when a real approval
exists. Open Interest live emission is a documented limitation -- see
strategy.py's module docstring.
"""

from .errors import ExecutionBridgeError
from .strategy import STRATEGY_NAME, ApprovedFundingAlphaStrategy, load_approved_specifications
from .candle_strategy import CANDLE_INTERVAL, ApprovedCandleAlphaStrategy

__all__ = [
    "ApprovedFundingAlphaStrategy",
    "ApprovedCandleAlphaStrategy",
    "CANDLE_INTERVAL",
    "load_approved_specifications",
    "STRATEGY_NAME",
    "ExecutionBridgeError",
]
