"""Venue error-shape mapping for the Hyperliquid adapter (Module 10, WP-3).

Pure, deterministic translation from Hyperliquid's documented response
shapes into Module 5's closed exception hierarchy
(exchange_adapter.errors). No network calls, no adapter state -- these
functions only classify inputs already in hand. Mis-mapping is
capital-relevant: exchange_adapter.retry.RetryPolicy branches on the
returned exception's TYPE (e.g. ExchangeAuthenticationError is never
auto-retried), so every mapping decision below is justified against
Hyperliquid's documented behavior, not guessed.

Covers only request/response-level failures that prevent a call from
completing normally. It deliberately does NOT cover:
  - Order lifecycle status representation (e.g. mapping orderStatus's
    terminal status strings like "filled"/"rejected"/"marginCanceled"
    into OrderStatus) -- a rejected-but-known order is a normal Order
    with status=REJECTED, not a raised exception; that translation
    belongs to the venue codec, not error mapping.
  - ExchangeTimeoutError -- a timeout is the ABSENCE of a Hyperliquid
    response, detected at the transport layer, not a shape Hyperliquid
    itself returns; mapping it is a transport-layer concern.
  - StaleSnapshotError / SequenceGapError -- these depend on
    snapshot/websocket state this module has no access to.

Verified response shapes (Hyperliquid docs, for-developers/api/):
  - Rate limit: HTTP 429, optional `Retry-After` header.
    ("Rate limits and user limits", exchange-endpoint docs.)
  - Whole-request rejection: {"status": "err", "response": "<message>"}.
    (exchange-endpoint docs.)
  - Single-order rejection within an otherwise-accepted request:
    {"status": "ok", "response": {"type": "order",
     "data": {"statuses": [{"error": "<message>"}, ...]}}}.
    (exchange-endpoint docs.)
  - Unknown order on query: {"status": "unknownOid"}.
    (info-endpoint orderStatus docs.)
"""

from typing import Optional

from exchange_adapter import (
    ExchangeAdapterError,
    ExchangeAuthenticationError,
    ExchangeConnectionError,
    ExchangeRejectedOrderError,
    OrderUnknownError,
    RateLimitExceededError,
)

# Hyperliquid has no structured auth/signature error code -- both an
# invalid signature (ECDSA recovery yields a garbage address) and an
# unregistered/expired wallet or agent surface as the identical
# human-readable message "User or API Wallet <address> does not exist."
# This is a documented-text heuristic, not a guarantee, matching the
# heuristic-guard pattern already used in this repository (see
# config/loader.py's _looks_like_raw_secret).
_AUTH_FAILURE_SUBSTRING = "does not exist"


def is_authentication_failure_message(message: str) -> bool:
    """True if `message` indicates the request was refused for an
    invalid/expired signing identity rather than a business-logic reason.
    Case-insensitive substring match against Hyperliquid's documented
    failure text."""
    return _AUTH_FAILURE_SUBSTRING in message.lower()


def map_http_error(status_code: int, retry_after_header: Optional[str] = None) -> ExchangeAdapterError:
    """Map an HTTP-level failure status into the closed hierarchy.

    429 -> RateLimitExceededError (retry_after_seconds parsed from the
    `Retry-After` header when present and numeric).
    5xx -> ExchangeConnectionError (transient server-side failure).
    Anything else -> base ExchangeAdapterError (unexpected; not classified
    more specifically without documented meaning for that code).
    """
    if status_code == 429:
        retry_after_seconds = None
        if retry_after_header is not None:
            try:
                retry_after_seconds = float(retry_after_header)
            except (TypeError, ValueError):
                retry_after_seconds = None
        return RateLimitExceededError(
            "Hyperliquid rate limit exceeded", retry_after_seconds=retry_after_seconds
        )
    if 500 <= status_code < 600:
        return ExchangeConnectionError(f"Hyperliquid returned HTTP {status_code} (server error)")
    return ExchangeAdapterError(f"Hyperliquid returned unexpected HTTP status {status_code}")


def map_request_error(message: str) -> ExchangeAdapterError:
    """Map the `response` string of a top-level {"status": "err",
    "response": <message>} reply. This shape means the WHOLE request was
    refused (not any single order within a multi-order batch), which
    matches ExchangeRejectedOrderError's own contract: "raised when the
    exchange rejects an order/amend/cancel outright... does not interpret
    WHY -- only that the exchange refused." An auth-pattern message takes
    priority, since RetryPolicy must never auto-retry that class.
    """
    if is_authentication_failure_message(message):
        return ExchangeAuthenticationError(message)
    return ExchangeRejectedOrderError(message)


def map_order_status_error(message: str) -> ExchangeAdapterError:
    """Map a single order's {"error": <message>} entry from a
    "status":"ok" response's statuses[] array -- this specific order was
    refused while the request as a whole successfully transmitted.
    Same auth-pattern priority as map_request_error, defensively: an
    order-level slot is not documented to carry an auth failure, but
    classifying it consistently costs nothing if it ever does.
    """
    if is_authentication_failure_message(message):
        return ExchangeAuthenticationError(message)
    return ExchangeRejectedOrderError(message)


def map_unknown_oid(exchange_order_id: str) -> OrderUnknownError:
    """Map an orderStatus {"status": "unknownOid"} reply -- the venue has
    no record of this order id at all."""
    return OrderUnknownError(f"Hyperliquid has no record of order {exchange_order_id!r}")
