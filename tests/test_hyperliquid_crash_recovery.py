"""Deterministic crash-recovery validation harness (Phase 1).

Drives a REAL OrderManager + HyperliquidAdapter + EventStore against a
stateful fake venue, injecting a simulated process crash at each of the six
critical points of a place_order, then reconstructs everything from the same
on-disk EventStore (simulating restart) and verifies recovery. No live venue.

Crash points:
  before_record   -- SUBMIT persisted; mapping.record() not yet run
  after_record    -- mapping durable; POST not yet made
  before_post     -- signed; venue never receives the order
  after_post      -- venue receives; we crash before reading the response
  before_ack      -- venue has order; OM crashes before persisting ACK
  none (after_ack)-- full success

For each: EventStore reopens clean (no corruption), OM state / in_doubt,
mapping reconstruction, resync behavior, duplicate-order prevention, and
engine_id attribution are checked.
"""

import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from event_store import EventStore
from secrets_boundary import EnvironmentHmacBackend, SigningBoundary

from exchange_adapter import OrderSide, OrderStatus, OrderType, Symbol, TimeInForce
from execution_state_machine import ExecutionStateMachine
from execution_state_machine import Trigger as ETrigger
from order_manager import OrderManager, OrderLifecycleState

try:
    from hyperliquid_adapter.signing import HyperliquidWalletSigner
    import eth_account  # noqa: F401
    import msgpack  # noqa: F401
    _HAVE = True
except ImportError:
    _HAVE = False

from hyperliquid_adapter import HttpResponse, HyperliquidAdapter
from hyperliquid_adapter.transport import TESTNET_BASE_URL

SIGNING_REF = "hyperliquid_signing_key_v1"
WALLET_REF = "hyperliquid_wallet_key_v1"
ACCOUNT = "0x1111111111111111111111111111111111111111"
WALLET_ENV = {"TURTLE_SECRET_HYPERLIQUID_WALLET_KEY_V1": "0x" + "44" * 32}
CID = "om:om:1:place"  # deterministic first-order id for om_id="om"


class CrashSignal(BaseException):
    """Simulated process death -- not an ExchangeAdapterError, so neither the
    base adapter nor OrderManager catches it; it unwinds to the harness."""


def _boundary():
    return SigningBoundary([SIGNING_REF], "1.0.0", "hyperliquid",
                           backend=EnvironmentHmacBackend(env={"TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1": "m"}))


class FakeVenue:
    """Stateful in-memory Hyperliquid model: keeps placed orders keyed by
    cloid, rejects duplicate cloids (as the real venue does), and answers
    /info queries. place_count lets tests assert no duplicate placement."""

    def __init__(self):
        self.orders = {}   # cloid -> {oid, coin, side, px, sz, status}
        self._next_oid = 5000
        self.place_count = 0

    def apply_exchange(self, payload):
        action = payload["action"]
        if action["type"] == "order":
            self.place_count += 1
            statuses = []
            for w in action["orders"]:
                cloid = w.get("c")
                if cloid in self.orders:
                    statuses.append({"error": "Order has duplicate cloid"})
                    continue
                oid = self._next_oid
                self._next_oid += 1
                self.orders[cloid] = {
                    "oid": oid, "cloid": cloid, "coin": "BTC",
                    "side": "B" if w["b"] else "A", "px": w["p"], "sz": w["s"], "status": "open",
                }
                statuses.append({"resting": {"oid": oid}})
            return {"status": "ok", "response": {"type": "order", "data": {"statuses": statuses}}}
        raise AssertionError(f"unexpected action type {action['type']}")

    def _find(self, key):
        if isinstance(key, str) and key.startswith("0x"):
            return self.orders.get(key)
        for o in self.orders.values():
            if str(o["oid"]) == str(key):
                return o
        return None

    def _order_obj(self, o):
        return {"coin": o["coin"], "cloid": o["cloid"], "limitPx": o["px"], "oid": o["oid"],
                "origSz": o["sz"], "reduceOnly": False, "side": o["side"], "sz": o["sz"], "timestamp": 1}

    def info(self, payload):
        t = payload["type"]
        if t == "meta":
            return {"universe": [{"name": "BTC", "szDecimals": 5}]}
        if t == "allMids":
            return {"BTC": "50000"}
        if t == "clearinghouseState":
            return {"assetPositions": [], "marginSummary": {"accountValue": "1000"}, "withdrawable": "1000"}
        if t == "frontendOpenOrders":
            return [self._order_obj(o) for o in self.orders.values() if o["status"] == "open"]
        if t == "userFills":
            return []
        if t == "orderStatus":
            o = self._find(payload["oid"])
            if o is None:
                return {"status": "unknownOid"}
            return {"status": "order", "order": {"order": self._order_obj(o), "status": o["status"], "statusTimestamp": 1}}
        raise AssertionError(f"unexpected info type {t}")


class HarnessTransport:
    def __init__(self, venue, crash_point=None):
        self.venue = venue
        self.crash_point = crash_point

    def __call__(self, url, payload, timeout):
        if url.endswith("/exchange"):
            if self.crash_point == "before_post":
                raise CrashSignal()          # venue never receives
            result = self.venue.apply_exchange(payload)
            if self.crash_point == "after_post":
                raise CrashSignal()          # venue received; crash before response
            return HttpResponse(200, result)
        return HttpResponse(200, self.venue.info(payload))


def _new_path():
    fd, p = tempfile.mkstemp(suffix=".log")
    os.close(fd)
    os.unlink(p)
    return Path(p)


def _build(path, venue, crash_point=None, fresh=False):
    store = EventStore(str(path))
    sm = ExecutionStateMachine(store, machine_id="m")
    if fresh:
        sm.transition(ETrigger.STARTED, "s")
        sm.transition(ETrigger.RECONCILED, "r")
        sm.transition(ETrigger.SIGNAL_RECEIVED, "sig")
    signer = HyperliquidWalletSigner(WALLET_REF, is_mainnet=False, env=WALLET_ENV)
    transport = HarnessTransport(venue, crash_point)
    adapter = HyperliquidAdapter(_boundary(), SIGNING_REF, ACCOUNT, transport=transport,
                                 event_store=store, wallet_signer=signer, base_url=TESTNET_BASE_URL)
    adapter.connect()
    om = OrderManager(adapter, store, sm, om_id="om")
    return store, adapter, om


def _crash(*a, **k):
    raise CrashSignal()


@unittest.skipUnless(_HAVE, "eth-account/msgpack not installed")
class CrashRecovery(unittest.TestCase):
    def _run_place_until_crash(self, path, venue, crash_point):
        store, adapter, om = _build(path, venue, crash_point=crash_point if crash_point in ("before_post", "after_post") else None, fresh=True)
        if crash_point == "before_record":
            adapter._mapping.record = _crash
        elif crash_point == "after_record":
            real = adapter._mapping.record
            def after(cid):
                real(cid)
                raise CrashSignal()
            adapter._mapping.record = after
        elif crash_point == "before_ack":
            om._ingest_status = _crash
        crashed = False
        try:
            om.place_order(Symbol("BTC"), OrderSide.BUY, OrderType.LIMIT, Decimal("1"), limit_price=Decimal("50000"))
        except CrashSignal:
            crashed = True
        store.close()  # simulate process death releasing the single-writer lock
        return crashed

    def _restart(self, path, venue):
        # Reopen the SAME log (would raise CorruptEventStoreError if corrupt).
        return _build(path, venue, fresh=False)

    # ---- points where the venue never received the order ----

    def _assert_unresolved(self, crash_point, expect_events_have_mapping):
        path = _new_path()
        venue = FakeVenue()
        try:
            self.assertTrue(self._run_place_until_crash(path, venue, crash_point))
            self.assertEqual(venue.place_count, 0)  # order never reached the venue
            store, adapter, om = self._restart(path, venue)
            try:
                self.assertEqual(om.in_doubt_client_order_ids, (CID,))  # SUBMITTED, in-doubt
                self.assertEqual(adapter._mapping.known_token(CID) is not None, expect_events_have_mapping)
                snap = om.resync_order(CID)
                self.assertEqual(snap.lifecycle_state, OrderLifecycleState.SUBMITTED)  # still unresolved
                self.assertIsNone(snap.exchange_order_id)
                self.assertEqual(venue.place_count, 0)  # resync never re-places
            finally:
                store.close()
        finally:
            path.unlink()

    def test_crash_before_record(self):
        self._assert_unresolved("before_record", expect_events_have_mapping=False)

    def test_crash_after_record(self):
        self._assert_unresolved("after_record", expect_events_have_mapping=True)

    def test_crash_before_post(self):
        self._assert_unresolved("before_post", expect_events_have_mapping=True)

    # ---- points where the venue DID receive the order ----

    def _assert_resolves_to_acknowledged(self, crash_point):
        path = _new_path()
        venue = FakeVenue()
        try:
            self.assertTrue(self._run_place_until_crash(path, venue, crash_point))
            self.assertEqual(venue.place_count, 1)  # venue received exactly one order
            store, adapter, om = self._restart(path, venue)
            try:
                self.assertEqual(om.in_doubt_client_order_ids, (CID,))
                self.assertIsNotNone(adapter._mapping.known_token(CID))  # mapping durable
                snap = om.resync_order(CID)  # find_order queries venue by token
                self.assertEqual(snap.lifecycle_state, OrderLifecycleState.ACKNOWLEDGED)
                self.assertIsNotNone(snap.exchange_order_id)
                self.assertEqual(snap.client_order_id, CID)         # engine_id attribution
                self.assertEqual(venue.place_count, 1)               # NO duplicate order placed
            finally:
                store.close()
        finally:
            path.unlink()

    def test_crash_after_post(self):
        self._assert_resolves_to_acknowledged("after_post")

    def test_crash_before_ack(self):
        self._assert_resolves_to_acknowledged("before_ack")

    # ---- full success (after ACK) ----

    def test_no_crash_after_ack(self):
        path = _new_path()
        venue = FakeVenue()
        try:
            self.assertFalse(self._run_place_until_crash(path, venue, None))
            self.assertEqual(venue.place_count, 1)
            store, adapter, om = self._restart(path, venue)
            try:
                self.assertEqual(om.in_doubt_client_order_ids, ())    # ACKNOWLEDGED, not in-doubt
                snap = om.get_order_status(CID)
                self.assertEqual(snap.lifecycle_state, OrderLifecycleState.ACKNOWLEDGED)
                self.assertIsNotNone(snap.exchange_order_id)
                self.assertEqual(venue.place_count, 1)
            finally:
                store.close()
        finally:
            path.unlink()

    # ---- venue-level duplicate-cloid rejection (the same order re-sent) ----

    def test_duplicate_cloid_rejected_by_venue(self):
        venue = FakeVenue()
        t = HarnessTransport(venue)
        # First place succeeds; a second /exchange with the SAME cloid is rejected.
        from hyperliquid_adapter import action_codec
        from hyperliquid_adapter.mapping import mint_venue_token
        cloid = mint_venue_token(CID)
        wire = action_codec.build_order_wire(0, True, Decimal("50000"), Decimal("1"), False, "Gtc", cloid)
        action = action_codec.build_order_action([wire])
        r1 = venue.apply_exchange({"action": action, "nonce": 1, "signature": {}})
        r2 = venue.apply_exchange({"action": action, "nonce": 2, "signature": {}})
        self.assertIn("resting", r1["response"]["data"]["statuses"][0])
        self.assertIn("error", r2["response"]["data"]["statuses"][0])  # duplicate cloid rejected
        self.assertEqual(len(venue.orders), 1)  # only one order exists


if __name__ == "__main__":
    unittest.main()
