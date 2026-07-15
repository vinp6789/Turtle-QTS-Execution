"""Order Manager for the Turtle Execution Engine.

Owns the lifecycle of orders after a strategy has already decided to
trade: deterministic id generation, outbound sequencing, and durable,
replayable order-state tracking. No exchange-specific logic, no position
sizing, no trading decisions -- communicates with the exchange only
through Module 5's typed ExchangeAdapter interface, and integrates with
Module 4's ExecutionStateMachine using its existing triggers.

Public API:
    OrderManager(adapter, store, execution_state_machine, om_id="default")
    OrderSnapshot
    OrderLifecycleState, OrderLifecycleTrigger
"""

from .errors import (
    IllegalOrderTransitionError,
    OrderManagerError,
    OrderNotFoundError,
    OrderStateInconsistencyError,
    ReplayIntegrityError,
)
from .manager import OrderManager
from .snapshot import OrderSnapshot
from .states import LEGAL_TRIGGERS_BY_STATE, TRANSITION_TABLE, OrderLifecycleState, OrderLifecycleTrigger

__all__ = [
    "OrderManager",
    "OrderSnapshot",
    "OrderLifecycleState",
    "OrderLifecycleTrigger",
    "TRANSITION_TABLE",
    "LEGAL_TRIGGERS_BY_STATE",
    "OrderManagerError",
    "OrderNotFoundError",
    "IllegalOrderTransitionError",
    "OrderStateInconsistencyError",
    "ReplayIntegrityError",
]
