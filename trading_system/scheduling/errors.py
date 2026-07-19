"""Errors for the scheduling layer."""

from ..errors import TradingSystemError


class SchedulingError(TradingSystemError):
    """Base for every scheduling failure raised BY THIS MODULE itself (a
    wrong-type argument). A failure from any coordinated stage
    (orchestration, strategy, sizing, portfolio_construction, execution,
    or a frozen module beneath them) is never caught or re-wrapped here --
    it propagates as-is, so the caller sees exactly what the failing
    stage reported."""
