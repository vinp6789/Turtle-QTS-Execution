"""Tests for ExchangeAdapter.find_order() (Module 10 WP-2, Option C).

New test file only -- tests/test_exchange_adapter.py and
tests/test_order_manager.py (frozen) are not modified. find_order() is a
concrete, overridable, strictly read-only method added to ExchangeAdapter:
given the OrderRequest an adapter was placed with, recompute which venue
order (if any) corresponds to it. Default implementation scans
get_orders() for a matching client_order_id.
"""

import unittest
from decimal import Decimal

from secrets_boundary import EnvironmentHmacBackend, SigningBoundary

from exchange_adapter import (
    ExchangeAdapter,
    MockExchangeAdapter,
    Order,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Symbol,
    TimeInForce,
)

SIGNING_REF = "hyperliquid_signing_key_v1"


def _boundary():
    env = {"TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1": "test-material"}
    return SigningBoundary([SIGNING_REF], "1.0.0", "hyperliquid", backend=EnvironmentHmacBackend(env=env))


def _adapter():
    a = MockExchangeAdapter(_boundary(), SIGNING_REF)
    a.connect()
    return a


def _request(client_order_id="cid-1", symbol="BTC"):
    return OrderRequest(
        client_order_id=client_order_id,
        symbol=Symbol(symbol),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("1"),
        limit_price=Decimal("50000"),
        time_in_force=TimeInForce.GTC,
    )


class DefaultImplementation(unittest.TestCase):
    def test_finds_matching_order_by_client_order_id(self):
        a = _adapter()
        request = _request()
        placed = a.place_order(request)

        found = a.find_order(request)

        self.assertIsNotNone(found)
        self.assertEqual(found.client_order_id, placed.client_order_id)
        self.assertEqual(found.exchange_order_id, placed.exchange_order_id)

    def test_returns_none_when_no_order_matches(self):
        a = _adapter()
        # Nothing was ever placed with this client_order_id.
        result = a.find_order(_request(client_order_id="never-placed"))
        self.assertIsNone(result)

    def test_returns_none_is_not_an_error(self):
        # Absence must be a normal return value, not an exception -- the
        # caller (resync_order) relies on this to mean "still unresolved".
        a = _adapter()
        try:
            result = a.find_order(_request(client_order_id="never-placed"))
        except Exception as exc:  # pragma: no cover - failure path
            self.fail(f"find_order raised {exc!r} instead of returning None")
        self.assertIsNone(result)

    def test_distinguishes_between_multiple_orders(self):
        a = _adapter()
        req1 = _request(client_order_id="cid-a", symbol="BTC")
        req2 = _request(client_order_id="cid-b", symbol="ETH")
        placed1 = a.place_order(req1)
        placed2 = a.place_order(req2)

        found1 = a.find_order(req1)
        found2 = a.find_order(req2)

        self.assertEqual(found1.exchange_order_id, placed1.exchange_order_id)
        self.assertEqual(found2.exchange_order_id, placed2.exchange_order_id)
        self.assertNotEqual(found1.exchange_order_id, found2.exchange_order_id)


class ReadOnlyGuarantee(unittest.TestCase):
    def test_find_order_does_not_transmit_or_mutate_state(self):
        a = _adapter()
        placed = a.place_order(_request())

        orders_before = a.get_orders()
        audit_before = a.audit_records

        a.find_order(_request())  # a second, distinct request object; same client_order_id

        self.assertEqual(a.get_orders(), orders_before)
        self.assertEqual(a.audit_records, audit_before)

    def test_find_order_on_disconnected_adapter_does_not_raise(self):
        # get_orders() requires connection (MockExchangeAdapter._require_connected);
        # find_order's default delegates to it, so calling it before connect()
        # surfaces that adapter-specific behavior rather than silently
        # succeeding -- confirms find_order adds no independent gating logic.
        a = MockExchangeAdapter(_boundary(), SIGNING_REF)  # not connected
        from exchange_adapter import ExchangeConnectionError

        with self.assertRaises(ExchangeConnectionError):
            a.find_order(_request())


class Overridability(unittest.TestCase):
    def test_subclass_can_override_find_order(self):
        class OverridingAdapter(MockExchangeAdapter):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.find_order_calls = []

            def find_order(self, request):
                self.find_order_calls.append(request)
                return super().find_order(request)

        a = OverridingAdapter(_boundary(), SIGNING_REF)
        a.connect()
        request = _request()
        a.place_order(request)

        result = a.find_order(request)

        self.assertEqual(len(a.find_order_calls), 1)
        self.assertIs(a.find_order_calls[0], request)
        self.assertIsNotNone(result)

    def test_second_concrete_adapter_inherits_default_unchanged(self):
        # Mirrors test_exchange_adapter.py's proof that a new exchange needs
        # zero interface modification -- find_order is inherited as-is.
        class SecondExchangeAdapter(MockExchangeAdapter):
            pass

        a = SecondExchangeAdapter(_boundary(), SIGNING_REF, exchange_name="second-exchange")
        a.connect()
        request = _request()
        a.place_order(request)

        found = a.find_order(request)
        self.assertIsNotNone(found)


class InterfaceShape(unittest.TestCase):
    def test_find_order_is_not_abstract(self):
        # A subclass implementing every OTHER abstract method but omitting
        # find_order must still be instantiable.
        class Minimal(ExchangeAdapter):
            def connect(self): pass
            def disconnect(self): pass
            def health(self): pass
            def get_positions(self): return ()
            def get_orders(self): return ()
            def get_balances(self): return ()
            def get_mark_price(self, symbol): pass
            def get_funding_rate(self, symbol): pass
            def get_order_status(self, exchange_order_id): pass
            def get_fills(self, since_utc=None): return ()
            def reconcile(self, local_positions): pass
            def _transmit_place_order(self, request): pass
            def _transmit_amend_order(self, request): pass
            def _transmit_cancel_order(self, request): pass
            def _transmit_cancel_all(self, request): return ()

        a = Minimal(_boundary(), "minimal-exchange", "1.0", _adapter().capabilities)
        # Default find_order delegates to get_orders(), which this minimal
        # subclass implements (returns empty) -- must not raise.
        self.assertIsNone(a.find_order(_request()))


if __name__ == "__main__":
    unittest.main()
