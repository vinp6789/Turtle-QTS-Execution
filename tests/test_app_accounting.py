"""Regression tests for the C1 fix (app/runtime/accounting.py).

THE PREVIOUS FAILURE (audit finding C1): fills never reached
PositionManager/PortfolioManager, so every cycle's risk evaluation saw
open_positions=(), heat=0, exposure=0 -- a strategy emitting the same
intent every cycle stacked a full-size position EVERY cycle, and
max_positions could never trigger. TestC1Regression reproduces exactly
that scenario and asserts the fix closes it: after cycle 1's order fills,
cycle 2 is REJECTED with MAX_POSITIONS_EXCEEDED -- a rejection that was
STRUCTURALLY IMPOSSIBLE before the fix, because the open-position count
risk_manager compares against was always zero.

Also proven here: duplicate-fill immunity (same fills re-synced -> zero
new events, zero accounting drift), restart immunity (a rebuilt
AccountingSync on the same store re-syncs the same fills as a durable
no-op), exactly-once initial deposit, and the reduce-only exit path.
"""

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from exchange_adapter import FundingRate, MarkPrice, OrderSide, OrderType, Symbol, TimeInForce
from risk_manager import ReasonCode

from app.runtime import AppSettings, AppState
from app.runtime.accounting import AccountingSync
from trading_system.strategy import Strategy, TradeIntent

_SIGNING_ENV = {"TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1": "signing-secret-material"}


class _FixedIntentStrategy(Strategy):
    """Emits the identical intent every cycle -- the exact C1 stacking
    scenario. Test-only stub, not a trading strategy."""

    def __init__(self, intent):
        self._intent = intent

    @property
    def name(self):
        return "c1-repro"

    def generate_intents(self, context):
        return (self._intent,)


def _intent(**overrides):
    fields = dict(
        symbol=Symbol("BTC"), side=OrderSide.BUY, order_type=OrderType.LIMIT,
        time_in_force=TimeInForce.GTC, reduce_only=False, stop_price=Decimal("90"),
        limit_price=Decimal("100"),
    )
    fields.update(overrides)
    return TradeIntent(**fields)


class _AccountingCase(unittest.TestCase):
    """Real paper engine + one-shot initial deposit + risk profile with
    max_positions=1 (so the C1 stacking scenario has a hard limit to hit)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.env = {
            **_SIGNING_ENV,
            "ENGINE_CONFIG_PATH": "deploy/engine.paper.toml",
            "ENGINE_STORE_PATH": str(Path(self._tmp.name) / "events.log"),
            "PORTFOLIO_INITIAL_DEPOSIT": "100000",
            # BALANCED profile in deploy/engine.paper.toml has max_positions=3;
            # risk profile for cycles is passed per-call below.
        }
        self.settings = AppSettings.from_env(self.env)
        self.strategy = _FixedIntentStrategy(_intent())
        self.state = AppState.create(self.settings, env=self.env, strategies=(self.strategy,))
        self.addCleanup(self.state.shutdown)
        # Tighten the profile to max_positions=1 for a crisp stacking test.
        from dataclasses import replace
        self.state.risk_profile = replace(self.state.risk_profile, max_positions=1, risk_pct_per_trade=0.02)
        adapter = self.state.engine.adapter
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        adapter.set_mark_price(MarkPrice(symbol=Symbol("BTC"), price=Decimal("100"), timestamp_utc=now))
        adapter.set_funding_rate(FundingRate(symbol=Symbol("BTC"), rate=Decimal("0.0001"),
                                             next_funding_time_utc=now, timestamp_utc=now))

    def _event_count(self) -> int:
        return len(tuple(self.state.engine.event_store.replay()))

    def _fill_last_order(self):
        """Simulates the venue fully filling the most recently placed order."""
        adapter = self.state.engine.adapter
        orders = adapter.get_orders()
        self.assertTrue(orders, "expected an open order to fill")
        order = orders[-1]
        adapter.simulate_fill(order.exchange_order_id, order.quantity, order.limit_price)
        return order


class TestC1Regression(_AccountingCase):
    def test_second_identical_cycle_is_rejected_instead_of_stacking(self):
        # Cycle 1: the intent is approved and a real order is placed.
        result1 = self.state.run_one_cycle()
        self.assertEqual(len(result1.construction.approved), 1)
        self.assertEqual(len(result1.executions), 1)

        # Venue fills the order between cycles.
        self._fill_last_order()

        # Cycle 2: the SAME intent again. PRE-FIX this was approved every
        # time (open_positions was always empty). POST-FIX the pre-cycle
        # accounting sync books the fill into a real position, so
        # RiskManager now sees 1 open position >= max_positions=1.
        result2 = self.state.run_one_cycle()
        self.assertEqual(result2.construction.approved, ())
        self.assertEqual(result2.executions, ())
        self.assertEqual(len(result2.construction.rejected), 1)
        reasons = result2.construction.rejected[0].decision.reason_codes
        self.assertIn(ReasonCode.MAX_POSITIONS_EXCEEDED, reasons)

    def test_fill_is_booked_into_position_and_portfolio(self):
        self.state.run_one_cycle()
        filled_order = self._fill_last_order()
        self.state.run_one_cycle()  # pre-cycle sync books the fill

        # Portfolio now reflects the position: margin allocated, position open.
        snapshot = self.state.engine.portfolio_manager.get_snapshot()
        self.assertEqual(len(snapshot.open_position_ids), 1)
        expected_margin = filled_order.quantity * filled_order.limit_price  # leverage 1
        self.assertEqual(snapshot.used_margin, expected_margin)
        self.assertGreater(snapshot.exposure, 0)
        self.assertGreater(snapshot.heat, 0)

        # PositionManager holds the filled position.
        pid = snapshot.open_position_ids[0]
        position = self.state.engine.position_manager.get_position(pid)
        self.assertEqual(position.filled_quantity, filled_order.quantity)
        self.assertEqual(position.symbol, Symbol("BTC"))
        self.assertEqual(position.stop_price, Decimal("90"))

        # OrderManager recorded the fill too (dispatch route).
        order_snapshot = self.state.engine.order_manager.get_order_status(filled_order.client_order_id)
        self.assertEqual(order_snapshot.filled_quantity, filled_order.quantity)


class TestDuplicateFillImmunity(_AccountingCase):
    def test_resyncing_the_same_fills_changes_nothing(self):
        self.state.run_one_cycle()
        self._fill_last_order()
        self.state.run_one_cycle()  # fill booked here

        events_before = self._event_count()
        portfolio_before = self.state.engine.portfolio_manager.get_snapshot()

        # The venue fill history is re-fetched and re-processed -- three times.
        for _ in range(3):
            notes = self.state.accounting.sync()
            self.assertEqual(notes, [])

        self.assertEqual(self._event_count(), events_before)  # zero new events
        portfolio_after = self.state.engine.portfolio_manager.get_snapshot()
        self.assertEqual(portfolio_after.used_margin, portfolio_before.used_margin)
        self.assertEqual(portfolio_after.fees_cumulative, portfolio_before.fees_cumulative)
        self.assertEqual(portfolio_after.open_position_ids, portfolio_before.open_position_ids)

    def test_rebuilt_accounting_sync_is_also_a_no_op(self):
        """Simulates a process restart at the accounting layer: a FRESH
        AccountingSync rebuilds its order->position map from the durable
        store and re-syncing the same venue fills must change nothing --
        in particular it must NOT create a duplicate position."""
        self.state.run_one_cycle()
        self._fill_last_order()
        self.state.run_one_cycle()

        events_before = self._event_count()
        positions_before = self.state.engine.portfolio_manager.get_snapshot().open_position_ids

        rebuilt = AccountingSync(self.state.engine, target_leverage=self.settings.target_leverage)
        notes = rebuilt.sync()
        self.assertEqual(notes, [])
        self.assertEqual(self._event_count(), events_before)
        self.assertEqual(
            self.state.engine.portfolio_manager.get_snapshot().open_position_ids, positions_before,
        )


class TestInitialDepositExactlyOnce(_AccountingCase):
    def test_deposit_applied_once_across_restarts(self):
        self.assertEqual(
            self.state.engine.portfolio_manager.get_snapshot().deposits_cumulative, Decimal("100000"),
        )
        # "Restart": release the store lock, rebuild AppState from the SAME
        # env (same PORTFOLIO_INITIAL_DEPOSIT) on the same store.
        self.state.shutdown()
        state2 = AppState.create(self.settings, env=self.env)
        self.addCleanup(state2.shutdown)
        self.assertEqual(
            state2.engine.portfolio_manager.get_snapshot().deposits_cumulative, Decimal("100000"),
        )  # not 200000


class TestReduceOnlyExit(_AccountingCase):
    def test_reduce_only_fill_closes_the_position_and_releases_margin(self):
        self.state.run_one_cycle()
        entry_order = self._fill_last_order()
        self.state.run_one_cycle()  # entry booked
        snapshot = self.state.engine.portfolio_manager.get_snapshot()
        self.assertEqual(len(snapshot.open_position_ids), 1)
        fees_after_entry = snapshot.fees_cumulative

        # A reduce-only SELL closes the long at 110 (profit 10/unit).
        exit_snapshot = self.state.engine.order_manager.place_order(
            symbol=Symbol("BTC"), side=OrderSide.SELL, order_type=OrderType.LIMIT,
            quantity=entry_order.quantity, limit_price=Decimal("110"), reduce_only=True,
        )
        self.state.engine.adapter.simulate_fill(
            exit_snapshot.exchange_order_id, entry_order.quantity, Decimal("110"),
        )
        notes = self.state.accounting.sync()
        self.assertEqual([n for n in notes if "failed" in n], [])

        final = self.state.engine.portfolio_manager.get_snapshot()
        self.assertEqual(final.open_position_ids, ())          # margin released, position closed
        self.assertEqual(final.used_margin, Decimal("0"))
        self.assertGreater(final.realized_pnl_cumulative, Decimal("0"))  # profitable close, net of fee
        self.assertGreaterEqual(final.available_cash, Decimal("100000") - fees_after_entry)


class TestF1CrashWindowHealing(_AccountingCase):
    """F1 regression: a crash between the position fsync and the portfolio
    fsync previously orphaned the portfolio leg FOREVER (the delta gate
    skipped re-application). Now the fill-id-keyed durable ledger heals it
    on the next sync."""

    def test_entry_margin_heals_after_crash_between_fill_and_reserve(self):
        self.state.run_one_cycle()
        self._fill_last_order()
        pm = self.state.engine.portfolio_manager

        def crash(*args, **kwargs):
            raise RuntimeError("simulated crash before margin fsync")

        pm.reserve_margin = crash  # instance shadow = crash simulation
        with self.assertRaises(RuntimeError):
            self.state.accounting.sync()
        del pm.reserve_margin      # "restart": real method restored

        rebuilt = AccountingSync(self.state.engine, target_leverage=self.settings.target_leverage)
        notes = rebuilt.sync()
        snapshot = pm.get_snapshot()
        # PRE-FIX: used_margin stayed 0 and open_position_ids stayed ()
        # forever (probe P7). POST-FIX: healed.
        self.assertEqual(len(snapshot.open_position_ids), 1)
        self.assertGreater(snapshot.used_margin, Decimal("0"))
        self.assertEqual([n for n in notes if "failed" in n], [])

    def test_exit_realized_and_release_heal_after_crash(self):
        self.state.run_one_cycle()
        entry_order = self._fill_last_order()
        self.state.run_one_cycle()
        exit_snapshot = self.state.engine.order_manager.place_order(
            symbol=Symbol("BTC"), side=OrderSide.SELL, order_type=OrderType.LIMIT,
            quantity=entry_order.quantity, limit_price=Decimal("110"), reduce_only=True,
        )
        self.state.engine.adapter.simulate_fill(
            exit_snapshot.exchange_order_id, entry_order.quantity, Decimal("110"),
        )
        pm = self.state.engine.portfolio_manager

        def crash(*args, **kwargs):
            raise RuntimeError("simulated crash before realized fsync")

        pm.apply_realized_pnl = crash
        with self.assertRaises(RuntimeError):
            self.state.accounting.sync()
        del pm.apply_realized_pnl

        # The position is already CLOSED at this point; the durable
        # exit-cid mapping (appended BEFORE record_exit) is what lets a
        # rebuilt sync still attribute and heal it.
        rebuilt = AccountingSync(self.state.engine, target_leverage=self.settings.target_leverage)
        rebuilt.sync()
        snapshot = pm.get_snapshot()
        self.assertEqual(snapshot.realized_pnl_cumulative,
                         (Decimal("110") - Decimal("100")) * entry_order.quantity)
        self.assertEqual(snapshot.open_position_ids, ())
        self.assertEqual(snapshot.used_margin, Decimal("0"))


class TestLevelsCrashWindow(_AccountingCase):
    """Regression for the levels-recording crash window: levels were
    previously batch-recorded AFTER the whole execution loop, so a crash
    (or a later order's placement failure) after order 1 was live at the
    venue lost order 1's stop/entry metadata permanently -- its fills
    could never be booked into a position. The on_execution hook now
    records each order's levels immediately after its own execute_place
    returns."""

    def _levels_events(self):
        return [e for e in self.state.engine.event_store.replay()
                if e.payload.get("source") == "app_accounting"
                and e.payload.get("action") == "order_levels_recorded"]

    def test_first_orders_levels_survive_a_mid_loop_failure(self):
        from exchange_adapter import ExchangeConnectionError, FundingRate

        # Two intents: BTC (conviction 0.9, placed first), ETH (0.1, second).
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        adapter = self.state.engine.adapter
        adapter.set_mark_price(MarkPrice(symbol=Symbol("ETH"), price=Decimal("50"), timestamp_utc=now))
        adapter.set_funding_rate(FundingRate(symbol=Symbol("ETH"), rate=Decimal("0.0001"),
                                              next_funding_time_utc=now, timestamp_utc=now))
        from dataclasses import replace
        self.state.risk_profile = replace(self.state.risk_profile, max_positions=3)
        self.state.strategies = (
            _FixedIntentStrategy(_intent(conviction=Decimal("0.9"))),
            _FixedIntentStrategy(_intent(
                symbol=Symbol("ETH"), stop_price=Decimal("45"), limit_price=Decimal("50"),
                conviction=Decimal("0.1"),
            )),
        )

        original_transmit = adapter._transmit_place_order
        calls = {"n": 0}

        def flaky(request):
            calls["n"] += 1
            if calls["n"] == 2:
                raise ExchangeConnectionError("simulated failure on second order")
            return original_transmit(request)

        adapter._transmit_place_order = flaky
        with self.assertRaises(ExchangeConnectionError):
            self.state.run_one_cycle()
        adapter._transmit_place_order = original_transmit

        # PRE-FIX: zero levels events survived the abort. POST-FIX: order 1's
        # levels were appended by the hook before order 2 was attempted.
        self.assertEqual(len(self._levels_events()), 1)

        # Order 1 is live at the venue; it fills; a rebuilt ("restarted")
        # accounting layer books it -- position and margin become risk-visible.
        order = adapter.get_orders()[-1]
        adapter.simulate_fill(order.exchange_order_id, order.quantity, order.limit_price)
        rebuilt = AccountingSync(self.state.engine, target_leverage=self.settings.target_leverage)
        notes = rebuilt.sync()
        self.assertFalse(any("no recorded stop/entry" in n for n in notes), notes)
        snapshot = self.state.engine.portfolio_manager.get_snapshot()
        self.assertEqual(len(snapshot.open_position_ids), 1)
        self.assertGreater(snapshot.used_margin, Decimal("0"))

    def test_hook_plus_batch_recording_appends_exactly_one_levels_event(self):
        # The per-execution hook AND the redundant post-cycle batch both
        # run on a normal cycle; idempotency-per-cid must yield exactly
        # ONE durable levels event per order (no duplicate writes).
        self.state.run_one_cycle()
        self.assertEqual(len(self._levels_events()), 1)


class TestF2PartialExitConservative(_AccountingCase):
    """F2 SAFETY regression (its guarantees, now generalized by H-B): a
    partial reduce-only fill must NEVER corrupt the position lifecycle or
    over-release margin. Under H-B a first partial tranche books its PnL
    and leaves the position open (awaiting the remaining fills) -- the
    conservative safety properties (not CLOSED, margin intact, slot held)
    are unchanged; the full close is completed by the remaining fills
    (see TestHBMultiFillClose). A full-quantity exit still closes cleanly."""

    def test_first_partial_tranche_books_pnl_without_corrupting_state(self):
        self.state.run_one_cycle()
        entry_order = self._fill_last_order()
        self.state.run_one_cycle()
        partial_qty = entry_order.quantity / 2
        exit_snapshot = self.state.engine.order_manager.place_order(
            symbol=Symbol("BTC"), side=OrderSide.SELL, order_type=OrderType.LIMIT,
            quantity=partial_qty, limit_price=Decimal("110"), reduce_only=True,
        )
        self.state.engine.adapter.simulate_fill(
            exit_snapshot.exchange_order_id, partial_qty, Decimal("110"),
        )
        notes = self.state.accounting.sync()
        # H-B: partial close is booked, not silently skipped.
        self.assertTrue(any("partial close" in n for n in notes), notes)

        snapshot = self.state.engine.portfolio_manager.get_snapshot()
        # SAFETY (unchanged from F2): position NOT closed, margin intact.
        self.assertEqual(len(snapshot.open_position_ids), 1)
        pid = snapshot.open_position_ids[0]
        position = self.state.engine.position_manager.get_position(pid)
        self.assertNotIn(position.lifecycle_state.value, ("CLOSED", "ARCHIVED"))
        self.assertEqual(position.remaining_quantity, entry_order.quantity)
        self.assertGreater(snapshot.used_margin, Decimal("0"))
        # H-B improvement: the closed tranche's realized PnL IS booked
        # (pre-H-B it was lost). Half of qty closed at 110 vs entry 100.
        self.assertEqual(snapshot.realized_pnl_cumulative,
                         (Decimal("110") - Decimal("100")) * partial_qty)

    def test_full_quantity_exit_still_closes_cleanly(self):
        self.state.run_one_cycle()
        entry_order = self._fill_last_order()
        self.state.run_one_cycle()
        exit_snapshot = self.state.engine.order_manager.place_order(
            symbol=Symbol("BTC"), side=OrderSide.SELL, order_type=OrderType.LIMIT,
            quantity=entry_order.quantity, limit_price=Decimal("110"), reduce_only=True,
        )
        self.state.engine.adapter.simulate_fill(
            exit_snapshot.exchange_order_id, entry_order.quantity, Decimal("110"),
        )
        self.state.accounting.sync()
        snapshot = self.state.engine.portfolio_manager.get_snapshot()
        self.assertEqual(snapshot.open_position_ids, ())
        self.assertEqual(snapshot.used_margin, Decimal("0"))
        self.assertEqual(snapshot.realized_pnl_cumulative,
                         (Decimal("110") - Decimal("100")) * entry_order.quantity)


class TestF3ShortSidePnl(_AccountingCase):
    """F3 regression: short positions previously booked INVERTED realized
    and unrealized PnL (frozen Module 7 is long-only). The accounting
    layer now computes both side-aware."""

    def _open_short(self):
        self.state.strategies = (_FixedIntentStrategy(_intent(
            side=OrderSide.SELL, stop_price=Decimal("110"), limit_price=Decimal("100"),
        )),)
        self.state.run_one_cycle()
        entry_order = self._fill_last_order()
        self.state.run_one_cycle()
        return entry_order

    def test_profitable_short_books_positive_unrealized(self):
        entry_order = self._open_short()
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        self.state.engine.adapter.set_mark_price(
            MarkPrice(symbol=Symbol("BTC"), price=Decimal("95"), timestamp_utc=now),
        )
        self.state.accounting.update_marks()
        snapshot = self.state.engine.portfolio_manager.get_snapshot()
        expected = (Decimal("100") - Decimal("95")) * entry_order.quantity  # PRE-FIX: -expected
        self.assertEqual(snapshot.unrealized_pnl, expected)
        self.assertEqual(snapshot.equity, Decimal("100000") + expected)

    def test_profitable_short_close_books_positive_realized(self):
        entry_order = self._open_short()
        exit_snapshot = self.state.engine.order_manager.place_order(
            symbol=Symbol("BTC"), side=OrderSide.BUY, order_type=OrderType.LIMIT,
            quantity=entry_order.quantity, limit_price=Decimal("95"), reduce_only=True,
        )
        self.state.engine.adapter.simulate_fill(
            exit_snapshot.exchange_order_id, entry_order.quantity, Decimal("95"),
        )
        self.state.accounting.sync()
        snapshot = self.state.engine.portfolio_manager.get_snapshot()
        expected = (Decimal("100") - Decimal("95")) * entry_order.quantity  # PRE-FIX: -expected
        self.assertEqual(snapshot.realized_pnl_cumulative, expected)

    def test_losing_short_books_negative_unrealized(self):
        entry_order = self._open_short()
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        self.state.engine.adapter.set_mark_price(
            MarkPrice(symbol=Symbol("BTC"), price=Decimal("103"), timestamp_utc=now),
        )
        self.state.accounting.update_marks()
        snapshot = self.state.engine.portfolio_manager.get_snapshot()
        expected = (Decimal("100") - Decimal("103")) * entry_order.quantity  # negative
        self.assertEqual(snapshot.unrealized_pnl, expected)
        self.assertLess(snapshot.unrealized_pnl, Decimal("0"))


if __name__ == "__main__":
    unittest.main()
