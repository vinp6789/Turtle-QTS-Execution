"""WP-8 mutation-path tests through HyperliquidAdapter.

Real EventStore + real wallet signer + injected fake transport that both
records the authenticated request and returns scripted /exchange responses.
No live network. Verifies: signing gate ordering (Emergency Kill),
persist-before-transmit, fail-safe on venue/signing errors, retry semantics
(never-auto-retry), engine-id labeling on returned Orders, and that the
signature in the transmitted body recovers to the wallet address.
"""

import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from event_store import EventStore
from secrets_boundary import EnvironmentHmacBackend, SecretRevokedError, SigningBoundary

from exchange_adapter import (
    CancelAllRequest,
    CancelRequest,
    ExchangeAdapterError,
    ExchangeAuthenticationError,
    ExchangeRejectedOrderError,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Symbol,
    TimeInForce,
)

try:
    from eth_account import Account
    from eth_utils import keccak
    from hyperliquid_adapter.signing import HyperliquidWalletSigner
    import msgpack
    _HAVE = True
except ImportError:
    _HAVE = False

from hyperliquid_adapter import HttpResponse, HyperliquidAdapter
from hyperliquid_adapter.mapping import OrderIdMapping
from hyperliquid_adapter.transport import TESTNET_BASE_URL

SIGNING_REF = "hyperliquid_signing_key_v1"
WALLET_REF = "hyperliquid_wallet_key_v1"
ACCOUNT = "0x1111111111111111111111111111111111111111"
WALLET_KEY = "0x" + "22" * 32
WALLET_ENV = {"TURTLE_SECRET_HYPERLIQUID_WALLET_KEY_V1": WALLET_KEY}

META = {"universe": [{"name": "BTC", "szDecimals": 5}, {"name": "ETH", "szDecimals": 4}]}
ALL_MIDS = {"BTC": "50000", "ETH": "3000"}


def _boundary(revoked=False):
    b = SigningBoundary([SIGNING_REF], "1.0.0", "hyperliquid",
                        backend=EnvironmentHmacBackend(env={"TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1": "m"}))
    if revoked:
        b.revoke(SIGNING_REF)
    return b


def _order_status_body(oid, cloid, coin="BTC", status="open", sz="5.0", origSz="5.0"):
    return {"status": "order", "order": {
        "order": {"coin": coin, "cloid": cloid, "limitPx": "29792.0", "oid": oid, "origSz": origSz,
                  "reduceOnly": False, "side": "A", "sz": sz, "timestamp": 1},
        "status": status, "statusTimestamp": 1}}


class ScriptedTransport:
    """Serves /info by request type and /exchange with a scripted result;
    records every /exchange call for signature/nonce inspection."""

    def __init__(self, exchange_result=None, info_overrides=None):
        self.exchange_calls = []
        self._exchange_result = exchange_result or {
            "status": "ok", "response": {"type": "order", "data": {"statuses": [{"resting": {"oid": 777}}]}}}
        self._info = {"meta": META, "allMids": ALL_MIDS, "frontendOpenOrders": [], "userFills": []}
        if info_overrides:
            self._info.update(info_overrides)

    def __call__(self, url, payload, timeout_seconds):
        if url.endswith("/exchange"):
            self.exchange_calls.append(payload)
            body = self._exchange_result() if callable(self._exchange_result) else self._exchange_result
            return HttpResponse(status_code=200, body=body)
        # An /info entry may be a callable(payload) -> body, so a single type
        # (e.g. orderStatus) can answer differently by query key -- the venue
        # returns the historical order when queried by numeric oid and the
        # live replacement when queried by cloid (used by the amend tests).
        entry = self._info[payload["type"]]
        body = entry(payload) if callable(entry) else entry
        return HttpResponse(status_code=200, body=body)


def _adapter(transport, connect=True):
    fd, p = tempfile.mkstemp(suffix=".log")
    os.close(fd)
    os.unlink(p)
    store = EventStore(p)
    signer = HyperliquidWalletSigner(WALLET_REF, is_mainnet=False, env=WALLET_ENV)
    a = HyperliquidAdapter(_boundary(), SIGNING_REF, ACCOUNT, transport=transport,
                           event_store=store, wallet_signer=signer, base_url=TESTNET_BASE_URL)
    if connect:
        a.connect()
    return a, store, Path(p)


def _order():
    return OrderRequest(client_order_id="om:default:1:place", symbol=Symbol("BTC"), side=OrderSide.BUY,
                        order_type=OrderType.LIMIT, quantity=Decimal("5.0"),
                        limit_price=Decimal("29792.0"), time_in_force=TimeInForce.GTC)


@unittest.skipUnless(_HAVE, "eth-account/msgpack not installed")
class PlaceOrder(unittest.TestCase):
    def setUp(self):
        self.t = ScriptedTransport()
        self.a, self.store, self.path = _adapter(self.t)

    def tearDown(self):
        self.store.close()
        self.path.unlink()

    def test_resting_order_returns_acknowledged_with_engine_id(self):
        order = self.a.place_order(_order())
        self.assertEqual(order.status, OrderStatus.ACKNOWLEDGED)
        self.assertEqual(order.exchange_order_id, "777")
        self.assertEqual(order.client_order_id, "om:default:1:place")  # INV-1: engine id

    def test_signature_in_body_recovers_to_wallet_address(self):
        self.a.place_order(_order())
        body = self.t.exchange_calls[-1]
        # recompute connectionId from the transmitted action+nonce and verify
        from hyperliquid_adapter import action_codec
        conn = action_codec.connection_id(body["action"], body["nonce"])
        typed = {"domain": {"name": "Exchange", "version": "1", "chainId": 1337,
                            "verifyingContract": "0x" + "00" * 20},
                 "types": {"Agent": [{"name": "source", "type": "string"}, {"name": "connectionId", "type": "bytes32"}],
                           "EIP712Domain": [{"name": "name", "type": "string"}, {"name": "version", "type": "string"},
                                            {"name": "chainId", "type": "uint256"}, {"name": "verifyingContract", "type": "address"}]},
                 "primaryType": "Agent", "message": {"source": "b", "connectionId": conn}}
        from eth_account.messages import encode_typed_data
        sig = body["signature"]
        raw = int(sig["r"], 16).to_bytes(32, "big") + int(sig["s"], 16).to_bytes(32, "big") + bytes([sig["v"]])
        rec = Account.recover_message(encode_typed_data(full_message=typed), signature=raw)
        self.assertEqual(rec, Account.from_key(WALLET_KEY).address)

    def test_transmitted_cloid_is_the_recorded_token(self):
        self.a.place_order(_order())
        body = self.t.exchange_calls[-1]
        cloid = body["action"]["orders"][0]["c"]
        # matches the durable mapping token for the engine id
        from hyperliquid_adapter.mapping import mint_venue_token
        self.assertEqual(cloid, mint_venue_token("om:default:1:place"))

    def test_persist_before_transmit(self):
        # A mapping event is durable in the store before the /exchange call.
        events_before = self.store.event_count
        self.a.place_order(_order())
        self.assertGreater(self.store.event_count, events_before)  # mapping recorded

    def test_market_order_rejected(self):
        req = OrderRequest(client_order_id="cid", symbol=Symbol("BTC"), side=OrderSide.BUY,
                           order_type=OrderType.MARKET, quantity=Decimal("1"),
                           time_in_force=TimeInForce.IOC)
        with self.assertRaises(ExchangeRejectedOrderError):
            self.a.place_order(req)
        self.assertEqual(self.t.exchange_calls, [])  # never transmitted

    def test_venue_order_error_maps_to_rejection(self):
        t = ScriptedTransport(exchange_result={"status": "ok", "response": {"type": "order",
                              "data": {"statuses": [{"error": "Order must have minimum value of $10."}]}}})
        a, store, path = _adapter(t)
        try:
            with self.assertRaises(ExchangeRejectedOrderError):
                a.place_order(_order())
        finally:
            store.close(); path.unlink()

    def test_whole_request_err_maps_to_rejection(self):
        t = ScriptedTransport(exchange_result={"status": "err", "response": "Insufficient margin"})
        a, store, path = _adapter(t)
        try:
            with self.assertRaises(ExchangeRejectedOrderError):
                a.place_order(_order())
        finally:
            store.close(); path.unlink()


@unittest.skipUnless(_HAVE, "eth-account/msgpack not installed")
class EmergencyKillGate(unittest.TestCase):
    def test_revoked_signing_boundary_blocks_before_transmit(self):
        t = ScriptedTransport()
        fd, p = tempfile.mkstemp(suffix=".log"); os.close(fd); os.unlink(p)
        store = EventStore(p)
        signer = HyperliquidWalletSigner(WALLET_REF, is_mainnet=False, env=WALLET_ENV)
        a = HyperliquidAdapter(_boundary(revoked=True), SIGNING_REF, ACCOUNT, transport=t,
                               event_store=store, wallet_signer=signer, base_url=TESTNET_BASE_URL)
        a._connected = True  # bypass connect (which would also be gated)
        try:
            with self.assertRaises(SecretRevokedError):
                a.place_order(_order())
            self.assertEqual(t.exchange_calls, [])          # nothing transmitted
        finally:
            store.close(); Path(p).unlink()

    def test_revoked_wallet_signer_blocks_transmit(self):
        t = ScriptedTransport()
        a, store, path = _adapter(t)
        try:
            a._wallet_signer.revoke()
            with self.assertRaises(ExchangeAuthenticationError):
                a.place_order(_order())
            self.assertEqual(t.exchange_calls, [])
        finally:
            store.close(); path.unlink()

    def test_no_signer_fails_closed(self):
        t = ScriptedTransport()
        a = HyperliquidAdapter(_boundary(), SIGNING_REF, ACCOUNT, transport=t)
        a.connect()
        with self.assertRaises(ExchangeAdapterError):
            a.place_order(_order())
        self.assertEqual(t.exchange_calls, [])


@unittest.skipUnless(_HAVE, "eth-account/msgpack not installed")
class CancelPaths(unittest.TestCase):
    def test_cancel_order_resolves_asset_and_returns_cancelled(self):
        cloid = None
        t = ScriptedTransport(
            exchange_result={"status": "ok", "response": {"type": "cancel", "data": {"statuses": ["success"]}}},
            info_overrides={"orderStatus": _order_status_body(777, cloid="0x" + "ab" * 16)},
        )
        # seed the mapping so the order's cloid resolves to the engine id
        a, store, path = _adapter(t)
        try:
            from hyperliquid_adapter.mapping import mint_venue_token, OrderIdMapping
            # make orderStatus cloid match a recorded engine id
            eng = "om:default:9:place"
            tok = OrderIdMapping(ACCOUNT, store).record(eng)
            t._info["orderStatus"] = _order_status_body(777, cloid=tok)
            # rebuild adapter so its mapping picks up the recorded token
            a2 = HyperliquidAdapter(_boundary(), SIGNING_REF, ACCOUNT, transport=t,
                                    event_store=store, base_url=TESTNET_BASE_URL,
                                    wallet_signer=HyperliquidWalletSigner(WALLET_REF, is_mainnet=False, env=WALLET_ENV))
            a2.connect()
            result = a2.cancel_order(CancelRequest(request_id="r1", exchange_order_id="777"))
            self.assertEqual(result.status, OrderStatus.CANCELLED)
            self.assertEqual(result.client_order_id, eng)  # INV-1
        finally:
            store.close(); path.unlink()

    def test_cancel_all_with_no_open_orders_transmits_nothing(self):
        t = ScriptedTransport(info_overrides={"frontendOpenOrders": []})
        a, store, path = _adapter(t)
        try:
            self.assertEqual(a.cancel_all(CancelAllRequest(request_id="r1")), ())
            self.assertEqual(t.exchange_calls, [])  # nothing to cancel -> no transmit
        finally:
            store.close(); path.unlink()


@unittest.skipUnless(_HAVE, "eth-account/msgpack not installed")
class CancelAllConfirmation(unittest.TestCase):
    """Regression for the WP-8 audit finding: cancel_all must report an order
    cancelled ONLY when the venue affirmatively confirmed it. A partial
    response (fewer statuses than cancels) must NOT be treated as
    confirmation."""

    def _two_open_orders_adapter(self, cancel_statuses):
        fd, p = tempfile.mkstemp(suffix=".log")
        os.close(fd)
        os.unlink(p)
        store = EventStore(p)
        m = OrderIdMapping(ACCOUNT, store)
        tok1 = m.record("om:default:1:place")
        tok2 = m.record("om:default:2:place")
        open_orders = [
            {"coin": "BTC", "cloid": tok1, "limitPx": "1", "oid": 101, "origSz": "1",
             "reduceOnly": False, "side": "A", "sz": "1", "timestamp": 1},
            {"coin": "BTC", "cloid": tok2, "limitPx": "1", "oid": 102, "origSz": "1",
             "reduceOnly": False, "side": "A", "sz": "1", "timestamp": 1},
        ]
        cancel_body = {"status": "ok", "response": {"type": "cancel", "data": {"statuses": cancel_statuses}}}
        t = ScriptedTransport(exchange_result=cancel_body, info_overrides={"frontendOpenOrders": open_orders})
        signer = HyperliquidWalletSigner(WALLET_REF, is_mainnet=False, env=WALLET_ENV)
        a = HyperliquidAdapter(_boundary(), SIGNING_REF, ACCOUNT, transport=t, event_store=store,
                               wallet_signer=signer, base_url=TESTNET_BASE_URL)
        a.connect()
        return a, store, Path(p)

    def test_partial_response_does_not_report_unconfirmed_as_cancelled(self):
        # 2 cancellable orders, venue confirms only ONE -> only one reported.
        # (This test FAILS against the pre-fix code, which reported both.)
        a, store, path = self._two_open_orders_adapter(cancel_statuses=["success"])
        try:
            result = a.cancel_all(CancelAllRequest(request_id="r1"))
            self.assertEqual(len(result), 1)
            self.assertEqual({o.exchange_order_id for o in result}, {"101"})
            self.assertNotIn("102", {o.exchange_order_id for o in result})  # unconfirmed, not reported
        finally:
            store.close(); path.unlink()

    def test_all_confirmed_reports_all(self):
        a, store, path = self._two_open_orders_adapter(cancel_statuses=["success", "success"])
        try:
            result = a.cancel_all(CancelAllRequest(request_id="r1"))
            self.assertEqual({o.exchange_order_id for o in result}, {"101", "102"})
            for o in result:
                self.assertEqual(o.status, OrderStatus.CANCELLED)
        finally:
            store.close(); path.unlink()

    def test_per_order_error_is_skipped(self):
        a, store, path = self._two_open_orders_adapter(
            cancel_statuses=[{"error": "Order was never placed"}, "success"])
        try:
            result = a.cancel_all(CancelAllRequest(request_id="r1"))
            self.assertEqual({o.exchange_order_id for o in result}, {"102"})  # only the 'success'
        finally:
            store.close(); path.unlink()

    def test_empty_statuses_reports_nothing(self):
        a, store, path = self._two_open_orders_adapter(cancel_statuses=[])
        try:
            self.assertEqual(a.cancel_all(CancelAllRequest(request_id="r1")), ())
        finally:
            store.close(); path.unlink()

    def test_malformed_present_status_is_not_reported_cancelled(self):
        # Phase 2.4: a present-but-unrecognized status (not "success", not an
        # error dict) is NOT affirmative confirmation -> must be skipped.
        for bad in (123, None, "cancelled", {"ok": True}, ["nested"]):
            a, store, path = self._two_open_orders_adapter(cancel_statuses=[bad, "success"])
            try:
                result = a.cancel_all(CancelAllRequest(request_id="r1"))
                self.assertEqual({o.exchange_order_id for o in result}, {"102"},
                                 f"malformed status {bad!r} must not be reported cancelled")
            finally:
                store.close(); path.unlink()


@unittest.skipUnless(_HAVE, "eth-account/msgpack not installed")
class AmendOrder(unittest.TestCase):
    """Adapter-level amend_order integration (Phase 2.1)."""

    def _adapter_with_open_order(self, modify_result=None, open_after_modify=None):
        fd, p = tempfile.mkstemp(suffix=".log"); os.close(fd); os.unlink(p)
        store = EventStore(p)
        eng = "om:default:5:place"
        tok = OrderIdMapping(ACCOUNT, store).record(eng)
        # Live-venue behavior for modify = cancel+replace (empirically confirmed
        # on testnet): the adapter first reads the pre-modify order by NUMERIC
        # oid 555; after the modify, orderStatus(cloid) still resolves to the
        # now-CANCELLED ORIGINAL (555) -- so it MUST NOT be used to find the
        # replacement -- while frontendOpenOrders shows the LIVE replacement
        # under the same cloid with a NEW oid (556). The adapter must resolve
        # the replacement from frontendOpenOrders and return the new oid.
        pre = _order_status_body(555, cloid=tok, coin="BTC", sz="5.0", origSz="5.0")
        stale = _order_status_body(555, cloid=tok, coin="BTC", sz="5.0", origSz="5.0", status="canceled")

        def order_status(payload):
            # cloid query returns the STALE cancelled original (the trap);
            # numeric-oid query returns the pre-modify order.
            return stale if str(payload.get("oid")).startswith("0x") else pre

        if open_after_modify is None:
            open_after_modify = [{"coin": "BTC", "cloid": tok, "limitPx": "29792.0", "oid": 556,
                                  "origSz": "8.0", "reduceOnly": False, "side": "A", "sz": "8.0",
                                  "timestamp": 1}]
        exch = modify_result or {"status": "ok", "response": {"type": "default"}}
        t = ScriptedTransport(exchange_result=exch,
                              info_overrides={"orderStatus": order_status,
                                              "frontendOpenOrders": open_after_modify})
        signer = HyperliquidWalletSigner(WALLET_REF, is_mainnet=False, env=WALLET_ENV)
        a = HyperliquidAdapter(_boundary(), SIGNING_REF, ACCOUNT, transport=t, event_store=store,
                               wallet_signer=signer, base_url=TESTNET_BASE_URL)
        a.connect()
        return a, store, Path(p), eng, t

    def test_amend_new_quantity_builds_modify_and_returns_updated_order(self):
        a, store, path, eng, t = self._adapter_with_open_order()
        try:
            from exchange_adapter import AmendRequest
            result = a.amend_order(AmendRequest(request_id="a1", exchange_order_id="555",
                                                new_quantity=Decimal("8.0")))
            self.assertEqual(result.client_order_id, eng)     # engine id preserved (INV-1)
            self.assertEqual(result.quantity, Decimal("8.0"))  # new size reflected
            # the transmitted action is a 'modify' carrying the resolved cloid,
            # keyed on the OLD oid (that's what the venue modifies).
            body = t.exchange_calls[-1]
            self.assertEqual(body["action"]["type"], "modify")
            self.assertEqual(body["action"]["oid"], 555)
            from hyperliquid_adapter.mapping import mint_venue_token
            self.assertEqual(body["action"]["order"]["c"], mint_venue_token(eng))
        finally:
            store.close(); path.unlink()

    def test_amend_returns_live_replacement_oid_from_open_orders_not_stale_cloid_lookup(self):
        # Core regression for the live defect: the returned Order must carry the
        # LIVE replacement oid (556, from frontendOpenOrders), NOT the obsolete
        # pre-modify oid (555) that orderStatus(cloid) still resolves to.
        a, store, path, eng, t = self._adapter_with_open_order()
        try:
            from exchange_adapter import AmendRequest
            result = a.amend_order(AmendRequest(request_id="a1", exchange_order_id="555",
                                                new_quantity=Decimal("8.0")))
            self.assertEqual(result.exchange_order_id, "556")      # live replacement oid
            self.assertNotEqual(result.exchange_order_id, "555")   # obsolete/cancelled oid not returned
        finally:
            store.close(); path.unlink()

    def test_amend_raises_if_replacement_not_in_open_orders_rather_than_returning_stale_oid(self):
        # Fail-safe: if no open order for the engine id can be found after a
        # successful modify, amend must RAISE, never return the obsolete oid.
        a, store, path, eng, t = self._adapter_with_open_order(open_after_modify=[])
        try:
            from exchange_adapter import AmendRequest
            with self.assertRaises(ExchangeAdapterError):
                a.amend_order(AmendRequest(request_id="a1", exchange_order_id="555",
                                           new_quantity=Decimal("8.0")))
        finally:
            store.close(); path.unlink()

    def test_amend_gates_on_signing_boundary(self):
        # A revoked signing_key_ref blocks the amend before any transmission.
        fd, p = tempfile.mkstemp(suffix=".log"); os.close(fd); os.unlink(p)
        store = EventStore(p)
        t = ScriptedTransport(info_overrides={"orderStatus": _order_status_body(555, cloid="0x" + "ab" * 16)})
        signer = HyperliquidWalletSigner(WALLET_REF, is_mainnet=False, env=WALLET_ENV)
        a = HyperliquidAdapter(_boundary(revoked=True), SIGNING_REF, ACCOUNT, transport=t, event_store=store,
                               wallet_signer=signer, base_url=TESTNET_BASE_URL)
        a._connected = True
        try:
            from exchange_adapter import AmendRequest
            with self.assertRaises(SecretRevokedError):
                a.amend_order(AmendRequest(request_id="a1", exchange_order_id="555", new_quantity=Decimal("8")))
            self.assertEqual(t.exchange_calls, [])
        finally:
            store.close(); Path(p).unlink()

    def test_amend_venue_error_maps(self):
        a, store, path, eng, t = self._adapter_with_open_order(
            modify_result={"status": "err", "response": "Order was never placed"})
        try:
            from exchange_adapter import AmendRequest, ExchangeRejectedOrderError
            with self.assertRaises(ExchangeRejectedOrderError):
                a.amend_order(AmendRequest(request_id="a1", exchange_order_id="555", new_quantity=Decimal("8")))
        finally:
            store.close(); path.unlink()


if __name__ == "__main__":
    unittest.main()
