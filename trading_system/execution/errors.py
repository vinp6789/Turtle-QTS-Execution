"""Errors for the execution layer."""

from ..errors import TradingSystemError


class ExecutionError(TradingSystemError):
    """Base for every execution-layer failure raised BY THIS MODULE
    itself (a wrong-type argument, or a TradeRequest whose RiskDecision is
    not APPROVED). A failure from OrderManager or ExchangeAdapter is never
    caught or re-wrapped here -- it propagates as-is (OrderManagerError,
    ExchangeAdapterError, etc.), so the caller sees exactly what the
    frozen modules themselves reported, not a translation of it."""
