"""Closed exception hierarchy for the Exchange Adapter.

Every error a concrete adapter can encounter -- from REST, from the
websocket, or from exchange-native error codes -- must be mapped into one
of these before it crosses the adapter boundary. Callers never see an
exchange-native exception type.
"""

from typing import Optional


class ExchangeAdapterError(Exception):
    """Base exception for all Exchange Adapter failures."""


class ExchangeConnectionError(ExchangeAdapterError):
    """Raised on websocket disconnect or REST connection failure."""


class ExchangeTimeoutError(ExchangeAdapterError):
    """Raised when a REST call does not complete within its deadline."""


class ExchangeAuthenticationError(ExchangeAdapterError):
    """Raised when signing or authentication is rejected by the exchange.
    Never automatically retried."""


class RateLimitExceededError(ExchangeAdapterError):
    """Raised when the exchange signals a rate limit has been hit."""

    def __init__(self, message: str, retry_after_seconds: Optional[float] = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class OrderUnknownError(ExchangeAdapterError):
    """Raised when a query references an order the exchange has no record
    of (e.g. get_order_status for an unrecognized exchange_order_id)."""


class ExchangeRejectedOrderError(ExchangeAdapterError):
    """Raised when the exchange rejects an order/amend/cancel outright.
    This module does not interpret WHY -- only that the exchange refused."""


class StaleSnapshotError(ExchangeAdapterError):
    """Raised when a position/balance snapshot is too old to be trusted."""


class SequenceGapError(ExchangeAdapterError):
    """Raised when websocket sequence numbers show a gap, indicating one
    or more messages were missed."""


class ReconciliationMismatchError(ExchangeAdapterError):
    """Available for callers that want a hard failure on mismatch; note
    that reconcile() itself returns a ReconciliationReport rather than
    raising, so discrepancies are normalized data, not a forced exception."""
