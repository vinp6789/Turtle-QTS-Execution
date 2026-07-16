"""REST transport seam for the Hyperliquid adapter (Module 10, WP-4).

Stdlib-only (urllib.request) -- Phase A stays dependency-free. Provides
one JSON-POST primitive, `post_json`, plus `TransportFn`: the injectable
seam type a future adapter class (WP-5+) accepts as a constructor
parameter so tests can substitute a fake transport with zero real network
I/O. This mirrors the sleep_fn injection pattern already used by
exchange_adapter.retry.execute_with_retry -- a plain callable, not a new
ABC or protocol class.

No signing: this module only transmits already-fully-formed, already
JSON-serializable payloads handed to it (e.g. Decimal fields must already
be stringified by the caller, matching exchange_adapter/audit.py's
existing pattern). It has no access to SigningBoundary and never will;
request construction and signing belong to later work packages.

Error mapping: connection-level failures (timeout, DNS failure, refused
connection) are mapped directly into the closed hierarchy here, per
hyperliquid_adapter.errors' own docstring: "a timeout is the ABSENCE of a
Hyperliquid response... mapping it is a transport-layer concern."
HTTP-status-level failures (429, 5xx) are mapped via the already-committed
hyperliquid_adapter.errors.map_http_error -- reused, not reimplemented.

Security: TLS certificate verification is never disabled anywhere in this
module (urllib's default ssl context is used unmodified). No secret
material may be placed in a URL -- everything travels in the POST body,
which this function treats as opaque data to serialize; it never logs
payload contents.
"""

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from exchange_adapter import ExchangeConnectionError, ExchangeTimeoutError

from .errors import map_http_error

# Hyperliquid's documented mainnet REST base URL. Not consumed by
# post_json itself (which is endpoint-agnostic); provided for a future
# caller (WP-5+) to build full request URLs from.
DEFAULT_BASE_URL = "https://api.hyperliquid.xyz"


@dataclass(frozen=True)
class HttpResponse:
    """A successful (2xx) HTTP response, body pre-decoded from JSON."""

    status_code: int
    body: dict


TransportFn = Callable[[str, dict, float], HttpResponse]


def post_json(url: str, payload: dict, timeout_seconds: float) -> HttpResponse:
    """POST `payload` as JSON to `url` using stdlib urllib.

    `timeout_seconds` is required (no default) so every call site states
    its deadline explicitly rather than risking an unbounded wait.

    Returns HttpResponse on any 2xx status. Never returns on failure --
    raises a member of exchange_adapter's closed exception hierarchy:
      ExchangeTimeoutError    -- the request did not complete within
                                 timeout_seconds (connect or read phase).
      ExchangeConnectionError -- DNS failure, connection refused, any
                                 other socket-level failure, or a 2xx
                                 response whose body is not valid JSON.
      (via map_http_error)    -- a non-2xx HTTP status: RateLimitExceededError
                                 for 429 (with retry_after_seconds parsed
                                 from a Retry-After header if present),
                                 ExchangeConnectionError for 5xx, base
                                 ExchangeAdapterError otherwise.
    """
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status_code = response.status
            body_bytes = response.read()
    except urllib.error.HTTPError as exc:
        retry_after = exc.headers.get("Retry-After") if exc.headers is not None else None
        raise map_http_error(exc.code, retry_after_header=retry_after) from exc
    except TimeoutError as exc:
        raise ExchangeTimeoutError(f"Hyperliquid request to {url} timed out after {timeout_seconds}s") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise ExchangeTimeoutError(f"Hyperliquid request to {url} timed out after {timeout_seconds}s") from exc
        raise ExchangeConnectionError(f"Hyperliquid request to {url} failed: {exc.reason}") from exc

    try:
        parsed_body = json.loads(body_bytes)
    except json.JSONDecodeError as exc:
        raise ExchangeConnectionError(f"Hyperliquid returned a non-JSON response from {url}") from exc

    return HttpResponse(status_code=status_code, body=parsed_body)
