import dataclasses
import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from exchange_adapter import (
    AmendRequest,
    CancelAllRequest,
    CancelRequest,
    ExchangeAdapter,
    ExchangeCapabilities,
    ExchangeConnectionError,
    ExchangeRejectedOrderError,
    MockExchangeAdapter,
    Operation,
    OperationSafety,
    OrderRequest,
    OrderSide,
    OrderType,
    OrderUnknownError,
    RateLimitExceededError,
    RetryPolicy,
    SequenceGapError,
    StaleSnapshotError,
    Symbol,
    TimeInForce,
    execute_with_retry,
)
from exchange_adapter.audit import compute_audit_record, order_request_audit_payload
from secrets_boundary import SigningBoundary

SIGNING_REF = "mock_exchange_signing_key_v1"


def _tmp_secret_env(value: str = "test-material") -> dict:
    from secrets_boundary.backend import _env_var_name

    return {_env_var_name(SIGNING_REF): value}


def _boundary() -> SigningBoundary:
    return SigningBoundary([SIGNING_REF], engine_version="1.0.0", exchange_name="mock", env=_tmp_secret_env())


def _adapter() -> MockExchangeAdapter:
    a = MockExchangeAdapter(_boundary(), SIGNING_REF)
    a.connect()
    return a


def _order_request(cid: str = "cid-1", qty: str = "1.5") -> OrderRequest:
    return OrderRequest(
        client_order_id=cid,
        symbol=Symbol("BTC"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal(qty),
        limit_price=Decimal("50000"),
        time_in_force=TimeInForce.GTC,
    )


class InterfaceCompliance(unittest.TestCase):
    def test_cannot_instantiate_abstract_adapter_directly(self):
        with self.assertRaises(TypeError):
            ExchangeAdapter(_boundary(), "x", "1.0", MockExchangeAdapter.__dict__)  # any args, must fail before that

    def test_incomplete_subclass_cannot_be_instantiated(self):
        class Incomplete(ExchangeAdapter):
            def connect(self): pass
            # every other abstract method deliberately omitted

        with self.assertRaises(TypeError):
            Incomplete(_boundary(), "x", "1.0", MockExchangeAdapter.__dict__)

    def test_mock_adapter_implements_full_interface(self):
        a = _adapter()
        self.assertIsInstance(a, ExchangeAdapter)

    def test_constructor_requires_signing_boundary_type(self):
        with self.assertRaises(TypeError):
            MockExchangeAdapter("not-a-signing-boundary", SIGNING_REF)

    def test_second_concrete_adapter_needs_no_interface_change(self):
        # Proves the interface supports another exchange (e.g. a future
        # Lighter/Variational adapter) with zero modification to this
        # module -- just a new subclass of the same ABC.
        class SecondExchangeAdapter(MockExchangeAdapter):
            pass

        a = SecondExchangeAdapter(_boundary(), SIGNING_REF, exchange_name="second-exchange")
        a.connect()
        self.assertEqual(a.exchange_name, "second-exchange")
        order = a.place_order(_order_request())
        self.assertEqual(order.status.value, "ACKNOWLEDGED")


class CapabilitiesAndImmutability(unittest.TestCase):
    def test_capabilities_exposed_and_frozen(self):
        a = _adapter()
        caps = a.capabilities
        self.assertIsInstance(caps, ExchangeCapabilities)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            caps.supports_market_orders = False

    def test_capabilities_immutable_after_construction_no_setter(self):
        a = _adapter()
        with self.assertRaises(AttributeError):
            a.capabilities = ExchangeCapabilities(
                supports_reduce_only=False, supports_post_only=False, supports_ioc=False,
                supports_fok=False, supports_market_orders=False, supports_limit_orders=False,
                supports_trigger_orders=False, supports_partial_fill_notifications=False,
                supports_funding_rate=False, supports_cross_margin=False, supports_isolated_margin=False,
            )

    def test_capabilities_extra_field_is_deep_frozen(self):
        caps = ExchangeCapabilities(
            supports_reduce_only=True, supports_post_only=True, supports_ioc=True, supports_fok=True,
            supports_market_orders=True, supports_limit_orders=True, supports_trigger_orders=True,
            supports_partial_fill_notifications=True, supports_funding_rate=True,
            supports_cross_margin=True, supports_isolated_margin=True,
            extra={"supports_twap": True},
        )
        with self.assertRaises(TypeError):
            caps.extra["supports_twap"] = False

    def test_order_and_position_models_are_frozen(self):
        a = _adapter()
        order = a.place_order(_order_request())
        with self.assertRaises(dataclasses.FrozenInstanceError):
            order.status = None


class TypedModelValidation(unittest.TestCase):
    def test_order_request_rejects_empty_client_order_id(self):
        with self.assertRaises(ValueError):
            OrderRequest("", Symbol("BTC"), OrderSide.BUY, OrderType.MARKET, Decimal("1"))

    def test_order_request_rejects_nonpositive_quantity(self):
        with self.assertRaises(ValueError):
            OrderRequest("cid", Symbol("BTC"), OrderSide.BUY, OrderType.MARKET, Decimal("0"))

    def test_amend_request_requires_at_least_one_change(self):
        with self.assertRaises(ValueError):
            AmendRequest("rid", "eoid")

    def test_symbol_rejects_empty_value(self):
        with self.assertRaises(ValueError):
            Symbol("")


class IdempotencyAndAudit(unittest.TestCase):
    def test_place_order_idempotent_on_duplicate_client_order_id(self):
        a = _adapter()
        r1 = a.place_order(_order_request("dup-1"))
        r2 = a.place_order(_order_request("dup-1", qty="99"))  # different qty, same id
        self.assertEqual(r1.exchange_order_id, r2.exchange_order_id)
        self.assertEqual(r2.quantity, Decimal("1.5"))  # original, not the retry's
        self.assertEqual(len(a.get_orders()), 1)

    def test_cancel_order_idempotent(self):
        a = _adapter()
        order = a.place_order(_order_request("cid-2"))
        req = CancelRequest("cancel-1", order.exchange_order_id)
        c1 = a.cancel_order(req)
        c2 = a.cancel_order(req)
        self.assertEqual(c1.updated_at_utc, c2.updated_at_utc)

    def test_every_mutation_creates_exactly_one_audit_record(self):
        a = _adapter()
        order = a.place_order(_order_request("cid-3"))
        a.amend_order(AmendRequest("amend-1", order.exchange_order_id, new_quantity=Decimal("2")))
        a.cancel_order(CancelRequest("cancel-1", order.exchange_order_id))
        actions = [r.logical_action for r in a.audit_records]
        self.assertEqual(actions, ["PLACE_ORDER", "AMEND_ORDER", "CANCEL_ORDER"])

    def test_duplicate_request_does_not_create_a_second_audit_record(self):
        a = _adapter()
        a.place_order(_order_request("cid-4"))
        a.place_order(_order_request("cid-4"))  # duplicate
        self.assertEqual(len(a.audit_records), 1)

    def test_audit_record_contains_only_permitted_fields(self):
        a = _adapter()
        a.place_order(_order_request("cid-5"))
        record = a.audit_records[0]
        fields = {f.name for f in dataclasses.fields(record)}
        self.assertEqual(
            fields,
            {"request_id", "logical_action", "exchange_name", "adapter_version",
             "timestamp_utc", "payload_hash", "idempotency_key"},
        )

    def test_audit_record_never_contains_signature_or_secret_material(self):
        canary = "CANARY-SECRET-9f8e"
        env = _tmp_secret_env(value=canary)
        boundary = SigningBoundary([SIGNING_REF], engine_version="1.0.0", exchange_name="mock", env=env)
        a = MockExchangeAdapter(boundary, SIGNING_REF)
        a.connect()
        a.place_order(_order_request("cid-6"))
        record = a.audit_records[-1]
        blob = repr(record)
        self.assertNotIn(canary, blob)
        self.assertNotIn("signature", blob.lower())

    def test_audit_record_hash_deterministic_and_reproducible(self):
        request = _order_request("cid-7")
        payload = order_request_audit_payload(request)
        r1 = compute_audit_record("cid-7", "PLACE_ORDER", "mock", "1.0.0-mock", "cid-7", payload)
        r2 = compute_audit_record("cid-7", "PLACE_ORDER", "mock", "1.0.0-mock", "cid-7", payload)
        self.assertEqual(r1.payload_hash, r2.payload_hash)  # same payload -> same hash, regardless of timestamp

    def test_audit_record_hash_changes_with_payload(self):
        p1 = order_request_audit_payload(_order_request("cid-8", qty="1"))
        p2 = order_request_audit_payload(_order_request("cid-8", qty="2"))
        r1 = compute_audit_record("cid-8", "PLACE_ORDER", "mock", "1.0.0-mock", "cid-8", p1)
        r2 = compute_audit_record("cid-8", "PLACE_ORDER", "mock", "1.0.0-mock", "cid-8", p2)
        self.assertNotEqual(r1.payload_hash, r2.payload_hash)

    def test_audit_record_created_before_transmission_even_on_failure(self):
        a = _adapter()
        a.fail_next("place_order", ExchangeRejectedOrderError("simulated rejection"))
        with self.assertRaises(ExchangeRejectedOrderError):
            a.place_order(_order_request("cid-9"))
        # the record for the attempt still exists even though transmission failed
        self.assertEqual(len(a.audit_records), 1)
        self.assertEqual(a.audit_records[0].logical_action, "PLACE_ORDER")


class CapabilityGating(unittest.TestCase):
    def test_market_order_rejected_when_unsupported(self):
        caps = ExchangeCapabilities(
            supports_reduce_only=True, supports_post_only=True, supports_ioc=True, supports_fok=True,
            supports_market_orders=False, supports_limit_orders=True, supports_trigger_orders=False,
            supports_partial_fill_notifications=True, supports_funding_rate=True,
            supports_cross_margin=True, supports_isolated_margin=True,
        )
        a = MockExchangeAdapter(_boundary(), SIGNING_REF, capabilities=caps)
        a.connect()
        req = OrderRequest("cid", Symbol("BTC"), OrderSide.BUY, OrderType.MARKET, Decimal("1"))
        with self.assertRaises(ExchangeRejectedOrderError):
            a.place_order(req)


class FailurePaths(unittest.TestCase):
    def test_websocket_disconnect(self):
        a = _adapter()
        a.simulate_disconnect()
        with self.assertRaises(ExchangeConnectionError):
            a.get_positions()

    def test_rest_timeout(self):
        from exchange_adapter import ExchangeTimeoutError
        a = _adapter()
        a.fail_next("get_balances", ExchangeTimeoutError("simulated timeout"))
        with self.assertRaises(ExchangeTimeoutError):
            a.get_balances()

    def test_duplicate_acknowledgement_handled_idempotently(self):
        a = _adapter()
        order = a.place_order(_order_request("dup-ack"))
        order_again = a.place_order(_order_request("dup-ack"))
        self.assertEqual(order.exchange_order_id, order_again.exchange_order_id)

    def test_partial_fill_normalized_not_an_error(self):
        a = _adapter()
        order = a.place_order(_order_request("cid-pf", qty="10"))
        updated = a.simulate_fill(order.exchange_order_id, Decimal("4"), Decimal("50000"))
        self.assertEqual(updated.status.value, "PARTIALLY_FILLED")
        self.assertEqual(updated.filled_quantity, Decimal("4"))

    def test_order_unknown(self):
        a = _adapter()
        with self.assertRaises(OrderUnknownError):
            a.get_order_status("does-not-exist")

    def test_stale_snapshot(self):
        a = _adapter()
        a.simulate_stale_snapshot(True)
        with self.assertRaises(StaleSnapshotError):
            a.get_positions()

    def test_sequence_gap(self):
        a = _adapter()
        a.simulate_sequence_gap(True)
        with self.assertRaises(SequenceGapError):
            a.get_positions()
        health = a.health()
        self.assertTrue(health.sequence_gap_detected)

    def test_reconciliation_mismatch(self):
        from exchange_adapter import Position
        a = _adapter()
        a.set_position(Position(Symbol("BTC"), Decimal("2"), Decimal("50000"), Decimal("51000"), Decimal("2000"), None))
        local = (Position(Symbol("BTC"), Decimal("1"), Decimal("50000"), Decimal("51000"), Decimal("1000"), None),)
        report = a.reconcile(local)
        self.assertFalse(report.matches)
        self.assertEqual(len(report.discrepancies), 1)

    def test_reconciliation_match(self):
        from exchange_adapter import Position
        a = _adapter()
        pos = Position(Symbol("ETH"), Decimal("3"), Decimal("2000"), Decimal("2050"), Decimal("150"), None)
        a.set_position(pos)
        report = a.reconcile((pos,))
        self.assertTrue(report.matches)
        self.assertEqual(report.discrepancies, ())


class RetryPolicyBehavior(unittest.TestCase):
    def test_mutations_never_retried_by_default(self):
        policy = RetryPolicy()
        for op in (Operation.PLACE_ORDER, Operation.AMEND_ORDER, Operation.CANCEL_ORDER, Operation.CANCEL_ALL):
            self.assertFalse(policy.should_retry(op, 1, ExchangeConnectionError("x")))

    def test_reads_retried_on_connection_error(self):
        policy = RetryPolicy(max_attempts=3)
        self.assertTrue(policy.should_retry(Operation.GET_POSITIONS, 1, ExchangeConnectionError("x")))
        self.assertFalse(policy.should_retry(Operation.GET_POSITIONS, 3, ExchangeConnectionError("x")))

    def test_auth_errors_never_retried_even_for_reads(self):
        from exchange_adapter import ExchangeAuthenticationError
        policy = RetryPolicy()
        self.assertFalse(policy.should_retry(Operation.GET_POSITIONS, 1, ExchangeAuthenticationError("x")))

    def test_rate_limit_backoff_uses_retry_after(self):
        policy = RetryPolicy()
        err = RateLimitExceededError("slow down", retry_after_seconds=7.5)
        self.assertEqual(policy.backoff_seconds(1, err), 7.5)

    def test_execute_with_retry_never_retries_unsafe_operation(self):
        policy = RetryPolicy(max_attempts=5)
        calls = []

        def flaky():
            calls.append(1)
            raise ExchangeConnectionError("down")

        with self.assertRaises(ExchangeConnectionError):
            execute_with_retry(flaky, Operation.PLACE_ORDER, policy, sleep_fn=lambda s: None)
        self.assertEqual(len(calls), 1)  # exactly one attempt, no retry

    def test_execute_with_retry_retries_safe_operation_until_success(self):
        policy = RetryPolicy(max_attempts=5)
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise ExchangeConnectionError("down")
            return "ok"

        result = execute_with_retry(flaky, Operation.GET_POSITIONS, policy, sleep_fn=lambda s: None)
        self.assertEqual(result, "ok")
        self.assertEqual(len(calls), 3)

    def test_custom_operation_safety_override(self):
        policy = RetryPolicy(operation_safety={Operation.PLACE_ORDER: OperationSafety.SAFE_TO_RETRY})
        self.assertTrue(policy.should_retry(Operation.PLACE_ORDER, 1, ExchangeConnectionError("x")))


class SigningIntegration(unittest.TestCase):
    def test_adapter_never_stores_raw_key_material(self):
        a = _adapter()
        self.assertFalse(hasattr(a, "_private_key"))
        self.assertFalse(hasattr(a, "_secret"))
        blob = repr(vars(a))
        self.assertNotIn("test-material", blob)  # the raw secret value used in the fixture

    def test_place_order_requires_connection_before_signing(self):
        a = MockExchangeAdapter(_boundary(), SIGNING_REF)  # not connected
        with self.assertRaises(ExchangeConnectionError):
            a.place_order(_order_request("cid-x"))


if __name__ == "__main__":
    unittest.main()
