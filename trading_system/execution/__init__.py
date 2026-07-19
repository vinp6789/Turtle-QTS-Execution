"""Execution layer (Milestone 7): the thin adapter between an
already-approved TradeRequest and OrderManager.

Public API:
    execute_place  -- submits a NEW order for a TradeRequest whose
                       RiskDecision is APPROVED; refuses otherwise.
    execute_amend  -- amends an existing order by client_order_id.
    execute_cancel -- cancels an existing order by client_order_id.
    ExecutionResult, ExecutionOperation -- surfaced result types.
    ExecutionError -- this sub-package's error base.

Never calls RiskManager.evaluate() (only reads an already-produced
RiskDecision), never touches ExchangeAdapter directly (only OrderManager),
never computes quantity/leverage/liquidation/conviction, never reorders or
prioritizes trades, and never duplicates orchestration's synchronize()/
reconcile()/dispatch() -- this is the write/submit path; those are the
read/observe path.
"""

from .errors import ExecutionError
from .executor import execute_amend, execute_cancel, execute_place
from .models import ExecutionOperation, ExecutionResult

__all__ = [
    "execute_place",
    "execute_amend",
    "execute_cancel",
    "ExecutionResult",
    "ExecutionOperation",
    "ExecutionError",
]
