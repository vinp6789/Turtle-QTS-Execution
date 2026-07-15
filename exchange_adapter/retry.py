"""Retry policy for the Exchange Adapter.

Pure and deterministic: no internal sleeping, no threads, no timers. The
caller supplies a sleep function (defaulting to time.sleep) so tests can
run this with zero real delay.

Default safety classification is deliberately conservative: EVERY
mutating operation (place/amend/cancel/cancel_all) defaults to
UNSAFE_NEVER_AUTO_RETRY. A client-side idempotency cache (idempotency.py)
only protects a retry once the ORIGINAL call is known to have completed;
it does nothing for the ambiguous case where a request timed out and it
is genuinely unknown whether the exchange received and processed it --
blindly retrying in that case could double-apply a mutation unless the
exchange itself guarantees server-side dedup on the client_order_id/
request_id, which is exchange-specific knowledge this module does not
yet have (no concrete exchange is implemented here). A future concrete
adapter that can positively verify such a guarantee for a specific
operation may supply an override; the module-provided default never
assumes it.
"""

import time
from enum import Enum
from types import MappingProxyType
from typing import Callable, Mapping, Optional, TypeVar

from .errors import (
    ExchangeAdapterError,
    ExchangeAuthenticationError,
    ExchangeConnectionError,
    ExchangeTimeoutError,
    RateLimitExceededError,
)

T = TypeVar("T")


class OperationSafety(Enum):
    SAFE_TO_RETRY = "SAFE_TO_RETRY"
    UNSAFE_NEVER_AUTO_RETRY = "UNSAFE_NEVER_AUTO_RETRY"


class Operation(Enum):
    CONNECT = "CONNECT"
    DISCONNECT = "DISCONNECT"
    HEALTH = "HEALTH"
    GET_POSITIONS = "GET_POSITIONS"
    GET_ORDERS = "GET_ORDERS"
    GET_BALANCES = "GET_BALANCES"
    GET_MARK_PRICE = "GET_MARK_PRICE"
    GET_FUNDING_RATE = "GET_FUNDING_RATE"
    PLACE_ORDER = "PLACE_ORDER"
    AMEND_ORDER = "AMEND_ORDER"
    CANCEL_ORDER = "CANCEL_ORDER"
    CANCEL_ALL = "CANCEL_ALL"
    GET_ORDER_STATUS = "GET_ORDER_STATUS"
    GET_FILLS = "GET_FILLS"
    RECONCILE = "RECONCILE"


_MUTATIONS = frozenset({Operation.PLACE_ORDER, Operation.AMEND_ORDER, Operation.CANCEL_ORDER, Operation.CANCEL_ALL})

DEFAULT_OPERATION_SAFETY: Mapping[Operation, OperationSafety] = MappingProxyType({
    op: (OperationSafety.UNSAFE_NEVER_AUTO_RETRY if op in _MUTATIONS else OperationSafety.SAFE_TO_RETRY)
    for op in Operation
})


class RetryPolicy:
    def __init__(
        self,
        max_attempts: int = 3,
        base_delay_seconds: float = 0.5,
        max_delay_seconds: float = 10.0,
        operation_safety: Optional[Mapping[Operation, OperationSafety]] = None,
    ):
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if base_delay_seconds <= 0 or max_delay_seconds <= 0:
            raise ValueError("delays must be positive")
        self._max_attempts = max_attempts
        self._base_delay = base_delay_seconds
        self._max_delay = max_delay_seconds
        self._safety = dict(DEFAULT_OPERATION_SAFETY)
        if operation_safety is not None:
            self._safety.update(operation_safety)

    def should_retry(self, operation: Operation, attempt: int, error: Exception) -> bool:
        if self._safety[operation] is OperationSafety.UNSAFE_NEVER_AUTO_RETRY:
            return False
        if attempt >= self._max_attempts:
            return False
        if isinstance(error, ExchangeAuthenticationError):
            return False  # never blindly retry a rejected signature/auth
        if isinstance(error, (ExchangeConnectionError, ExchangeTimeoutError, RateLimitExceededError)):
            return True
        return False

    def backoff_seconds(self, attempt: int, error: Optional[Exception] = None) -> float:
        if isinstance(error, RateLimitExceededError) and error.retry_after_seconds is not None:
            return error.retry_after_seconds
        return min(self._base_delay * (2 ** (attempt - 1)), self._max_delay)


def execute_with_retry(
    fn: Callable[[], T],
    operation: Operation,
    policy: RetryPolicy,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> T:
    """Run `fn`, retrying according to `policy`. `fn` must be safe to call
    more than once only if `policy` actually permits retrying `operation`
    -- this function enforces that, it does not decide it."""
    attempt = 0
    while True:
        attempt += 1
        try:
            return fn()
        except ExchangeAdapterError as exc:
            if not policy.should_retry(operation, attempt, exc):
                raise
            sleep_fn(policy.backoff_seconds(attempt, exc))
