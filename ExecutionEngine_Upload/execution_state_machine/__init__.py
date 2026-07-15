"""Execution State Machine for the Turtle Execution Engine.

Single source of truth for execution lifecycle state. Explicit, finite,
event-driven, deterministic. No business logic, no exchange-specific
code, no timers, no threads, no network calls -- it only validates and
durably records state transitions requested by other modules, via the
Event Store (Module 3).

Public API:
    ExecutionStateMachine(store, machine_id="default")
    State, Trigger, TransitionResult
    TRANSITION_TABLE, LEGAL_TRIGGERS_BY_STATE, TRIGGER_EVENT_TYPE
"""

from .errors import (
    ExecutionStateMachineError,
    IllegalTransitionError,
    ReplayIntegrityError,
    UnknownTriggerError,
)
from .machine import ExecutionStateMachine
from .states import State, Trigger, TransitionResult
from .transitions import LEGAL_TRIGGERS_BY_STATE, TRANSITION_TABLE, TRIGGER_EVENT_TYPE

__all__ = [
    "ExecutionStateMachine",
    "State",
    "Trigger",
    "TransitionResult",
    "TRANSITION_TABLE",
    "LEGAL_TRIGGERS_BY_STATE",
    "TRIGGER_EVENT_TYPE",
    "ExecutionStateMachineError",
    "IllegalTransitionError",
    "UnknownTriggerError",
    "ReplayIntegrityError",
]
