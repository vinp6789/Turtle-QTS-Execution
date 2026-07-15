"""Exceptions raised by the Position Manager."""


class PositionManagerError(Exception):
    """Base exception for all Position Manager failures."""


class PositionNotFoundError(PositionManagerError):
    """Raised when an operation references a position_id this Position
    Manager instance has no record of."""


class IllegalPositionTransitionError(PositionManagerError):
    """Raised when a requested operation is not valid for a position's
    current lifecycle state."""


class PositionStateInconsistencyError(PositionManagerError):
    """Raised when an incoming update is neither a legal forward
    transition nor recognizable as a stale/duplicate/out-of-order
    notification -- a genuine contradiction requiring operator attention,
    never silently absorbed."""


class ReplayIntegrityError(PositionManagerError):
    """Raised during recovery if persisted event history is inconsistent
    with the current transition table. Indicates corruption or
    tampering, never raised during ordinary operation."""
