"""Tests for hyperliquid_adapter.HyperliquidAdapter (Module 10, WP-5).

Uses an injected fake TransportFn (dict-dispatch on the /info request
"type" field) -- zero real network I/O, matching the injectable-seam
proof already established in test_hyperliquid_adapter_transport.py.
"""

import unittest
from decimal import Decimal

from secrets_boundary import EnvironmentHmacBackend, SecretRevokedError, SigningBoundary

from exchange_adapter import (
    AmendRequest,
    CancelAllRequest,
    CancelRequest,
    ConnectionState,
    ExchangeAdapterError,
    ExchangeConnectionError,
    OrderRequest,
    OrderSide,
    OrderType,
    OrderUnknownError,
    Position,
    Symbol,
    TimeInForce,
)

from hyperliquid_adapter import HttpResponse, HyperliquidAdapter

SIGNING_REF = "hyperliquid_signing_key_v1"
ACCOUNT_ADDRESS = "0x1111111111111111111111111111111111111"

ALL_MIDS = {"BTC": "50000.0", "ETH": "3000.0"}

CLEARINGHOUSE_STATE = {
    "assetPositions": [
        {
            "position": {
                "coin": "ETH",
                "entryPx": "2986.3",
                "liquidationPx": "2866.26936529",
                "positionValue": "100.02765",
                "szi": "0.0335",
                "unrealizedPnl": "-0.0134",
            }
        }
    ],
    "marginSummary": {"accountValue": "13109.482328"},
    "withdrawable": "13104.514502",
}

FRONTEND_OPEN_ORDERS = [
    {
        "coin": "BTC",
        "cloid": "0x1234567890abcdef1234567890abcdef",
        "limitPx": "29792.0",
        "oid": 91490942,
        "origSz": "5.0",
        "reduceOnly": False,
        "side": "A",
        "sz": "5.0",
        "timestamp": 1681247412573,
    }
]

USER_FILLS = [
    {
        "cloid": "0xabcdef1234567890abcdef1234567890",
        "coin": "AVAX",
        "fee": "0.01",
        "oid": 90542681,
        "px": "18.435",
        "side": "B",
        "sz": "93.53",
        "tid": 118906512037719,
        "time": 1681222254710,
    }
]

ORDER_STATUS_KNOWN = {
    "status": "order",
    "order": {
        "order": {
            "coin": "BTC",
            "cloid": "0x1234567890abcdef1234567890abcdef",
            "limitPx": "29792.0",
            "oid": 91490942,
            "origSz": "5.0",
            "reduceOnly": False,
            "side": "A",
            "sz": "5.0",
            "timestamp": 1681247412573,
        },
        "status": "open",
        "statusTimestamp": 1724361546645,
    },
}

META_AND_ASSET_CTXS = [
    {"universe": [{"name": "BTC"}, {"name": "ETH"}]},
    [{"funding": "0.0001"}, {"funding": "-0.0002"}],
]

_RESPONSES = {
    "allMids": ALL_MIDS,
    "clearinghouseState": CLEARINGHOUSE_STATE,
    "frontendOpenOrders": FRONTEND_OPEN_ORDERS,
    "userFills": USER_FILLS,
    "orderStatus": ORDER_STATUS_KNOWN,
    "metaAndAssetCtxs": META_AND_ASSET_CTXS,
}


def _boundary(revoked=False):
    env = {"TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1": "test-material"}
    boundary = SigningBoundary([SIGNING_REF], "1.0.0", "hyperliquid", backend=EnvironmentHmacBackend(env=env))
    if revoked:
        boundary.revoke(SIGNING_REF)
    return boundary


class FakeTransport:
    """Records every call; dispatches by the payload's "type" field."""

    def __init__(self, responses=None, fail_types=None):
        self.calls = []
        self._responses = dict(_RESPONSES if responses is None else responses)
        self._fail_types = fail_types or {}

    def __call__(self, url: str, payload: dict, timeout_seconds: float) -> HttpResponse:
        self.calls.append((url, payload, timeout_seconds))
        request_type = payload["type"]
        if request_type in self._fail_types:
            raise self._fail_types[request_type]
        return HttpResponse(status_code=200, body=self._responses[request_type])


def _adapter(transport=None, **kwargs):
    return HyperliquidAdapter(
        _boundary(),
        SIGNING_REF,
        ACCOUNT_ADDRESS,
        transport=transport or FakeTransport(),
        **kwargs,
    )


def _order_request():
    return OrderRequest(
        client_order_id="cid-1",
        symbol=Symbol("BTC"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("1"),
        limit_price=Decimal("50000"),
        time_in_force=TimeInForce.GTC,
    )


class ConstructorValidation(unittest.TestCase):
    def test_empty_account_address_rejected(self):
        with self.assertRaises(ValueError):
            HyperliquidAdapter(_boundary(), SIGNING_REF, "", transport=FakeTransport())

    def test_whitespace_only_account_address_rejected(self):
        with self.assertRaises(ValueError):
            HyperliquidAdapter(_boundary(), SIGNING_REF, "   ", transport=FakeTransport())

    def test_non_positive_timeout_rejected(self):
        with self.assertRaises(ValueError):
            _adapter(timeout_seconds=0)
        with self.assertRaises(ValueError):
            _adapter(timeout_seconds=-1.0)

    def test_default_capabilities_applied(self):
        a = _adapter()
        self.assertFalse(a.capabilities.supports_market_orders)
        self.assertTrue(a.capabilities.supports_limit_orders)


class ConnectionLifecycle(unittest.TestCase):
    def test_connect_gates_on_signing_boundary(self):
        a = HyperliquidAdapter(_boundary(revoked=True), SIGNING_REF, ACCOUNT_ADDRESS, transport=FakeTransport())
        with self.assertRaises(SecretRevokedError):
            a.connect()

    def test_connect_probes_all_mids_and_sets_connected(self):
        transport = FakeTransport()
        a = _adapter(transport=transport)
        health = a.connect()
        self.assertEqual(health.connection_state, ConnectionState.CONNECTED)
        self.assertTrue(any(call[1]["type"] == "allMids" for call in transport.calls))

    def test_reads_before_connect_raise(self):
        a = _adapter()
        with self.assertRaises(ExchangeConnectionError):
            a.get_positions()

    def test_disconnect_then_read_raises(self):
        a = _adapter()
        a.connect()
        a.disconnect()
        with self.assertRaises(ExchangeConnectionError):
            a.get_positions()

    def test_health_reflects_disconnected_state(self):
        a = _adapter()
        h = a.health()
        self.assertEqual(h.connection_state, ConnectionState.DISCONNECTED)
        self.assertFalse(h.rest_reachable)


class ReadMethods(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.adapter = _adapter(transport=self.transport)
        self.adapter.connect()

    def test_get_positions(self):
        positions = self.adapter.get_positions()
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0].symbol.value, "ETH")

    def test_get_balances(self):
        balances = self.adapter.get_balances()
        self.assertEqual(balances[0].asset.value, "USDC")

    def test_get_orders(self):
        orders = self.adapter.get_orders()
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].client_order_id, "0x1234567890abcdef1234567890abcdef")

    def test_get_mark_price(self):
        mp = self.adapter.get_mark_price(Symbol("BTC"))
        self.assertEqual(mp.price, Decimal("50000.0"))

    def test_get_funding_rate(self):
        fr = self.adapter.get_funding_rate(Symbol("ETH"))
        self.assertEqual(fr.rate, Decimal("-0.0002"))

    def test_get_order_status_known(self):
        order = self.adapter.get_order_status("91490942")
        self.assertEqual(order.exchange_order_id, "91490942")

    def test_get_order_status_unknown_oid_raises_order_unknown(self):
        transport = FakeTransport(responses={**_RESPONSES, "orderStatus": {"status": "unknownOid"}})
        a = _adapter(transport=transport)
        a.connect()
        with self.assertRaises(OrderUnknownError):
            a.get_order_status("1")

    def test_get_order_status_non_integer_id_raises_adapter_error(self):
        with self.assertRaises(ExchangeAdapterError):
            self.adapter.get_order_status("not-an-oid")

    def test_get_fills_unfiltered(self):
        fills = self.adapter.get_fills()
        self.assertEqual(len(fills), 1)

    def test_get_fills_filtered_by_since_utc_excludes_earlier(self):
        # USER_FILLS' single fill has time=1681222254710 -> some 2023 date;
        # filtering to "far future" must exclude it.
        fills = self.adapter.get_fills(since_utc="2999-01-01T00:00:00+00:00")
        self.assertEqual(fills, ())

    def test_reconcile_reports_no_discrepancy_when_matching(self):
        local = (
            Position(
                symbol=Symbol("ETH"), quantity=Decimal("0.0335"), entry_price=Decimal("2986.3"),
                mark_price=Decimal("2986.3"), unrealized_pnl=Decimal("-0.0134"), liquidation_price=None,
            ),
        )
        report = self.adapter.reconcile(local)
        self.assertTrue(report.matches)

    def test_reconcile_reports_discrepancy_on_mismatch(self):
        local = (
            Position(
                symbol=Symbol("ETH"), quantity=Decimal("999"), entry_price=Decimal("1"),
                mark_price=Decimal("1"), unrealized_pnl=Decimal("0"), liquidation_price=None,
            ),
        )
        report = self.adapter.reconcile(local)
        self.assertFalse(report.matches)
        self.assertEqual(len(report.discrepancies), 1)

    def test_find_order_default_works_against_real_get_orders(self):
        # WP-2's inherited default: scans get_orders() for a matching
        # client_order_id -- proves it still works once get_orders() is a
        # real, non-mock implementation.
        request = _order_request()
        # client_order_id must match FRONTEND_OPEN_ORDERS' fixture cloid.
        request = OrderRequest(
            client_order_id="0x1234567890abcdef1234567890abcdef",
            symbol=Symbol("BTC"), side=OrderSide.BUY, order_type=OrderType.LIMIT,
            quantity=Decimal("5.0"), limit_price=Decimal("29792.0"), time_in_force=TimeInForce.GTC,
        )
        found = self.adapter.find_order(request)
        self.assertIsNotNone(found)
        self.assertEqual(found.exchange_order_id, "91490942")


class FailClosedMutations(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.adapter = _adapter(transport=self.transport)
        self.adapter.connect()
        self.transport.calls.clear()  # ignore the connect() probe call

    def test_place_order_fails_closed_without_network(self):
        with self.assertRaises(ExchangeAdapterError):
            self.adapter.place_order(_order_request())
        self.assertEqual(self.transport.calls, [])  # no network call attempted

    def test_amend_order_fails_closed_without_network(self):
        with self.assertRaises(ExchangeAdapterError):
            self.adapter.amend_order(AmendRequest(request_id="r1", exchange_order_id="1", new_quantity=Decimal("2")))
        self.assertEqual(self.transport.calls, [])

    def test_cancel_order_fails_closed_without_network(self):
        with self.assertRaises(ExchangeAdapterError):
            self.adapter.cancel_order(CancelRequest(request_id="r1", exchange_order_id="1"))
        self.assertEqual(self.transport.calls, [])

    def test_cancel_all_fails_closed_without_network(self):
        with self.assertRaises(ExchangeAdapterError):
            self.adapter.cancel_all(CancelAllRequest(request_id="r1"))
        self.assertEqual(self.transport.calls, [])

    def test_fail_closed_errors_are_not_exchange_rejected_order_error(self):
        # A capital-safety distinction: the exchange never saw this
        # request, so it must not be reported as "the exchange rejected
        # it" (ExchangeRejectedOrderError), which would misrepresent what
        # happened.
        from exchange_adapter import ExchangeRejectedOrderError

        try:
            self.adapter.place_order(_order_request())
        except ExchangeRejectedOrderError:
            self.fail("fail-closed mutation must not raise ExchangeRejectedOrderError")
        except ExchangeAdapterError:
            pass


if __name__ == "__main__":
    unittest.main()
