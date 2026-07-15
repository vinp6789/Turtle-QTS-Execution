"""Position Manager for the Turtle Execution Engine.

Owns the complete lifecycle of live positions after an order has begun
filling: creation, entry-fill accumulation, average price, realized and
unrealized PnL, T1/T2/stop/breakeven status, close, and archival. Pure
bookkeeping over caller-supplied stop/T1/T2 levels -- never calculates
conviction, position sizing, or trading signals; never touches
SigningBoundary or ExchangeAdapter directly.

Public API:
    PositionManager(store, pm_id="default")
    PositionSnapshot, ClosedLeg
    PositionLifecycleState, PositionLifecycleTrigger
"""

from .errors import (
    IllegalPositionTransitionError,
    PositionManagerError,
    PositionNotFoundError,
    PositionStateInconsistencyError,
    ReplayIntegrityError,
)
from .manager import PositionManager
from .snapshot import ClosedLeg, PositionSnapshot
from .states import LEGAL_TRIGGERS_BY_STATE, TRANSITION_TABLE, PositionLifecycleState, PositionLifecycleTrigger

__all__ = [
    "PositionManager",
    "PositionSnapshot",
    "ClosedLeg",
    "PositionLifecycleState",
    "PositionLifecycleTrigger",
    "TRANSITION_TABLE",
    "LEGAL_TRIGGERS_BY_STATE",
    "PositionManagerError",
    "PositionNotFoundError",
    "IllegalPositionTransitionError",
    "PositionStateInconsistencyError",
    "ReplayIntegrityError",
]
