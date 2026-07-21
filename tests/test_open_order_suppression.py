"""Adversarial verification for the H-A fix: run_cycle suppresses intents
whose (symbol, reduce_only) already has a LIVE engine-owned order.

THE PREVIOUS FAILURE: StrategyContext exposes only FILLED positions, so a
resting limit order was invisible to the strategy on the next cycle; it
re-emitted the same intent, each cycle minted a NEW client_order_id, and
N cycles produced N resting orders -> N fills -> N x intended exposure.
TestStackingRegression reproduces exactly that sequence and asserts the
fix holds it to ONE order.
"""

import tempfile
import threading
import unittest
from decimal import Decimal
from pathlib import Path

from exchange_adapter import FundingRate, MarkPrice, OrderSide, OrderType, Symbol, TimeInForce

from app.runtime import AppSettings, AppState, EmergencyStopActive
from trading_system.strategy import Strategy, TradeIntent

_SIGNING_ENV = {"TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1": "signing-secret-material"}


class _FixedIntentStrategy(Strategy):
    """Re-emits the same intent every cycle -- the exact H-A hazard. The
    intents are swappable mid-test to model strategy behavior changes."""

    def __init__(self, *intents):
        self.intents = tuple(intents)

    @property
    def name(self):
        return "h-a-repro"

    def generate_intents(self, context):
        return self.intents


def _intent(**overrides):
    fields = dict(
        symbol=Symbol("BTC"), side=OrderSide.BUY, order_type=OrderType.LIMIT,
        time_in_force=TimeInForce.GTC, reduce_only=False, stop_price=Decimal("90"),
        limit_price=Decimal("100"),
    )
    fields.update(overrides)
    return TradeIntent(**fields)


def _live_orders(state):
    from exchange_adapter import OrderStatus
    return [o for o in state.engine.adapter.get_orders()
            if o.status not in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED)]


class _SuppressionCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.env = {
            **_SIGNING_ENV,
            "ENGINE_CONFIG_PATH": "deploy/engine.paper.toml",
            "ENGINE_STORE_PATH": str(Path(self._tmp.name) / "events.log"),
            "PORTFOLIO_INITIAL_DEPOSIT": "100000",
            "RISK_MAX_STALE_DATA_SECONDS": "3600",
        }
        self.settings = AppSettings.from_env(self.env)
        self.strategy = _FixedIntentStrategy(_intent())
        self.state = AppState.create(self.settings, env=self.env, strategies=(self.strategy,))
        self.addCleanup(self.state.shutdown)
        self._set_market()
        # Loosen max_positions so ONLY the suppression filter (not risk)
        # is what prevents stacking -- the adversarial point of H-A.
        from dataclasses import replace
        self.state.risk_profile = replace(self.state.risk_profile, max_positions=10,
                                          risk_pct_per_trade=0.01, heat_cap=0.5)

    def _set_market(self):
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        adapter = self.state.engine.adapter
        for sym, px in (("BTC", "100"), ("ETH", "50")):
            adapter.set_mark_price(MarkPrice(symbol=Symbol(sym), price=Decimal(px), timestamp_utc=now))
            adapter.set_funding_rate(FundingRate(symbol=Symbol(sym), rate=Decimal("0.0001"),
                                                  next_funding_time_utc=now, timestamp_utc=now))


class TestStackingRegression(_SuppressionCase):
    def test_three_cycles_same_intent_place_exactly_one_order(self):
        """THE H-A HEADLINE. Pre-fix: cycle1 -> order A, cycle2 -> order B,
        cycle3 -> order C, all resting, 3x exposure after fills. Post-fix:
        exactly one order ever rests."""
        r1 = self.state.run_one_cycle()
        self.assertEqual(len(r1.executions), 1)
        self.assertEqual(r1.suppressed_by_open_orders, ())

        r2 = self.state.run_one_cycle()
        r3 = self.state.run_one_cycle()
        self.assertEqual(r2.executions, ())
        self.assertEqual(r3.executions, ())
        self.assertEqual(len(r2.suppressed_by_open_orders), 1)   # loud, not silent
        self.assertEqual(len(r3.suppressed_by_open_orders), 1)
        self.assertEqual(len(_live_orders(self.state)), 1)       # ONE resting order, ever
        # Nothing was silently dropped: raw intents still visible.
        self.assertEqual(len(r2.intents), 1)

    def test_multiple_resting_orders_different_symbols_each_suppress_their_own(self):
        self.strategy.intents = (
            _intent(symbol=Symbol("BTC")),
            _intent(symbol=Symbol("ETH"), limit_price=Decimal("50"), stop_price=Decimal("45")),
        )
        r1 = self.state.run_one_cycle()
        self.assertEqual(len(r1.executions), 2)
        r2 = self.state.run_one_cycle()
        self.assertEqual(r2.executions, ())
        self.assertEqual(len(r2.suppressed_by_open_orders), 2)
        self.assertEqual(len(_live_orders(self.state)), 2)

    def test_partial_fill_still_suppresses(self):
        r1 = self.state.run_one_cycle()
        order = r1.executions[0].order_snapshot
        # Venue partially fills the resting order -- it is still LIVE.
        self.state.engine.adapter.simulate_fill(
            order.exchange_order_id, order.quantity / 2, order.limit_price)
        r2 = self.state.run_one_cycle()
        self.assertEqual(r2.executions, ())
        self.assertEqual(len(r2.suppressed_by_open_orders), 1)
        self.assertEqual(len(_live_orders(self.state)), 1)

    def test_full_fill_lifts_suppression_and_risk_governs_the_next_intent(self):
        r1 = self.state.run_one_cycle()
        order = r1.executions[0].order_snapshot
        self.state.engine.adapter.simulate_fill(order.exchange_order_id, order.quantity, order.limit_price)
        r2 = self.state.run_one_cycle()
        # No live order remains -> the intent reaches construction again;
        # whether it is APPROVED is risk's decision (max_positions=10 here,
        # so a second, risk-governed order is legitimate).
        self.assertEqual(r2.suppressed_by_open_orders, ())
        self.assertEqual(len(r2.construction.approved) + len(r2.construction.rejected), 1)


class TestCancelReplaceAndCleanup(_SuppressionCase):
    def test_cancel_then_replace_places_a_new_order(self):
        r1 = self.state.run_one_cycle()
        cid = r1.executions[0].order_snapshot.client_order_id
        self.state.engine.order_manager.cancel_order(cid)
        self.assertEqual(_live_orders(self.state), [])          # stale order cleaned up
        r2 = self.state.run_one_cycle()
        self.assertEqual(len(r2.executions), 1)                  # replacement allowed
        self.assertEqual(r2.suppressed_by_open_orders, ())
        self.assertEqual(len(_live_orders(self.state)), 1)

    def test_reduce_only_close_is_never_blocked_by_a_resting_entry(self):
        self.state.run_one_cycle()                               # entry order now resting
        # Strategy pivots to a risk-REDUCING close while the entry rests.
        self.strategy.intents = (_intent(side=OrderSide.SELL, reduce_only=True,
                                          stop_price=Decimal("110")),)
        r2 = self.state.run_one_cycle()
        # The close intent must NOT be suppressed by the resting entry --
        # suppressing risk reduction would be the unsafe direction. (It
        # reaches construction; risk/capabilities then govern it.)
        self.assertEqual(r2.suppressed_by_open_orders, ())
        self.assertEqual(len(r2.construction.approved) + len(r2.construction.rejected)
                         + len(r2.construction.skipped), 1)

    def test_duplicate_reduce_only_closes_are_suppressed_against_each_other(self):
        # Place a resting reduce-only order directly, then have the
        # strategy emit another reduce-only intent for the same symbol.
        self.state.run_one_cycle()
        self.state.engine.order_manager.place_order(
            symbol=Symbol("BTC"), side=OrderSide.SELL, order_type=OrderType.LIMIT,
            quantity=Decimal("1"), limit_price=Decimal("110"), reduce_only=True)
        self.strategy.intents = (_intent(side=OrderSide.SELL, reduce_only=True,
                                          stop_price=Decimal("110")),)
        r = self.state.run_one_cycle()
        self.assertEqual(len(r.suppressed_by_open_orders), 1)    # no duplicate close
        self.assertEqual(r.executions, ())


class TestReplayAndCrash(_SuppressionCase):
    def test_suppressed_cycles_append_no_order_events(self):
        self.state.run_one_cycle()
        events_before = len(tuple(self.state.engine.event_store.replay()))
        r2 = self.state.run_one_cycle()                          # fully suppressed
        self.assertEqual(len(r2.suppressed_by_open_orders), 1)
        submit_events = [e for e in tuple(self.state.engine.event_store.replay())[events_before:]
                         if e.payload.get("source") == "order_manager"
                         and e.payload.get("action") == "SUBMIT"]
        self.assertEqual(submit_events, [])                      # suppression writes NOTHING

    def test_restart_replays_cleanly_and_suppression_follows_venue_truth(self):
        self.state.run_one_cycle()
        self.state.run_one_cycle()                               # suppressed
        self.state.shutdown()
        # Restart on the same store: replay must reconstruct without error.
        restarted = AppState.create(self.settings, env=self.env,
                                    strategies=(_FixedIntentStrategy(_intent()),))
        self.addCleanup(restarted.shutdown)
        # The mock venue forgets orders across restart (fresh adapter), so
        # venue truth says "nothing resting" -- a new order is correctly
        # allowed. (On live, frontendOpenOrders would still show the
        # resting order and suppression would hold: the filter reads venue
        # truth, never stale local state.)
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        restarted.engine.adapter.set_mark_price(MarkPrice(symbol=Symbol("BTC"), price=Decimal("100"), timestamp_utc=now))
        restarted.engine.adapter.set_funding_rate(FundingRate(symbol=Symbol("BTC"), rate=Decimal("0.0001"),
                                                               next_funding_time_utc=now, timestamp_utc=now))
        from dataclasses import replace
        restarted.risk_profile = replace(restarted.risk_profile, max_positions=10)
        result = restarted.run_one_cycle()
        self.assertEqual(result.suppressed_by_open_orders, ())

    def test_reconciliation_unaffected(self):
        r1 = self.state.run_one_cycle()
        r2 = self.state.run_one_cycle()
        self.assertTrue(r1.reconciliation.matches)
        self.assertTrue(r2.reconciliation.matches)


class TestConcurrencyAndStop(_SuppressionCase):
    def test_concurrent_cycles_serialize_and_never_stack(self):
        errors = []

        def cycle():
            try:
                self.state.run_one_cycle()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=cycle) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(_live_orders(self.state)), 1)       # lock + filter: ONE order

    def test_emergency_stop_interaction_unchanged(self):
        self.state.run_one_cycle()
        cancelled = self.state.emergency_stop()                  # H2: cancels the resting order
        self.assertEqual(len(cancelled), 1)
        with self.assertRaises(EmergencyStopActive):
            self.state.run_one_cycle()                           # M1 gate precedes the filter


if __name__ == "__main__":
    unittest.main()
