"""Tests for hyperliquid_adapter.errors (Module 10, WP-3).

Each mapping is pinned to a Hyperliquid response shape verified against
the venue's documented API. Retry-safety is capital-relevant:
exchange_adapter.retry.RetryPolicy branches on exception TYPE, so a wrong
mapping (e.g. an auth failure classified as retryable) could cause a
mutation to be retried when it must not be, or vice versa.
"""

import unittest

from exchange_adapter import (
    ExchangeAdapterError,
    ExchangeAuthenticationError,
    ExchangeConnectionError,
    ExchangeRejectedOrderError,
    OrderUnknownError,
    RateLimitExceededError,
)
from exchange_adapter.retry import RetryPolicy

import hyperliquid_adapter
from hyperliquid_adapter import (
    is_authentication_failure_message,
    map_http_error,
    map_order_status_error,
    map_request_error,
    map_unknown_oid,
)


class AuthenticationFailureDetection(unittest.TestCase):
    def test_detects_documented_wallet_does_not_exist_message(self):
        # Verbatim documented failure text (Hyperliquid): both a bad
        # signature and an unregistered/expired wallet or agent surface
        # as this identical message.
        msg = "User or API Wallet 0x1234567890abcdef1234567890abcdef12345678 does not exist."
        self.assertTrue(is_authentication_failure_message(msg))

    def test_detection_is_case_insensitive(self):
        self.assertTrue(is_authentication_failure_message("USER OR API WALLET DOES NOT EXIST"))

    def test_unrelated_message_is_not_a_failure(self):
        self.assertFalse(is_authentication_failure_message("Order must have minimum value of $10."))

    def test_empty_message_is_not_a_failure(self):
        self.assertFalse(is_authentication_failure_message(""))


class RequestLevelErrorMapping(unittest.TestCase):
    """Maps {"status": "err", "response": "<message>"} -- the whole
    request was refused."""

    def test_auth_pattern_maps_to_authentication_error(self):
        exc = map_request_error("User or API Wallet 0xabc does not exist.")
        self.assertIsInstance(exc, ExchangeAuthenticationError)

    def test_non_auth_message_maps_to_rejected_order_error(self):
        exc = map_request_error("Invalid order type")
        self.assertIsInstance(exc, ExchangeRejectedOrderError)

    def test_message_is_preserved_in_exception(self):
        exc = map_request_error("Invalid order type")
        self.assertIn("Invalid order type", str(exc))

    def test_authentication_error_is_never_auto_retried(self):
        # Capital-relevant: RetryPolicy must never retry a rejected signature.
        exc = map_request_error("User or API Wallet 0xabc does not exist.")
        policy = RetryPolicy()
        from exchange_adapter.retry import Operation

        self.assertFalse(policy.should_retry(Operation.PLACE_ORDER, attempt=1, error=exc))


class OrderStatusErrorMapping(unittest.TestCase):
    """Maps a single order's {"error": "<message>"} entry within an
    otherwise-successful statuses[] array."""

    def test_maps_to_rejected_order_error(self):
        exc = map_order_status_error("Order must have minimum value of $10.")
        self.assertIsInstance(exc, ExchangeRejectedOrderError)

    def test_auth_pattern_still_takes_priority(self):
        exc = map_order_status_error("User or API Wallet 0xabc does not exist.")
        self.assertIsInstance(exc, ExchangeAuthenticationError)


class UnknownOidMapping(unittest.TestCase):
    def test_maps_to_order_unknown_error(self):
        exc = map_unknown_oid("91490942")
        self.assertIsInstance(exc, OrderUnknownError)

    def test_order_id_is_preserved_in_message(self):
        exc = map_unknown_oid("91490942")
        self.assertIn("91490942", str(exc))


class HttpErrorMapping(unittest.TestCase):
    def test_429_maps_to_rate_limit_exceeded(self):
        exc = map_http_error(429)
        self.assertIsInstance(exc, RateLimitExceededError)

    def test_429_with_retry_after_header_populates_seconds(self):
        exc = map_http_error(429, retry_after_header="30")
        self.assertEqual(exc.retry_after_seconds, 30.0)

    def test_429_without_retry_after_header_leaves_seconds_none(self):
        exc = map_http_error(429)
        self.assertIsNone(exc.retry_after_seconds)

    def test_429_with_non_numeric_retry_after_leaves_seconds_none(self):
        # Defensive: an unparseable header must not raise, just degrade
        # to "no explicit backoff hint".
        exc = map_http_error(429, retry_after_header="not-a-number")
        self.assertIsInstance(exc, RateLimitExceededError)
        self.assertIsNone(exc.retry_after_seconds)

    def test_500_maps_to_connection_error(self):
        exc = map_http_error(500)
        self.assertIsInstance(exc, ExchangeConnectionError)

    def test_503_maps_to_connection_error(self):
        exc = map_http_error(503)
        self.assertIsInstance(exc, ExchangeConnectionError)

    def test_5xx_is_retryable_for_a_read(self):
        # Capital-relevant in the other direction: a transient server
        # error on a read must remain retryable.
        exc = map_http_error(502)
        policy = RetryPolicy()
        from exchange_adapter.retry import Operation

        self.assertTrue(policy.should_retry(Operation.GET_POSITIONS, attempt=1, error=exc))

    def test_unclassified_status_maps_to_base_error(self):
        exc = map_http_error(418)
        self.assertIsInstance(exc, ExchangeAdapterError)
        self.assertNotIsInstance(exc, (ExchangeConnectionError, RateLimitExceededError))


class PackageSurface(unittest.TestCase):
    def test_all_declares_exactly_the_expected_names(self):
        self.assertEqual(
            sorted(hyperliquid_adapter.__all__),
            sorted([
                "DEFAULT_HYPERLIQUID_CAPABILITIES",
                "is_authentication_failure_message",
                "map_http_error",
                "map_request_error",
                "map_order_status_error",
                "map_unknown_oid",
                "DEFAULT_BASE_URL",
                "HttpResponse",
                "TransportFn",
                "post_json",
            ]),
        )

    def test_every_all_name_resolves(self):
        for name in hyperliquid_adapter.__all__:
            self.assertTrue(hasattr(hyperliquid_adapter, name), f"{name} in __all__ but not importable")


if __name__ == "__main__":
    unittest.main()
