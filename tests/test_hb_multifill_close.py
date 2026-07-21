"""H-B regression: reduce-only closes that arrive in MULTIPLE fills.

THE PREVIOUS FAILURE: accounting booked an exit only when
fill.quantity == remaining_position_quantity. A venue splitting a close
(200 -> 60 + 80 + 60) matched none, so the position never closed locally,
margin never released, the slot was consumed forever, and the engine
eventually bricked. H-B books each tranche's realized PnL per fill and
finalizes (single record_exit(CLOSE) + release_margin) exactly once when
the accumulated close reaches the position's open size.

Entry sizing here: equity 100000 x risk 0.02 = 2000 risk; stop_d
|100-90| = 10 -> quantity 200 @ entry 100 -> used_margin 20000. A long
closed at 110 realizes (110-100) x qty.
"""

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from exchange_adapter import FundingRate, MarkPrice, OrderSide, OrderType, Symbol, TimeInForce

from app.runtime import AppSettings, AppState
from app.runtime.accounting import AccountingSync
from trading_system.strategy import Strategy, TradeIntent

_SIGNING_ENV = {"TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1": "signing-secret-material"}


class _OneShotStrategy(Strategy):
    """Emits an entry intent only until the position exists, so exactly one
    entry order is placed (H-A suppression also guards this)."""

    @property
    def name(self):
        return "hb-entry"

    def generate_intents(self, context):
        if context.open_positions:
            return ()
        return (TradeIntent(
            symbol=Symbol("BTC"), side=OrderSide.BUY, order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.GTC, reduce_only=False,
            stop_price=Decimal("90"), limit_price=Decimal("100")),)


class _MultiFillCase(unittest.TestCase):
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
        self.state = AppState.create(self.settings, env=self.env, strategies=(_OneShotStrategy(),))
        self.addCleanup(self.state.shutdown)
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        a = self.state.engine.adapter
        a.set_mark_price(MarkPrice(symbol=Symbol("BTC"), price=Decimal("100"), timestamp_utc=now))
        a.set_funding_rate(FundingRate(symbol=Symbol("BTC"), rate=Decimal("0.0001"),
                                       next_funding_time_utc=now, timestamp_utc=now))
        from dataclasses import replace
        self.state.risk_profile = replace(self.state.risk_profile, max_positions=3, risk_pct_per_trade=0.02)

    def _open_position(self):
        """Places + fully fills the entry order, books it. Returns (pid, qty)."""
        self.state.run_one_cycle()                 # places entry order
        order = self.state.engine.adapter.get_orders()[-1]
        self.state.engine.adapter.simulate_fill(order.exchange_order_id, order.quantity, order.limit_price)
        self.state.run_one_cycle()                 # books the entry
        snap = self.state.engine.portfolio_manager.get_snapshot()
        self.assertEqual(len(snap.open_position_ids), 1)
        pid = snap.open_position_ids[0]
        return pid, self.state.engine.position_manager.get_position(pid).filled_quantity

    def _place_reduce_only(self, qty):
        return self.state.engine.order_manager.place_order(
            symbol=Symbol("BTC"), side=OrderSide.SELL, order_type=OrderType.LIMIT,
            quantity=qty, limit_price=Decimal("110"), reduce_only=True)

    def _fill(self, order_ex_id, qty, price="110"):
        self.state.engine.adapter.simulate_fill(order_ex_id, Decimal(qty), Decimal(price))

    def _event_count(self):
        return len(tuple(self.state.engine.event_store.replay()))

    def _close_in_tranches(self, total_qty, tranches):
        """Places one reduce-only order for total_qty, fills it in the
        given tranches (syncing after each), returns the portfolio snapshot."""
        exit_order = self._place_reduce_only(total_qty)
        for q in tranches:
            self._fill(exit_order.exchange_order_id, q)
            self.state.accounting.sync()
        return self.state.engine.portfolio_manager.get_snapshot()


class TestMultiFillClose(_MultiFillCase):
    def test_two_fill_close(self):
        pid, qty = self._open_position()
        snap = self._close_in_tranches(qty, [qty / 2, qty / 2])
        self.assertEqual(snap.open_position_ids, ())               # slot freed
        self.assertEqual(snap.used_margin, Decimal("0"))            # margin released
        self.assertEqual(snap.realized_pnl_cumulative, (Decimal("110") - Decimal("100")) * qty)

    def test_three_fill_close_uneven(self):
        pid, qty = self._open_position()                           # qty == 200
        snap = self._close_in_tranches(qty, [Decimal("30"), Decimal("40"), qty - Decimal("70")])
        self.assertEqual(snap.open_position_ids, ())
        self.assertEqual(snap.used_margin, Decimal("0"))
        self.assertEqual(snap.realized_pnl_cumulative, (Decimal("110") - Decimal("100")) * qty)

    def test_n_fills_close(self):
        pid, qty = self._open_position()
        per = qty / 5
        snap = self._close_in_tranches(qty, [per, per, per, per, per])
        self.assertEqual(snap.open_position_ids, ())
        self.assertEqual(snap.realized_pnl_cumulative, (Decimal("110") - Decimal("100")) * qty)

    def test_tiny_remainder_fill_completes_the_close(self):
        pid, qty = self._open_position()
        snap = self._close_in_tranches(qty, [qty - Decimal("1"), Decimal("1")])
        self.assertEqual(snap.open_position_ids, ())
        self.assertEqual(snap.used_margin, Decimal("0"))

    def test_partial_close_leaves_position_open_and_margin_held(self):
        pid, qty = self._open_position()
        exit_order = self._place_reduce_only(qty)
        self._fill(exit_order.exchange_order_id, qty / 2)          # only half fills
        notes = self.state.accounting.sync()
        snap = self.state.engine.portfolio_manager.get_snapshot()
        self.assertEqual(len(snap.open_position_ids), 1)           # NOT closed
        self.assertGreater(snap.used_margin, Decimal("0"))         # margin still held
        self.assertTrue(any("partial close" in n for n in notes))
        # But the closed half's PnL IS booked (H-B, not lost like pre-fix).
        self.assertEqual(snap.realized_pnl_cumulative, (Decimal("110") - Decimal("100")) * (qty / 2))


class TestExactlyOnce(_MultiFillCase):
    def test_realized_pnl_exactly_once_and_margin_released_once(self):
        pid, qty = self._open_position()
        snap = self._close_in_tranches(qty, [Decimal("60"), Decimal("80"), Decimal("60")])
        expected = (Decimal("110") - Decimal("100")) * qty
        self.assertEqual(snap.realized_pnl_cumulative, expected)

        events_before = self._event_count()
        # Re-sync the identical fill history three times -- must be a total no-op.
        for _ in range(3):
            self.assertEqual(self.state.accounting.sync(), [])
        self.assertEqual(self._event_count(), events_before)       # zero new events
        after = self.state.engine.portfolio_manager.get_snapshot()
        self.assertEqual(after.realized_pnl_cumulative, expected)  # not doubled
        self.assertEqual(after.used_margin, Decimal("0"))          # not double-released

    def test_duplicate_fill_replay_via_rebuilt_accounting_is_noop(self):
        pid, qty = self._open_position()
        self._close_in_tranches(qty, [Decimal("100"), Decimal("100")])
        events_before = self._event_count()
        before = self.state.engine.portfolio_manager.get_snapshot()
        # Simulate an accounting-layer restart: rebuild maps from EventStore,
        # reset the in-memory accumulation, re-process the SAME venue fills.
        rebuilt = AccountingSync(self.state.engine, target_leverage=self.settings.target_leverage)
        self.assertEqual(rebuilt.sync(), [])
        self.assertEqual(self._event_count(), events_before)
        after = self.state.engine.portfolio_manager.get_snapshot()
        self.assertEqual(after.realized_pnl_cumulative, before.realized_pnl_cumulative)
        self.assertEqual(after.open_position_ids, before.open_position_ids)


class TestReplayAndCrash(_MultiFillCase):
    def test_full_process_restart_replays_the_closed_books(self):
        pid, qty = self._open_position()
        self._close_in_tranches(qty, [Decimal("70"), Decimal("70"), Decimal("60")])
        before = self.state.engine.portfolio_manager.get_snapshot()
        self.state.shutdown()
        # Full restart: EventStore replay must reconstruct the durable
        # portfolio truth (realized PnL, released margin, freed slot)
        # WITHOUT needing the venue fill history.
        restarted = AppState.create(self.settings, env=self.env)
        self.addCleanup(restarted.shutdown)
        after = restarted.engine.portfolio_manager.get_snapshot()
        self.assertEqual(after.realized_pnl_cumulative, before.realized_pnl_cumulative)
        self.assertEqual(after.used_margin, Decimal("0"))
        self.assertEqual(after.open_position_ids, ())

    def test_crash_mid_close_then_resume(self):
        pid, qty = self._open_position()
        exit_order = self._place_reduce_only(qty)
        # Two tranches fill and are booked; then a "crash" (rebuild the
        # accounting layer) before the final tranche.
        self._fill(exit_order.exchange_order_id, Decimal("70"))
        self.state.accounting.sync()
        self._fill(exit_order.exchange_order_id, Decimal("70"))
        self.state.accounting.sync()
        mid = self.state.engine.portfolio_manager.get_snapshot()
        self.assertEqual(len(mid.open_position_ids), 1)            # still open (140/200)
        self.assertEqual(mid.realized_pnl_cumulative, (Decimal("110") - Decimal("100")) * Decimal("140"))

        self.state.accounting = AccountingSync(self.state.engine, target_leverage=self.settings.target_leverage)
        # Final tranche arrives after the "restart".
        self._fill(exit_order.exchange_order_id, Decimal("60"))
        self.state.accounting.sync()
        final = self.state.engine.portfolio_manager.get_snapshot()
        self.assertEqual(final.open_position_ids, ())              # completed
        self.assertEqual(final.used_margin, Decimal("0"))
        self.assertEqual(final.realized_pnl_cumulative, (Decimal("110") - Decimal("100")) * qty)

    def test_reconciliation_clean_after_multifill_close(self):
        pid, qty = self._open_position()
        self._close_in_tranches(qty, [Decimal("60"), Decimal("80"), Decimal("60")])
        # A fresh cycle runs reconciliation: local (no open positions) vs
        # venue (the mock order is fully filled, i.e. flat) -> match.
        result = self.state.run_one_cycle()
        self.assertTrue(result.reconciliation.matches, result.reconciliation.discrepancies)


class TestSingleFillUnchanged(_MultiFillCase):
    def test_single_fill_close_still_zeroes_remaining(self):
        pid, qty = self._open_position()
        snap = self._close_in_tranches(qty, [qty])                 # one fill == full size
        self.assertEqual(snap.open_position_ids, ())
        self.assertEqual(snap.used_margin, Decimal("0"))
        self.assertEqual(snap.realized_pnl_cumulative, (Decimal("110") - Decimal("100")) * qty)
        # Single-fill close is the ONE case that ends remaining == 0 exactly.
        pos = self.state.engine.position_manager.get_position(pid)
        self.assertEqual(pos.remaining_quantity, Decimal("0"))
        self.assertEqual(pos.lifecycle_state.value, "CLOSED")


if __name__ == "__main__":
    unittest.main()
