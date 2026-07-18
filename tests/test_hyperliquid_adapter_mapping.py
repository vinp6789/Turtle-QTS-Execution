"""Mechanical invariant tests for hyperliquid_adapter.mapping (M1).

Each test class names the catalogue invariant it enforces. Uses real
temp-file EventStore instances (the repository's universal test idiom) --
no mocks of Module 3.
"""

import os
import tempfile
import unittest
from pathlib import Path

from event_store import EventStore, EventType

from exchange_adapter import ExchangeAdapterError

from hyperliquid_adapter.mapping import OrderIdMapping, _idempotency_key, mint_venue_token

ACCOUNT = "0x1111111111111111111111111111111111111111"

# Deliberately hostile id formats: Module 5's contract permits ANY
# non-empty string, and INV-2 forbids format assumptions.
ARBITRARY_IDS = [
    "om:default:1:place",
    "cid-1",
    "注文-1",
    "a" * 200,
    "with:colons:everywhere:1",
    "0xdeadbeef",
    " leading-and-trailing ",
]


def _tmp_store():
    fd, path = tempfile.mkstemp(suffix=".log")
    os.close(fd)
    os.unlink(path)
    return EventStore(path), Path(path)


class Inv2_OpacityGrammarIndependence(unittest.TestCase):
    def test_arbitrary_id_formats_round_trip(self):
        # Any implementation that parses/reconstructs id structure fails
        # this; hashing opaque bytes passes it.
        store, path = _tmp_store()
        try:
            mapping = OrderIdMapping(ACCOUNT, store)
            for cid in ARBITRARY_IDS:
                token = mapping.record(cid)
                self.assertEqual(mapping.resolve(token), cid)
        finally:
            store.close()
            path.unlink()


class Inv5_PersistBeforeTransmit(unittest.TestCase):
    def test_record_without_store_raises(self):
        # Structural guard: a mutation path can never obtain a token
        # without durability.
        mapping = OrderIdMapping(ACCOUNT, None)
        with self.assertRaises(ExchangeAdapterError):
            mapping.record("om:default:1:place")

    def test_mapping_event_is_durable_before_record_returns(self):
        store, path = _tmp_store()
        try:
            mapping = OrderIdMapping(ACCOUNT, store)
            token = mapping.record("om:default:1:place")
            store.close()
            # Reopen the log from disk: the mapping must already be there.
            store2 = EventStore(path)
            try:
                rebuilt = OrderIdMapping(ACCOUNT, store2)
                self.assertEqual(rebuilt.resolve(token), "om:default:1:place")
            finally:
                store2.close()
        finally:
            if path.exists():
                path.unlink()


class Inv6_TokenIdentity(unittest.TestCase):
    def test_minting_is_deterministic(self):
        self.assertEqual(mint_venue_token("om:default:1:place"), mint_venue_token("om:default:1:place"))

    def test_re_record_returns_original_token_single_event(self):
        store, path = _tmp_store()
        try:
            mapping = OrderIdMapping(ACCOUNT, store)
            t1 = mapping.record("om:default:1:place")
            count_after_first = store.event_count
            t2 = mapping.record("om:default:1:place")
            self.assertEqual(t1, t2)
            self.assertEqual(store.event_count, count_after_first)  # deduplicated, no second event
        finally:
            store.close()
            path.unlink()

    def test_restart_re_record_returns_the_durably_stored_token(self):
        # Simulated restart: fresh mapping instance, empty in-memory state,
        # record() again -- must return the ORIGINAL durable token via
        # first-writer-wins, never a divergent fresh one.
        store, path = _tmp_store()
        try:
            t1 = OrderIdMapping(ACCOUNT, store).record("om:default:7:place")
            fresh = OrderIdMapping(ACCOUNT, store)  # replays; but test the record path too
            t2 = fresh.record("om:default:7:place")
            self.assertEqual(t1, t2)
        finally:
            store.close()
            path.unlink()


class Inv7_TokenInjectivity(unittest.TestCase):
    def test_no_collisions_across_generated_id_population(self):
        ids = set(f"om:default:{i}:place" for i in range(5000)) | set(ARBITRARY_IDS)
        tokens = {mint_venue_token(cid) for cid in ids}
        self.assertEqual(len(tokens), len(ids))  # one token per distinct id


class Inv8_TokenVenueFormat(unittest.TestCase):
    def test_token_is_0x_plus_32_lowercase_hex(self):
        for cid in ARBITRARY_IDS:
            token = mint_venue_token(cid)
            self.assertTrue(token.startswith("0x"))
            self.assertEqual(len(token), 34)
            self.assertEqual(token, token.lower())
            int(token, 16)  # parses as hex


class Inv9_KeyNamespaceIsolation(unittest.TestCase):
    def test_key_is_length_prefixed_and_source_tag_first(self):
        key = _idempotency_key(ACCOUNT, "om:default:1:place")
        self.assertTrue(key.startswith("hyperliquid_adapter:"))
        self.assertLessEqual(len(key), 200)  # event_store's MAX_IDEMPOTENCY_KEY_LENGTH

    def test_key_cannot_collide_across_component_boundaries(self):
        # length prefixes make (account="a", cid="b:c") != (account="a:b", cid="c")
        self.assertNotEqual(_idempotency_key("a", "b:c"), _idempotency_key("a:b", "c"))

    def test_dedup_returning_foreign_event_is_detected_not_trusted(self):
        # Occupy the mapping's exact idempotency key with a FOREIGN event
        # first; record() must refuse loudly rather than silently adopt it.
        store, path = _tmp_store()
        try:
            cid = "om:default:1:place"
            store.append(
                EventType.ORDER_SUBMITTED,
                {"source": "order_manager", "om_id": "default", "client_order_id": cid},
                idempotency_key=_idempotency_key(ACCOUNT, cid),
            )
            mapping = OrderIdMapping(ACCOUNT, store)
            with self.assertRaises(ExchangeAdapterError):
                mapping.record(cid)
        finally:
            store.close()
            path.unlink()


class Inv10_SourceTaggingAndSelfReplay(unittest.TestCase):
    def test_rebuilt_map_equals_original(self):
        store, path = _tmp_store()
        try:
            mapping = OrderIdMapping(ACCOUNT, store)
            recorded = {cid: mapping.record(cid) for cid in ARBITRARY_IDS}
            rebuilt = OrderIdMapping(ACCOUNT, store)
            for cid, token in recorded.items():
                self.assertEqual(rebuilt.resolve(token), cid)
                self.assertEqual(rebuilt.known_token(cid), token)
            self.assertEqual(len(rebuilt), len(recorded))
        finally:
            store.close()
            path.unlink()

    def test_other_account_instances_do_not_see_each_others_mappings(self):
        store, path = _tmp_store()
        try:
            a = OrderIdMapping(ACCOUNT, store)
            token = a.record("om:default:1:place")
            other = OrderIdMapping("0x2222222222222222222222222222222222222222", store)
            self.assertIsNone(other.resolve(token))
        finally:
            store.close()
            path.unlink()


class Inv12_PayloadCompliance(unittest.TestCase):
    def test_mapping_payload_passes_event_store_forbidden_name_scan(self):
        # If any payload field name contained a forbidden substring,
        # append() itself would raise MalformedEventError; a clean record()
        # is the mechanical proof.
        store, path = _tmp_store()
        try:
            OrderIdMapping(ACCOUNT, store).record("om:default:1:place")
        finally:
            store.close()
            path.unlink()


class Inv13_ReplaySelfContainment(unittest.TestCase):
    def test_foreign_module_events_do_not_affect_the_map(self):
        store, path = _tmp_store()
        try:
            # Interleave realistic foreign events around a mapping record.
            store.append(
                EventType.ORDER_SUBMITTED,
                {"source": "order_manager", "om_id": "default", "client_order_id": "om:default:1:place"},
                idempotency_key="order_manager:default:om:default:1:place",
            )
            mapping = OrderIdMapping(ACCOUNT, store)
            token = mapping.record("om:default:2:place")
            store.append(
                EventType.POSITION_UPDATED,
                {"source": "portfolio_manager", "pm_id": "default", "action": "reserve"},
                idempotency_key="portfolio_manager:default:reserve:1",
            )
            rebuilt = OrderIdMapping(ACCOUNT, store)
            self.assertEqual(len(rebuilt), 1)
            self.assertEqual(rebuilt.resolve(token), "om:default:2:place")
            # And the map never picked up the OM event's client_order_id.
            self.assertIsNone(rebuilt.known_token("om:default:1:place"))
        finally:
            store.close()
            path.unlink()


# ---------------------------------------------------------------------------
# Robustness tests closing the audit's identified gaps.
# ---------------------------------------------------------------------------


class ConcurrentRecord(unittest.TestCase):
    """record() holds no lock of its own; correctness under concurrency is
    delegated to EventStore.append (atomic, first-writer-wins). Prove it."""

    def test_concurrent_record_same_id_yields_one_event_one_token(self):
        import threading

        store, path = _tmp_store()
        try:
            mapping = OrderIdMapping(ACCOUNT, store)
            cid = "om:default:1:place"
            barrier = threading.Barrier(16)
            results = []

            def worker():
                barrier.wait()  # maximize overlap
                results.append(mapping.record(cid))

            threads = [threading.Thread(target=worker) for _ in range(16)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            self.assertEqual(len(set(results)), 1)             # all returned the same token
            self.assertEqual(results[0], mint_venue_token(cid))
            # Exactly one durable mapping event exists for this id.
            rebuilt = OrderIdMapping(ACCOUNT, store)
            self.assertEqual(len(rebuilt), 1)
            self.assertEqual(rebuilt.resolve(results[0]), cid)
        finally:
            store.close()
            path.unlink()

    def test_concurrent_record_distinct_ids_all_recorded(self):
        import threading

        store, path = _tmp_store()
        try:
            mapping = OrderIdMapping(ACCOUNT, store)
            ids = [f"om:default:{i}:place" for i in range(50)]
            barrier = threading.Barrier(len(ids))

            def worker(cid):
                barrier.wait()
                mapping.record(cid)

            threads = [threading.Thread(target=worker, args=(c,)) for c in ids]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            rebuilt = OrderIdMapping(ACCOUNT, store)
            self.assertEqual(len(rebuilt), len(ids))
            for cid in ids:
                self.assertEqual(rebuilt.resolve(mint_venue_token(cid)), cid)
        finally:
            store.close()
            path.unlink()


class OrphanMapping(unittest.TestCase):
    """A mapping durably recorded but never transmitted (crash between
    append and transmit, or a fail-closed mutation) is harmless: it
    resolves to its cid but the venue never carries that token, so no read
    path can surface or mis-attribute it."""

    def test_orphan_resolves_but_is_never_surfaced_by_reads(self):
        store, path = _tmp_store()
        try:
            mapping = OrderIdMapping(ACCOUNT, store)
            token = mapping.record("om:default:1:place")  # recorded, "never transmitted"
            # The mapping resolves it...
            self.assertEqual(mapping.resolve(token), "om:default:1:place")
            # ...but the codec, given a venue snapshot that does NOT contain
            # this token (the venue has no such order), returns nothing to
            # attribute -- the orphan cannot be surfaced or mislabeled.
            from hyperliquid_adapter import codec

            self.assertEqual(codec.parse_open_orders([], mapping.resolve), ())
            other_venue_order = [{
                "coin": "BTC", "cloid": "0x" + "e" * 32, "limitPx": "1", "oid": 5,
                "origSz": "1", "reduceOnly": False, "side": "A", "sz": "1", "timestamp": 1,
            }]
            # That foreign order does not resolve; the orphan token is not in it either.
            self.assertEqual(codec.parse_open_orders(other_venue_order, mapping.resolve), ())
        finally:
            store.close()
            path.unlink()


class ColdRestartDedup(unittest.TestCase):
    """After a genuine cold restart (fresh process, empty in-memory map),
    re-recording must return the ORIGINAL durable token. This isolates the
    append-dedup path: the second OrderIdMapping is built WITHOUT replaying
    the mapping (from_event_id past it), so its fast-path cache is empty and
    record() must rely on EventStore first-writer-wins, not preloaded memory."""

    def test_record_after_empty_memory_dedups_via_append(self):
        store, path = _tmp_store()
        try:
            cid = "om:default:7:place"
            first = OrderIdMapping(ACCOUNT, store)
            original_token = first.record(cid)

            # Build a second instance whose in-memory map is guaranteed empty
            # by monkeypatching replay to yield nothing -- simulating a cold
            # process that has not yet (or cannot) replay this event, forcing
            # the append-dedup path rather than the known-token fast path.
            cold = OrderIdMapping.__new__(OrderIdMapping)
            cold._account = ACCOUNT
            cold._store = store
            cold._token_to_cid = {}
            cold._cid_to_token = {}
            self.assertEqual(len(cold), 0)  # provably empty memory

            returned = cold.record(cid)  # must hit append -> first-writer-wins
            self.assertEqual(returned, original_token)
            # And still exactly one durable event (no duplicate written).
            self.assertEqual(len(OrderIdMapping(ACCOUNT, store)), 1)
        finally:
            store.close()
            path.unlink()


class ReplayIsolationAcrossModules(unittest.TestCase):
    """A mapping event uses EventType.ORDER_SUBMITTED but source-tag
    'hyperliquid_adapter'; a real frozen OrderManager replaying the SAME
    store must not ingest it (it filters on payload['source'] first)."""

    def test_order_manager_ignores_mapping_events_on_replay(self):
        from secrets_boundary import EnvironmentHmacBackend, SigningBoundary

        from event_store import EventStore
        from exchange_adapter import MockExchangeAdapter
        from execution_state_machine import ExecutionStateMachine
        from order_manager import OrderManager, OrderNotFoundError

        signing_ref = "hyperliquid_signing_key_v1"

        def _boundary():
            env = {"TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1": "test-material"}
            return SigningBoundary([signing_ref], "1.0.0", "mock", backend=EnvironmentHmacBackend(env=env))

        store, path = _tmp_store()
        try:
            # Write a mapping event into the shared log, then close.
            OrderIdMapping(ACCOUNT, store).record("om:default:1:place")
            store.close()

            # A fresh OrderManager replays the SAME on-disk log.
            store2 = EventStore(path)
            adapter = MockExchangeAdapter(_boundary(), signing_ref)
            try:
                sm = ExecutionStateMachine(store2, machine_id="default")
                om = OrderManager(adapter, store2, sm, om_id="default")
                # The mapping event (source='hyperliquid_adapter') must be
                # invisible: OM tracks zero orders and has no in-doubt set.
                with self.assertRaises(OrderNotFoundError):
                    om.get_order_status("om:default:1:place")
                self.assertEqual(om.in_doubt_client_order_ids, ())
            finally:
                store2.close()
        finally:
            if path.exists():
                path.unlink()


if __name__ == "__main__":
    unittest.main()
