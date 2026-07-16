"""Concrete Hyperliquid Exchange Adapter (Module 10).

Implements the frozen Module 5 ExchangeAdapter contract for the
Hyperliquid venue. A concrete adapter owns venue transport, translation
of native venue shapes into Module 5's typed models, venue error mapping
into Module 5's closed error hierarchy, and venue request signing (via
Module 2's SigningBoundary only -- never raw key material). It owns no
business logic: it never decides whether, when, or how much to trade.

Depends only on lower-numbered frozen modules: exchange_adapter (5) and,
once the adapter class lands, secrets_boundary (2).

Build state: capability declaration and venue error mapping only. The
adapter class, codec, transport, and signing are not present yet.

Public API:
    DEFAULT_HYPERLIQUID_CAPABILITIES -- vetted default capability set
    is_authentication_failure_message -- detects Hyperliquid's auth-failure text
    map_http_error       -- HTTP-level failure -> closed hierarchy
    map_request_error    -- whole-request {"status":"err"} -> closed hierarchy
    map_order_status_error -- single-order {"error":...} -> closed hierarchy
    map_unknown_oid       -- orderStatus unknownOid -> OrderUnknownError
"""

from .capabilities import DEFAULT_HYPERLIQUID_CAPABILITIES
from .errors import (
    is_authentication_failure_message,
    map_http_error,
    map_order_status_error,
    map_request_error,
    map_unknown_oid,
)

__all__ = [
    "DEFAULT_HYPERLIQUID_CAPABILITIES",
    "is_authentication_failure_message",
    "map_http_error",
    "map_request_error",
    "map_order_status_error",
    "map_unknown_oid",
]
