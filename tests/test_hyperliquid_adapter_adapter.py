"""Tests for hyperliquid_adapter.HyperliquidAdapter (Module 10, M1).

Injected fake TransportFn (dict-dispatch on the /info "type") -- zero real
network. A real temp-file EventStore backs the durable id mapping; fixture
cloids are the actual tokens minted for seeded engine ids, so resolution
exercises the true round-trip (INV-1/INV-3).
"""

import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from event_store import EventStore
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
from hyperliquid_adapter.mapping import OrderIdMapping, mint_venue_token

SIGNING_REF = "hyperliquid_signing_key_v1"
ACCOUNT_ADDRESS = "0x1111111111111111111111111111111111111111"

# Engine ids seeded into every test store, and their minted venue tokens.
ENGINE_ORDER_ID = "om:default:1:place"
ENGINE_FILL_ID = "om:default:2:place"
ORDER_TOKEN = mint_venue_token(ENGINE_ORDER_ID)
FILL_TOKEN = mint_venue_token(ENGINE_FILL_ID)
FOREIGN_TOKEN = "0x" + "f" * 32  # never seeded -> unattributable

ALL_MIDS = {"BTC": "50000.0", "ETH": "3000.0"}

CLEARINGHOUSE_STATE = {
    "assetPositions": [
        {
            "position": {
                "coin": "ETH", "entryPx": "2986.3", "liquidationPx": "2866.26936529",
                "positionValue": "100.02765", "szi": "0.0335", "unrealizedPnl": "-0.0134",
            }
        }
    ],
    "marginSummary": {"accountValue": "13109.482328"},
    "withdrawable": "13104.514502",
}

FRONTEND_OPEN_ORDERS = [
    {
        "coin": "BTC", "cloid": ORDER_TOKEN, "limitPx": "29792.0", "oid": 91490942,
        "origSz": "5.0", "reduceOnly": False, "side": "A", "sz": "5.0", "timestamp": 1681247412573,
    }
]

USER_FILLS = [
    {
        "cloid": FILL_TOKEN, "coin": "AVAX", "fee": "0.01", "oid": 90542681, "px": "18.435",
        "side": "B", "sz": "93.53", "tid": 118906512037719, "time": 1681222254710,
    }
]

ORDER_STATUS_KNOWN = {
    "status": "order",
    "order": {
        "order": {
            "coin": "BTC", "cloid": ORDER_TOKEN, "limitPx": "29792.0", "oid": 91490942,
            "origSz": "5.0", "reduceOnly": False, "side": "A", "sz": "5.0", "timestamp": 1681247412573,
        },
        "status": "open", "statusTimestamp": 1724361546645,
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
    def __init__(self, responses=None, fail_types=None):
        self.calls = []
        self._responses = dict(_RESPONSES if responses is None else responses)
        self._fail_types = fail_types or {}

    def __call__(self, url, payload, timeout_seconds):
        self.calls.append((url, payload, timeout_seconds))
        request_type = payload["type"]
        if request_type in self._fail_types:
            raise self._fail_types[request_type]
        return HttpResponse(status_code=200, body=self._responses[request_type])


def _new_store():
    fd, path = tempfile.mkstemp(suffix=".log")
    os.close(fd)
    os.unlink(path)
    store = EventStore(path)
    return store, Path(path)


def _seed(store):
    """Record the two engine-id mappings the fixtures rely on."""
    m = OrderIdMapping(ACCOUNT_ADDRESS, store)
    m.record(ENGINE_ORDER_ID)
    m.record(ENGINE_FILL_ID)


def _order_request(client_order_id="cid-1"):
    return OrderRequest(
        client_order_id=client_order_id, symbol=Symbol("BTC"), side=OrderSide.BUY, order_type=OrderType.LIMIT,
        quantity=Decimal("1"), limit_price=Decimal("50000"), time_in_force=TimeInForce.GTC,
    )


class _StoreBackedCase(unittest.TestCase):
    """Base: a seeded temp store + connected adapter, cleaned up."""

    def setUp(self):
        self.store, self.path = _new_store()
        _seed(self.store)
        self.transport = FakeTransport()
        self.adapter = HyperliquidAdapter(
            _boundary(), SIGNING_REF, ACCOUNT_ADDRESS, transport=self.transport, event_store=self.store
        )
        self.adapter.connect()

    def tearDown(self):
        self.store.close()
        if self.path.exists():
            self.path.unlink()


class ConstructorValidation(unittest.TestCase):
    def test_empty_account_address_rejected(self):
        with self.assertRaises(ValueError):
            HyperliquidAdapter(_boundary(), SIGNING_REF, "", transport=FakeTransport())

    def test_non_positive_timeout_rejected(self):
        with self.assertRaises(ValueError):
            HyperliquidAdapter(_boundary(), SIGNING_REF, ACCOUNT_ADDRESS, transport=FakeTransport(), timeout_seconds=0)

    def test_storeless_adapter_constructs_for_readonly_use(self):
        # A storeless adapter is a valid read-only instrument; its own-order
        # reads are simply empty (no mappings can exist).
        a = HyperliquidAdapter(_boundary(), SIGNING_REF, ACCOUNT_ADDRESS, transport=FakeTransport())
        a.connect()
        self.assertEqual(a.get_orders(), ())  # nothing resolvable
        self.assertEqual(a.get_fills(), ())


class ConnectionLifecycle(unittest.TestCase):
    def test_connect_gates_on_signing_boundary(self):
        a = HyperliquidAdapter(_boundary(revoked=True), SIGNING_REF, ACCOUNT_ADDRESS, transport=FakeTransport())
        with self.assertRaises(SecretRevokedError):
            a.connect()

    def test_reads_before_connect_raise(self):
        a = HyperliquidAdapter(_boundary(), SIGNING_REF, ACCOUNT_ADDRESS, transport=FakeTransport())
        with self.assertRaises(ExchangeConnectionError):
            a.get_positions()

    def test_health_reflects_disconnected(self):
        a = HyperliquidAdapter(_boundary(), SIGNING_REF, ACCOUNT_ADDRESS, transport=FakeTransport())
        self.assertEqual(a.health().connection_state, ConnectionState.DISCONNECTED)


class ReadMethods(_StoreBackedCase):
    def test_get_positions(self):
        positions = self.adapter.get_positions()
        self.assertEqual(positions[0].symbol.value, "ETH")

    def test_get_balances(self):
        self.assertEqual(self.adapter.get_balances()[0].asset.value, "USDC")

    def test_get_orders_labeled_with_engine_id(self):
        # INV-1: the resolved order carries the engine id, not the token.
        orders = self.adapter.get_orders()
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].client_order_id, ENGINE_ORDER_ID)

    def test_get_orders_excludes_foreign(self):
        # INV-3: an order whose cloid is not in our mapping is foreign.
        foreign = [dict(FRONTEND_OPEN_ORDERS[0], cloid=FOREIGN_TOKEN)]
        transport = FakeTransport(responses={**_RESPONSES, "frontendOpenOrders": foreign})
        a = HyperliquidAdapter(_boundary(), SIGNING_REF, ACCOUNT_ADDRESS, transport=transport, event_store=self.store)
        a.connect()
        self.assertEqual(a.get_orders(), ())

    def test_get_mark_price(self):
        self.assertEqual(self.adapter.get_mark_price(Symbol("BTC")).price, Decimal("50000.0"))

    def test_get_funding_rate(self):
        self.assertEqual(self.adapter.get_funding_rate(Symbol("ETH")).rate, Decimal("-0.0002"))

    def test_get_order_status_labeled_with_engine_id(self):
        order = self.adapter.get_order_status("91490942")
        self.assertEqual(order.client_order_id, ENGINE_ORDER_ID)  # INV-1

    def test_get_order_status_unknown_oid_raises(self):
        transport = FakeTransport(responses={**_RESPONSES, "orderStatus": {"status": "unknownOid"}})
        a = HyperliquidAdapter(_boundary(), SIGNING_REF, ACCOUNT_ADDRESS, transport=transport, event_store=self.store)
        a.connect()
        with self.assertRaises(OrderUnknownError):
            a.get_order_status("1")

    def test_get_fills_labeled_with_engine_id(self):
        fills = self.adapter.get_fills()
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].client_order_id, ENGINE_FILL_ID)  # INV-1

    def test_reconcile_matches(self):
        local = (Position(symbol=Symbol("ETH"), quantity=Decimal("0.0335"), entry_price=Decimal("2986.3"),
                          mark_price=Decimal("2986.3"), unrealized_pnl=Decimal("-0.0134"), liquidation_price=None),)
        self.assertTrue(self.adapter.reconcile(local).matches)


class FindOrderOverride(_StoreBackedCase):
    """INV-19: find_order locates the order by token in ANY venue state."""

    def test_find_order_returns_engine_id_labeled_order(self):
        # request carries the engine id; adapter queries orderStatus by the
        # order's token and stamps the caller's id back on.
        found = self.adapter.find_order(_order_request(client_order_id=ENGINE_ORDER_ID))
        self.assertIsNotNone(found)
        self.assertEqual(found.client_order_id, ENGINE_ORDER_ID)
        self.assertEqual(found.exchange_order_id, "91490942")

    def test_find_order_finds_a_FILLED_in_doubt_order(self):
        # The crux of INV-19: an in-doubt order that FILLED during a crash
        # is absent from open orders; only the by-token status query finds
        # it. The inherited open-orders-scan default would return None here.
        filled_status = {
            "status": "order",
            "order": {
                "order": dict(ORDER_STATUS_KNOWN["order"]["order"], sz="0.0"),  # fully filled
                "status": "filled", "statusTimestamp": 1724361546645,
            },
        }
        transport = FakeTransport(responses={**_RESPONSES, "orderStatus": filled_status})
        a = HyperliquidAdapter(_boundary(), SIGNING_REF, ACCOUNT_ADDRESS, transport=transport, event_store=self.store)
        a.connect()
        found = a.find_order(_order_request(client_order_id=ENGINE_ORDER_ID))
        self.assertIsNotNone(found)
        self.assertEqual(found.status.value, "FILLED")
        self.assertEqual(found.client_order_id, ENGINE_ORDER_ID)

    def test_find_order_unknown_returns_none_fail_safe(self):
        transport = FakeTransport(responses={**_RESPONSES, "orderStatus": {"status": "unknownOid"}})
        a = HyperliquidAdapter(_boundary(), SIGNING_REF, ACCOUNT_ADDRESS, transport=transport, event_store=self.store)
        a.connect()
        self.assertIsNone(a.find_order(_order_request(client_order_id="om:default:99:place")))

    def test_find_order_does_not_transmit_or_record(self):
        # Strictly read-only: only the orderStatus query, no append.
        events_before = self.store.event_count
        self.transport.calls.clear()
        self.adapter.find_order(_order_request(client_order_id=ENGINE_ORDER_ID))
        self.assertEqual(self.store.event_count, events_before)  # no mapping appended
        self.assertTrue(all(c[1]["type"] == "orderStatus" for c in self.transport.calls))


class FailClosedMutations(_StoreBackedCase):
    def setUp(self):
        super().setUp()
        self.transport.calls.clear()
        self.events_before = self.store.event_count

    def _assert_fail_closed(self, thunk):
        with self.assertRaises(ExchangeAdapterError):
            thunk()
        self.assertEqual(self.transport.calls, [])           # no network
        self.assertEqual(self.store.event_count, self.events_before)  # no mapping recorded

    def test_place_order_fail_closed(self):
        self._assert_fail_closed(lambda: self.adapter.place_order(_order_request()))

    def test_amend_order_fail_closed(self):
        self._assert_fail_closed(
            lambda: self.adapter.amend_order(AmendRequest(request_id="r1", exchange_order_id="1", new_quantity=Decimal("2")))
        )

    def test_cancel_order_fail_closed(self):
        self._assert_fail_closed(lambda: self.adapter.cancel_order(CancelRequest(request_id="r1", exchange_order_id="1")))

    def test_cancel_all_fail_closed(self):
        self._assert_fail_closed(lambda: self.adapter.cancel_all(CancelAllRequest(request_id="r1")))

    def test_not_reported_as_exchange_rejection(self):
        from exchange_adapter import ExchangeRejectedOrderError

        try:
            self.adapter.place_order(_order_request())
        except ExchangeRejectedOrderError:
            self.fail("fail-closed must not raise ExchangeRejectedOrderError")
        except ExchangeAdapterError:
            pass


if __name__ == "__main__":
    unittest.main()
