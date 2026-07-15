"""Exchange Adapter interface for the Turtle Execution Engine.

Defines the abstract contract only -- no exchange-specific business
logic, no real network calls, no trading decisions. A concrete adapter
(Hyperliquid, Lighter, Variational, or any future exchange) implements
this same interface unchanged.

Public API:
    ExchangeAdapter          -- the abstract interface
    MockExchangeAdapter       -- no-network test double (testing only)
    Typed models (models.py)
    Closed error hierarchy (errors.py)
    RetryPolicy / Operation / execute_with_retry (retry.py)
    IdempotencyCache (idempotency.py)
"""

from .adapter import ExchangeAdapter
from .errors import (
    ExchangeAdapterError,
    ExchangeAuthenticationError,
    ExchangeConnectionError,
    ExchangeRejectedOrderError,
    ExchangeTimeoutError,
    OrderUnknownError,
    RateLimitExceededError,
    ReconciliationMismatchError,
    SequenceGapError,
    StaleSnapshotError,
)
from .idempotency import IdempotencyCache
from .mock_adapter import DEFAULT_MOCK_CAPABILITIES, MockExchangeAdapter
from .models import (
    AmendRequest,
    AuditRecord,
    Balance,
    CancelAllRequest,
    CancelRequest,
    ConnectionState,
    ExchangeCapabilities,
    Fill,
    FundingRate,
    HealthStatus,
    MarkPrice,
    Order,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    ReconciliationReport,
    Symbol,
    TimeInForce,
)
from .retry import DEFAULT_OPERATION_SAFETY, Operation, OperationSafety, RetryPolicy, execute_with_retry

__all__ = [
    "ExchangeAdapter",
    "MockExchangeAdapter",
    "DEFAULT_MOCK_CAPABILITIES",
    "Symbol",
    "OrderSide",
    "OrderType",
    "TimeInForce",
    "OrderStatus",
    "ConnectionState",
    "ExchangeCapabilities",
    "OrderRequest",
    "AmendRequest",
    "CancelRequest",
    "CancelAllRequest",
    "Order",
    "Fill",
    "Position",
    "Balance",
    "MarkPrice",
    "FundingRate",
    "HealthStatus",
    "ReconciliationReport",
    "AuditRecord",
    "ExchangeAdapterError",
    "ExchangeConnectionError",
    "ExchangeTimeoutError",
    "ExchangeAuthenticationError",
    "RateLimitExceededError",
    "OrderUnknownError",
    "ExchangeRejectedOrderError",
    "StaleSnapshotError",
    "SequenceGapError",
    "ReconciliationMismatchError",
    "IdempotencyCache",
    "Operation",
    "OperationSafety",
    "DEFAULT_OPERATION_SAFETY",
    "RetryPolicy",
    "execute_with_retry",
]
