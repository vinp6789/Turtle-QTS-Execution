"""State, Trigger, and TransitionResult definitions for the Execution
State Machine. Pure data -- no behavior, no business logic."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class State(Enum):
    INITIALIZING = "INITIALIZING"
    RECONCILING = "RECONCILING"
    READY = "READY"
    SIGNAL_PENDING = "SIGNAL_PENDING"
    ORDER_PENDING = "ORDER_PENDING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    POSITION_OPEN = "POSITION_OPEN"
    POSITION_CLOSING = "POSITION_CLOSING"
    FLAT = "FLAT"
    SOFT_KILL = "SOFT_KILL"
    HARD_KILL = "HARD_KILL"
    EMERGENCY_KILL = "EMERGENCY_KILL"
    STOPPED = "STOPPED"


class Trigger(Enum):
    STARTED = "STARTED"
    RECONCILED = "RECONCILED"
    RECONCILIATION_FAILED = "RECONCILIATION_FAILED"
    SIGNAL_RECEIVED = "SIGNAL_RECEIVED"
    SIGNAL_REJECTED = "SIGNAL_REJECTED"
    ORDER_PLACED = "ORDER_PLACED"
    ORDER_REJECTED = "ORDER_REJECTED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    PARTIAL_FILL_RECEIVED = "PARTIAL_FILL_RECEIVED"
    FULLY_FILLED = "FULLY_FILLED"
    REMAINDER_FILLED = "REMAINDER_FILLED"
    STOP_ADJUSTED = "STOP_ADJUSTED"
    PARTIAL_TAKE_PROFIT_FILLED = "PARTIAL_TAKE_PROFIT_FILLED"
    CLOSE_INITIATED = "CLOSE_INITIATED"
    PARTIAL_CLOSE_FILLED = "PARTIAL_CLOSE_FILLED"
    CLOSE_COMPLETED = "CLOSE_COMPLETED"
    READY_FOR_NEXT = "READY_FOR_NEXT"
    SOFT_KILL_TRIGGERED = "SOFT_KILL_TRIGGERED"
    HARD_KILL_TRIGGERED = "HARD_KILL_TRIGGERED"
    EMERGENCY_KILL_TRIGGERED = "EMERGENCY_KILL_TRIGGERED"
    FLATTEN_FILL_RECEIVED = "FLATTEN_FILL_RECEIVED"
    RESUME = "RESUME"
    SHUTDOWN = "SHUTDOWN"


@dataclass(frozen=True)
class TransitionResult:
    """The outcome of a single transition() call -- either newly recorded,
    or the replayed outcome of an earlier identical (idempotent) request.
    Immutable: callers cannot alter a result after the fact."""

    event_id: int
    trigger: Trigger
    from_state: State
    to_state: State
    timestamp_utc: str
    request_id: str
    context: Mapping[str, Any]
    replayed: bool
