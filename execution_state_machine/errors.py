"""Exceptions raised by the Execution State Machine."""


class ExecutionStateMachineError(Exception):
    """Base exception for all Execution State Machine failures."""


class IllegalTransitionError(ExecutionStateMachineError):
    """Raised when a requested trigger is not a legal edge from the
    current state. Nothing is recorded and no state change occurs."""


class UnknownTriggerError(ExecutionStateMachineError):
    """Raised when transition() is called with something other than a
    Trigger enum member."""


class ReplayIntegrityError(ExecutionStateMachineError):
    """Raised during recovery if persisted event history contains a
    transition that is not a legal edge in the current transition table,
    references an unrecognized state/trigger value, or does not follow
    on from the previously reconstructed state. Indicates corruption,
    tampering, or a mismatched transition-table version -- never raised
    during ordinary operation."""
