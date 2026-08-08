"""TRADE_ATTRIBUTION: why a cycle decided what it decided.

The most important test here is TestIntentIdentitySurvivesPooling. The
whole design rests on TradeIntent objects being passed by reference from
generate_intents() all the way into CycleResult. If that ever stops being
true, attribution silently degrades -- so it is asserted end-to-end
against a real paper engine, not assumed.
"""

import json
import unittest
from decimal import Decimal

from event_store import MAX_PAYLOAD_BYTES, EventType, read_events
from exchange_adapter import OrderSide, Symbol

from alpha_engine.platform import PluginKind, get_plugin
from alpha_engine.platform.attributed_strategy import (
    AttributedStrategy, StrategyIdentity, forget_all, resolve)
from measurement import attribution
from measurement.attribution import MAX_FEATURES_PER_INTENT

from tests.test_trading_system_scheduling import (
    _FixedIntentStrategy, _RealPaperEngineCase, _intent)

ALPHA_ID = StrategyIdentity("alpha_a", "1.2", "alpha")
PROBE_ID = StrategyIdentity("lifecycle_probe", "1.0", "engine_test")


class _Multi(_FixedIntentStrategy):
    def __init__(self, intents, label):
        super().__init__(intents[0], label)
        self._intents = tuple(intents)

    def generate_intents(self, context):
        return self._intents


# --------------------------------------------------- THE CRITICAL GATE
class TestIntentIdentitySurvivesPooling(_RealPaperEngineCase):
    """If this fails, STOP. Do not patch around it -- request a
    strategy_id field on TradeIntent under Constitution §9."""

    def test_same_objects_reach_cycle_result(self):
        i1 = _intent(symbol=Symbol("BTC"))
        i2 = _intent(symbol=Symbol("BTC"), reduce_only=True)
        i3 = _intent(symbol=Symbol("ETH"))
        a = _FixedIntentStrategy(i1, label="alpha_a")
        b = _Multi((i2, i3), label="probe_b")

        result = self._run((a, b))
        originals = {id(i1), id(i2), id(i3)}

        seen = [id(x) for x in result.intents]
        seen += [id(r.intent) for r in result.construction.rejected]
        seen += [id(s.intent) for s in result.construction.skipped]
        seen += [id(x) for x in result.suppressed_by_open_orders]

        copies = [s for s in seen if s not in originals]
        self.assertFalse(
            copies,
            "a TradeIntent was reconstructed somewhere in the pipeline; "
            "id()-based attribution is INVALID and must not be patched around")

    def test_wrapper_passes_the_same_objects_through_a_real_cycle(self):
        """The wrapper must not copy, and the object it recorded must be
        the object that arrives in CycleResult."""
        i1 = _intent(symbol=Symbol("BTC"))
        w = AttributedStrategy(_FixedIntentStrategy(i1, "alpha_a"), ALPHA_ID)
        result = self._run((w,))
        self.assertIn(id(i1), [id(x) for x in result.intents],
                      "the wrapper's intent did not reach CycleResult by identity")
        self.assertEqual(resolve((w,), i1), ALPHA_ID,
                         "the wrapper failed to attribute its own intent")

    def test_wrapper_changes_no_behaviour(self):
        """Wrapped and unwrapped must produce identical cycle outcomes."""
        i_plain = _intent(symbol=Symbol("BTC"))
        plain = self._run((_FixedIntentStrategy(i_plain, "alpha_a"),))
        i_wrapped = _intent(symbol=Symbol("BTC"))
        wrapped = self._run((AttributedStrategy(
            _FixedIntentStrategy(i_wrapped, "alpha_a"), ALPHA_ID),))
        self.assertEqual(len(plain.intents), len(wrapped.intents))
        self.assertEqual(len(plain.construction.approved), len(wrapped.construction.approved))
        self.assertEqual(len(plain.construction.skipped), len(wrapped.construction.skipped))
        self.assertEqual(len(plain.construction.rejected), len(wrapped.construction.rejected))


# ------------------------------------------------------ MULTI-STRATEGY
class TestMultiStrategyAttribution(_RealPaperEngineCase):
    """2 strategies, 3 intents, mixed dispositions, mixed kinds."""

    def _cycle(self):
        self.i1 = _intent(symbol=Symbol("BTC"))
        self.i2 = _intent(symbol=Symbol("BTC"), reduce_only=True)
        self.i3 = _intent(symbol=Symbol("ETH"))          # outside universe -> SKIPPED
        self.a = AttributedStrategy(_FixedIntentStrategy(self.i1, "alpha_a"), ALPHA_ID)
        self.b = AttributedStrategy(_Multi((self.i2, self.i3), "probe_b"), PROBE_ID)
        self.strategies = (self.a, self.b)
        return self._run(self.strategies)

    def test_every_intent_is_attributed_to_its_own_strategy(self):
        result = self._cycle()
        payload = attribution.build(result, self.strategies)
        by_symbol_side = {(r["symbol"], r["reduce_only"]): r for r in payload["intents"]}
        self.assertEqual(by_symbol_side[("BTC", False)]["strategy_id"], "alpha_a")
        self.assertEqual(by_symbol_side[("BTC", True)]["strategy_id"], "lifecycle_probe")
        self.assertEqual(by_symbol_side[("ETH", False)]["strategy_id"], "lifecycle_probe")

    def test_strategy_kinds_are_distinct_and_registry_sourced(self):
        result = self._cycle()
        payload = attribution.build(result, self.strategies)
        kinds = {r["strategy_id"]: r["strategy_kind"] for r in payload["intents"]}
        self.assertEqual(kinds["alpha_a"], "alpha")
        self.assertEqual(kinds["lifecycle_probe"], "engine_test")

    def test_all_three_intents_appear_exactly_once(self):
        result = self._cycle()
        payload = attribution.build(result, self.strategies)
        self.assertEqual(len(payload["intents"]), 3)

    def test_every_intent_has_a_disposition(self):
        result = self._cycle()
        payload = attribution.build(result, self.strategies)
        for r in payload["intents"]:
            self.assertIn(r["disposition"],
                          {"APPROVED", "REJECTED", "SKIPPED", "SUPPRESSED"})

    def test_skipped_intents_carry_a_reason(self):
        result = self._cycle()
        payload = attribution.build(result, self.strategies)
        skipped = [r for r in payload["intents"] if r["disposition"] == "SKIPPED"]
        self.assertTrue(skipped)
        for r in skipped:
            self.assertTrue(r.get("reason"), "a SKIPPED intent must say why")

    def test_orders_carry_client_order_id_and_rejected_intents_do_not(self):
        result = self._cycle()
        payload = attribution.build(result, self.strategies)
        for o in payload["orders"]:
            self.assertTrue(o["client_order_id"])
        for r in payload["intents"]:
            self.assertNotIn("client_order_id", r,
                             "an intent record must never carry an order id; "
                             "linkage is by symbol into orders[]")

    def test_unattributed_is_explicit_never_guessed(self):
        result = self._cycle()
        stray = _intent(symbol=Symbol("SOL"))
        self.assertEqual(resolve(self.strategies, stray).strategy_id, "UNATTRIBUTED")

    def test_forget_clears_per_cycle_maps(self):
        self._cycle()
        forget_all(self.strategies)
        self.assertEqual(resolve(self.strategies, self.i1).strategy_id, "UNATTRIBUTED")


# ------------------------------------------------------- PERSISTENCE
class TestAttributionPersistence(_RealPaperEngineCase):

    def _one(self):
        i1 = _intent(symbol=Symbol("BTC"))
        s = AttributedStrategy(_FixedIntentStrategy(i1, "alpha_a"), ALPHA_ID)
        return self._run((s,)), (s,)

    def test_exactly_one_attribution_event_per_cycle(self):
        result, strategies = self._one()
        self.assertIsNone(attribution.record(self.engine.event_store, result, strategies))
        events = [e for e in self.engine.event_store.replay()
                  if e.event_type is EventType.TRADE_ATTRIBUTION]
        self.assertEqual(len(events), 1)

    def test_replaying_the_new_event_type_does_not_disturb_the_store(self):
        result, strategies = self._one()
        before = len(list(self.engine.event_store.replay()))
        attribution.record(self.engine.event_store, result, strategies)
        after = list(self.engine.event_store.replay())
        self.assertEqual(len(after), before + 1)
        self.assertIs(after[-1].event_type, EventType.TRADE_ATTRIBUTION)

    def test_a_later_append_cannot_mutate_the_earlier_record(self):
        result, strategies = self._one()
        attribution.record(self.engine.event_store, result, strategies)
        first = [e for e in self.engine.event_store.replay()
                 if e.event_type is EventType.TRADE_ATTRIBUTION][0]
        original = json.dumps(dict(first.payload), sort_keys=True, default=str)
        self.engine.event_store.append(
            EventType.TRADE_ATTRIBUTION,
            {"schema": 1, "evaluated_at_utc": "later", "intents": [], "orders": [],
             "post_trade_note": "assessment appended afterwards"})
        again = [e for e in self.engine.event_store.replay()
                 if e.event_type is EventType.TRADE_ATTRIBUTION][0]
        self.assertEqual(json.dumps(dict(again.payload), sort_keys=True, default=str), original,
                         "append-only: an earlier attribution record must be immutable")

    def test_failure_returns_a_reason_and_never_raises(self):
        result, strategies = self._one()

        class _Broken:
            def append(self, *a, **k):
                raise RuntimeError("disk on fire")

        reason = attribution.record(_Broken(), result, strategies)
        self.assertIsNotNone(reason)
        self.assertIn("RuntimeError", reason)


# ------------------------------------------------------ FEATURE POLICY
class TestFeatureSnapshotPolicy(_RealPaperEngineCase):

    def test_feature_cap_is_enforced_and_flagged(self):
        i1 = _intent(symbol=Symbol("BTC"))
        s = AttributedStrategy(_FixedIntentStrategy(i1, "alpha_a"), ALPHA_ID)
        result = self._run((s,))
        many = {f"f{n}": Decimal(n) for n in range(MAX_FEATURES_PER_INTENT + 40)}
        payload = attribution.build(result, (s,), features_by_intent={id(i1): many})
        rec = [r for r in payload["intents"] if r["symbol"] == "BTC"][0]
        self.assertEqual(len(rec["features"]), MAX_FEATURES_PER_INTENT)
        self.assertTrue(rec["features_truncated"])

    def test_non_scalar_features_are_dropped_not_serialised(self):
        i1 = _intent(symbol=Symbol("BTC"))
        s = AttributedStrategy(_FixedIntentStrategy(i1, "alpha_a"), ALPHA_ID)
        result = self._run((s,))
        payload = attribution.build(result, (s,), features_by_intent={
            id(i1): {"ok": Decimal("1"), "candles": [1, 2, 3], "book": {"bids": []}}})
        rec = [r for r in payload["intents"] if r["symbol"] == "BTC"][0]
        self.assertIn("ok", rec["features"])
        self.assertNotIn("candles", rec["features"])
        self.assertNotIn("book", rec["features"])

    def test_payload_stays_below_the_event_store_limit(self):
        i1 = _intent(symbol=Symbol("BTC"))
        s = AttributedStrategy(_FixedIntentStrategy(i1, "alpha_a"), ALPHA_ID)
        result = self._run((s,))
        many = {f"feature_with_a_long_name_{n}": Decimal("1.2345678901234567890")
                for n in range(MAX_FEATURES_PER_INTENT)}
        payload = attribution.build(result, (s,), features_by_intent={id(i1): many})
        size = len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
        self.assertLess(size, MAX_PAYLOAD_BYTES)

    def test_decimals_serialise_deterministically_as_strings(self):
        i1 = _intent(symbol=Symbol("BTC"))
        s = AttributedStrategy(_FixedIntentStrategy(i1, "alpha_a"), ALPHA_ID)
        result = self._run((s,))
        payload = attribution.build(result, (s,),
                                    features_by_intent={id(i1): {"x": Decimal("0.1")}})
        rec = [r for r in payload["intents"] if r["symbol"] == "BTC"][0]
        self.assertEqual(rec["features"]["x"], "0.1")
        self.assertIsInstance(rec["stop_price"], str)


# --------------------------------------------------- RESEARCH BOUNDARY
class TestResearchBoundary(unittest.TestCase):

    def test_probe_kind_comes_from_the_registry(self):
        self.assertIs(get_plugin("lifecycle_probe").kind, PluginKind.ENGINE_TEST)

    def test_no_second_classification_enum_was_created(self):
        from alpha_engine.platform import attributed_strategy as mod
        self.assertFalse(
            [n for n in dir(mod)
             if n.endswith("Kind") and n != "PluginKind" and isinstance(getattr(mod, n), type)],
            "strategy_kind must come from PluginKind, not a parallel enum")

    def test_engine_test_never_appears_in_alpha_surfaces(self):
        from pathlib import Path
        for doc in ("docs/ALPHA_LIBRARY.md", "docs/RESEARCH_LEDGER.md",
                    "docs/ALPHA_SCORECARD.md", "docs/RESEARCH_DECISIONS.md"):
            p = Path(doc)
            if p.is_file():
                text = p.read_text(encoding="utf-8")
                self.assertNotIn("lifecycle_probe", text)
                self.assertNotIn("TRADE_ATTRIBUTION", text)


if __name__ == "__main__":
    unittest.main()
