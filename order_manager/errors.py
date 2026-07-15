"""Exceptions raised by the Order Manager."""


class OrderManagerError(Exception):
    """Base exception for all Order Manager failures."""


class OrderNotFoundError(OrderManagerError):
    """Raised when an operation references a client_order_id this Order
    Manager instance has no record of."""


class IllegalOrderTransitionError(OrderManagerError):
    """Raised when a requested operation (amend/cancel) is not valid for
    an order's current lifecycle state."""


class OrderStateInconsistencyError(OrderManagerError):
    """Raised when an incoming update is neither a legal forward
    transition nor recognizable as a stale/duplicate/out-of-order
    notification -- a genuine contradiction requiring operator attention,
    never silently absorbed."""


class ReplayIntegrityError(OrderManagerError):
    """Raised during recovery if persisted event history is inconsistent
    with the current transition table or references an order that was
    never created. Indicates corruption or tampering, never raised during
    ordinary operation."""
