"""The measurement/accounting BOUNDARY -- the seam the old tests missed.

WHY THIS FILE EXISTS. test_measurement_metrics.py verifies
trade_metrics()'s formula against hand-built dicts in which realized_pnl
is ALREADY net of every fee. That premise was never checked against what
PositionManager actually emits, and it was false: pnl.leg_realized_pnl
subtracts only the CLOSING leg's fee while fees_paid accumulates the
entry fill's fee too. gross = realized_pnl + fees_paid + funding_paid
therefore added the entry fee back without it ever having been
subtracted.

Measured on the corrected lifecycle, 2026-08-10: reported gross
-0.2530262760 against a price PnL of -0.32766 -- overstated by exactly
the entry fee, 0.0746337240. Fees are positive, so the bias only ever
flatters: gross_profit_factor and the VDA tax gate were both optimistic,
which is the direction that lets a losing strategy be called deployable.

EVERY TEST BELOW DRIVES THE REAL COMPONENTS -- a real EventStore, a real
PositionManager, the real closed_trades() and the real trade_metrics().
Nothing is stubbed, because a stub is exactly what hid the defect.

THE ONE CONVENTION, asserted throughout:

    gross = price PnL, before all costs
    net   = gross - fees_paid - funding_paid
"""

import unittest
from decimal import Decimal

from event_store import EventStore
from exchange_adapter import OrderSide, Symbol
from position_manager import PositionLifecycleTrigger, PositionManager

from alpha_engine.feasibility import MIN_GROSS_PROFIT_FACTOR, survives_vda_tax
from measurement import metrics as M
from measurement.scoreboard import closed_trades

from tests.test_position_manager import _create, _fill, _tmp_path


class _Closed:
    """One opened-and-closed position, built through the real manager.

    Prices are chosen so the price PnL is a round number the test states
    itself, rather than a figure copied back out of the code under test.
    """

    ENTRY = Decimal("50000")

    def __init__(self, exit_px, qty="1", entry_fee="0", exit_fee="0", funding=None):
        self.store = EventStore(_tmp_path())
        self.pm = PositionManager(self.store)
        pos = _create(self.pm, qty=qty)
        self.pid = pos.position_id
        self.pm.record_entry_fill(
            self.pid, _fill("f1", "c1", "e1", str(self.ENTRY), qty, entry_fee))
        if funding is not None:
            self.pm.record_funding_payment(
                self.pid, Decimal(funding), "2026-01-01T00:30:00+00:00", "fund1")
        self.pm.record_exit(
            self.pid, _fill("x1", "c1", "e1", str(exit_px), qty, exit_fee),
            PositionLifecycleTrigger.CLOSE)
        self.price_pnl = (Decimal(exit_px) - self.ENTRY) * Decimal(qty)

    def stats(self):
        return M.trade_metrics(closed_trades(self.store, self.pm))

    def close(self):
        self.store.close()


class TestGrossIsPricePnlBeforeAllCosts(unittest.TestCase):

    def test_one_losing_trade_separates_price_from_costs(self):
        """TEST 1. -5000 of price movement, 190 of cost, stated by hand."""
        c = _Closed(exit_px="45000", qty="10", entry_fee="100", exit_fee="90")
        try:
            s = c.stats()
            self.assertEqual(c.price_pnl, Decimal("-50000"))
            self.assertEqual(s["total_gross_pnl"], Decimal("-50000"),
                             "gross must be price PnL, with NO fee added back")
            self.assertEqual(s["fees_paid"], Decimal("190"),
                             "fees_paid must be entry + exit")
            self.assertEqual(s["total_net_pnl"], Decimal("-50190"),
                             "net must carry BOTH fees")
            self.assertEqual(s["total_gross_pnl"] - s["fees_paid"] - s["funding_paid"],
                             s["total_net_pnl"], "the one convention must hold")
        finally:
            c.close()

    def test_a_winning_trade_is_not_flattered_by_the_entry_fee(self):
        """TEST 2, the critical one. Under the defect a +100 win with a 20
        entry fee reported gross 120; the signal produced 100."""
        c = _Closed(exit_px="50100", qty="1", entry_fee="20", exit_fee="0")
        try:
            s = c.stats()
            self.assertEqual(c.price_pnl, Decimal("100"))
            self.assertEqual(s["total_gross_pnl"], Decimal("100"))
            self.assertNotEqual(s["total_gross_pnl"], Decimal("120"),
                                "the entry fee must not inflate a winner's gross")
            self.assertEqual(s["total_net_pnl"], Decimal("80"))
        finally:
            c.close()

    def test_an_entry_fee_cannot_disappear_from_net(self):
        """TEST 3. Flat price, entry fee only: the account still lost it."""
        c = _Closed(exit_px="50000", qty="1", entry_fee="100", exit_fee="0")
        try:
            s = c.stats()
            self.assertEqual(s["total_gross_pnl"], Decimal("0"),
                             "no price movement means no gross")
            self.assertEqual(s["total_net_pnl"], Decimal("-100"),
                             "the entry fee must survive into net")
            self.assertEqual(s["fees_paid"], Decimal("100"))
        finally:
            c.close()

    def test_an_exit_fee_is_counted_exactly_once(self):
        """TEST 4. Flat price, exit fee only. Counting it twice would give
        -180; not at all would give 0 net."""
        c = _Closed(exit_px="50000", qty="1", entry_fee="0", exit_fee="90")
        try:
            s = c.stats()
            self.assertEqual(s["total_gross_pnl"], Decimal("0"))
            self.assertEqual(s["total_net_pnl"], Decimal("-90"))
            self.assertEqual(s["fees_paid"], Decimal("90"))
        finally:
            c.close()

    def test_funding_keeps_its_existing_cost_semantics(self):
        """TEST 5. Funding is a cost in net and is added back for gross,
        exactly as fees are -- unchanged in kind by this correction."""
        c = _Closed(exit_px="50000", qty="1", funding="25")
        try:
            s = c.stats()
            self.assertEqual(s["funding_paid"], Decimal("25"))
            self.assertEqual(s["total_gross_pnl"], Decimal("0"))
            self.assertEqual(s["total_net_pnl"], Decimal("-25"))
        finally:
            c.close()

    def test_cost_attribution_is_a_share_of_price_pnl(self):
        c = _Closed(exit_px="50100", qty="1", entry_fee="20", exit_fee="0")
        try:
            attr = M.cost_attribution(c.stats())
            self.assertEqual(attr["cost_total"], Decimal("20"))
            # 20 / 100, not 20 / 120.
            self.assertEqual(attr["cost_ratio_of_gross"], Decimal("20") / Decimal("100"))
        finally:
            c.close()


class TestTheVdaGateIsNoLongerFlattered(unittest.TestCase):
    """PROOF OF DIRECTION: the old formula could produce a false PASS.

    One +100 win carrying a 20 entry fee and one -70 loss. The project's
    own bar is MIN_GROSS_PROFIT_FACTOR; no new threshold is invented.

        defective gross PF = (100 + 20) / 70 = 1.714  -> ABOVE the bar
        corrected gross PF =  100       / 70 = 1.429  -> BELOW the bar
    """

    @staticmethod
    def _defective_gross_pf(records):
        """The formula as it behaved before the fix: realized_pnl straight
        from PositionSnapshot, with fees_paid added back on top."""
        gross = [Decimal(r["raw_realized_pnl"]) + Decimal(r["fees_paid"]) for r in records]
        return M.profit_factor([float(g) for g in gross])

    def test_the_old_formula_passes_the_bar_and_the_new_one_does_not(self):
        win = _Closed(exit_px="50100", qty="1", entry_fee="20", exit_fee="0")
        loss = _Closed(exit_px="49930", qty="1")
        try:
            corrected = M.trade_metrics(
                closed_trades(win.store, win.pm) + closed_trades(loss.store, loss.pm))
            defective = self._defective_gross_pf([
                {"raw_realized_pnl": str(win.pm.get_position(win.pid).realized_pnl),
                 "fees_paid": str(win.pm.get_position(win.pid).fees_paid)},
                {"raw_realized_pnl": str(loss.pm.get_position(loss.pid).realized_pnl),
                 "fees_paid": str(loss.pm.get_position(loss.pid).fees_paid)},
            ])
            bar = Decimal(str(MIN_GROSS_PROFIT_FACTOR))

            self.assertGreater(Decimal(str(defective)), bar,
                               "the defective formula cleared the VDA bar")
            self.assertLessEqual(corrected["gross_profit_factor"], bar,
                                 "the corrected gross PF must not clear it")
            # Through the project's own gate, not a re-implementation of it.
            self.assertTrue(survives_vda_tax(float(defective)))
            self.assertFalse(survives_vda_tax(float(corrected["gross_profit_factor"])))
        finally:
            win.close()
            loss.close()


class TestNormalisationHoldsForEveryClosedShape(unittest.TestCase):
    """ROBUSTNESS: one entry + one exit does not prove the general case.

    The normalisation rests on ONE invariant, and this class exercises it
    against every shape PositionManager can actually reach:

        fees_paid - sum(leg.fee) == sum of the ENTRY fills' fees

    It holds because fees_paid is mutated in exactly two places --
    manager.py:230 (ENTRY_FILL) and :260 (EXIT) -- and :260 sits in the
    same branch as :253, which appends the leg. Fee and leg are written
    together, so no exit fee can exist without a leg carrying it.
    COMPLETE_CLOSE, ARCHIVE and BREAKEVEN are pure transitions with empty
    details and cannot contribute a fee; FUNDING touches funding_paid
    only.
    """

    ENTRY = Decimal("50000")

    def _pm(self):
        store = EventStore(_tmp_path())
        return store, PositionManager(store)

    def _open(self, pm, side=OrderSide.BUY, qty="10"):
        return pm.create_position(
            Symbol("BTC"), side, Decimal(qty), stop_price=Decimal("45000"),
            stop_d=Decimal("0.10"), t1_price=Decimal("57500"),
            t2_price=Decimal("65000"), conviction=None).position_id

    def _assert_contract(self, store, pm, pid):
        """gross == the legs' own price PnL, and the identity closes."""
        legs = pm.get_closed_legs(pid)
        price = sum(((l.exit_px - l.entry_px) * l.quantity for l in legs), Decimal("0"))
        s = M.trade_metrics(closed_trades(store, pm))
        self.assertEqual(s["total_gross_pnl"], price,
                         "gross must equal the legs' price PnL, before costs")
        self.assertEqual(s["total_gross_pnl"],
                         s["total_net_pnl"] + s["fees_paid"] + s["funding_paid"],
                         "gross = net + fees + funding must close exactly")
        return s

    def test_A_long_single_entry_single_exit(self):
        store, pm = self._pm()
        try:
            pid = self._open(pm)
            pm.record_entry_fill(pid, _fill("e1", "c1", "x", "50000", "10", "100"))
            pm.record_exit(pid, _fill("x1", "c1", "x", "45000", "10", "90"),
                           PositionLifecycleTrigger.CLOSE)
            s = self._assert_contract(store, pm, pid)
            self.assertEqual(s["fees_paid"], Decimal("190"))
        finally:
            store.close()

    def test_C_partial_exit_then_final_exit(self):
        """Two closed legs. sum(leg.fee) must cover BOTH."""
        store, pm = self._pm()
        try:
            pid = self._open(pm)
            pm.record_entry_fill(pid, _fill("e1", "c1", "x", "50000", "10", "100"))
            pm.record_exit(pid, _fill("x1", "c1", "x", "57500", "5", "50"),
                           PositionLifecycleTrigger.T1)
            pm.confirm_breakeven(pid)
            pm.record_exit(pid, _fill("x2", "c1", "x", "65000", "5", "40"),
                           PositionLifecycleTrigger.T2)
            pm.complete_close(pid)
            self.assertEqual(len(pm.get_closed_legs(pid)), 2)
            s = self._assert_contract(store, pm, pid)
            self.assertEqual(s["total_gross_pnl"], Decimal("112500"))
            self.assertEqual(s["fees_paid"], Decimal("190"))
        finally:
            store.close()

    def test_D_multiple_entry_fills(self):
        """Entry fees split across fills must still be fully recovered."""
        store, pm = self._pm()
        try:
            pid = self._open(pm)
            pm.record_entry_fill(pid, _fill("e1", "c1", "x", "50000", "5", "60"))
            pm.record_entry_fill(pid, _fill("e2", "c1", "x", "50000", "5", "40"))
            pm.record_exit(pid, _fill("x1", "c1", "x", "45000", "10", "90"),
                           PositionLifecycleTrigger.CLOSE)
            s = self._assert_contract(store, pm, pid)
            self.assertEqual(s["total_net_pnl"], Decimal("-50190"),
                             "both entry fills' fees must appear in net")
        finally:
            store.close()

    def test_E_multiple_entries_and_multiple_exits(self):
        store, pm = self._pm()
        try:
            pid = self._open(pm)
            pm.record_entry_fill(pid, _fill("e1", "c1", "x", "50000", "5", "60"))
            pm.record_entry_fill(pid, _fill("e2", "c1", "x", "50000", "5", "40"))
            pm.record_exit(pid, _fill("x1", "c1", "x", "57500", "5", "50"),
                           PositionLifecycleTrigger.T1)
            pm.confirm_breakeven(pid)
            pm.record_exit(pid, _fill("x2", "c1", "x", "45000", "5", "40"),
                           PositionLifecycleTrigger.STOP)
            pm.complete_close(pid)
            s = self._assert_contract(store, pm, pid)
            self.assertEqual(s["total_gross_pnl"], Decimal("12500"))
            self.assertEqual(s["fees_paid"], Decimal("190"))
        finally:
            store.close()

    def test_multi_position_fees_never_leak_between_positions(self):
        """ISOLATION: fees_paid and _closed_legs are both keyed by
        position_id (manager.py:99, :230, :253), so a second position's
        costs must not reach the first's trade record."""
        store, pm = self._pm()
        try:
            a = self._open(pm)
            b = self._open(pm)
            pm.record_entry_fill(a, _fill("a1", "ca", "x", "50000", "10", "100"))
            pm.record_entry_fill(b, _fill("b1", "cb", "x", "50000", "10", "777"))
            pm.record_exit(a, _fill("a2", "ca", "x", "45000", "10", "90"),
                           PositionLifecycleTrigger.CLOSE)
            trades = closed_trades(store, pm)
            self.assertEqual(len(trades), 1, "only position A is closed")
            self.assertEqual(Decimal(trades[0]["fees_paid"]), Decimal("190"),
                             "position B's 777 fee must not appear here")
            self.assertEqual(M.trade_metrics(trades)["total_gross_pnl"],
                             Decimal("-50000"))
        finally:
            store.close()

    def test_short_position_inherits_the_upstream_sign_convention(self):
        """LIMIT, RECORDED DELIBERATELY -- not a claim that this is right.

        pnl.leg_realized_pnl is (exit - entry) * qty - fee with NO
        direction term, and neither position_manager/manager.py nor
        pnl.py references OrderSide.SELL at all. A SHORT is therefore
        measured with the long formula UPSTREAM of measurement, and
        shorts are reachable in production (app/runtime/accounting.py:290
        passes side=fill.side).

        This normalisation is sign-agnostic: it subtracts scalar costs
        and never touches prices, so it neither causes nor corrects that.
        What it DOES still guarantee for a short is asserted here. If
        Module 7 ever becomes direction-aware, this test fails and points
        at exactly the line that changed.
        """
        store, pm = self._pm()
        try:
            pid = self._open(pm, side=OrderSide.SELL)
            pm.record_entry_fill(pid, _fill("e1", "c1", "x", "50000", "10", "100"))
            pm.record_exit(pid, _fill("x1", "c1", "x", "45000", "10", "90"),
                           PositionLifecycleTrigger.CLOSE)
            s = self._assert_contract(store, pm, pid)
            self.assertEqual(s["fees_paid"], Decimal("190"),
                             "cost recovery is unaffected by side")
            self.assertEqual(s["total_gross_pnl"], Decimal("-50000"),
                             "upstream long-only convention, recorded as the "
                             "known limit -- a true short covered 5000 lower "
                             "made money")
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
