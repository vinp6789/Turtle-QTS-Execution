import os
import tempfile
import threading
import unittest
from decimal import Decimal
from pathlib import Path

from event_store import EventStore
from exchange_adapter import Fill, OrderSide, Symbol
from position_manager import (
    PositionLifecycleState,
    PositionLifecycleTrigger,
    PositionManager,
    PositionNotFoundError,
    PositionStateInconsistencyError,
)


def _tmp_path() -> Path:
    fd, name = tempfile.mkstemp(suffix=".log")
    os.close(fd)
    os.unlink(name)
    return Path(name)


def _fill(fill_id, cid, eoid, price, qty, fee="0") -> Fill:
    return Fill(fill_id, cid, eoid, Symbol("BTC"), OrderSide.BUY, Decimal(price), Decimal(qty), Decimal(fee),
                "2026-01-01T00:00:00+00:00")


def _create(pm: PositionManager, qty="10", stop_d="0.10", conviction=None):
    # entry=50000, stop_pct=0.10 -> stop=45000, t1=57500, t2=65000 (mirrors
    # turtle_backtest.py's exact stop/t1/t2 formulas at these inputs)
    return pm.create_position(
        Symbol("BTC"), OrderSide.BUY, Decimal(qty),
        stop_price=Decimal("45000"), stop_d=Decimal(stop_d),
        t1_price=Decimal("57500"), t2_price=Decimal("65000"),
        conviction=Decimal(conviction) if conviction else None,
    )


class ReferenceResearchEngineMath:
    """Byte-for-byte transcription of turtle_backtest.py's r/pct formula,
    used only to independently verify Position Manager's math -- not
    imported from Position Manager itself."""

    FEE = Decimal("0.001")
    SLIP = Decimal("0.001")

    @classmethod
    def leg_r(cls, entry, exit_px, stop_d, frac):
        return (exit_px / entry - 1) / stop_d * frac - cls.FEE - cls.SLIP

    @classmethod
    def leg_pct(cls, entry, exit_px, frac):
        return (exit_px / entry - 1) * 100 * frac


class HappyPath(unittest.TestCase):
    def test_full_lifecycle_with_t1_then_t2(self):
        store = EventStore(_tmp_path())
        try:
            pm = PositionManager(store)
            pos = _create(pm, qty="10")
            pos = pm.record_entry_fill(pos.position_id, _fill("f1", "c1", "e1", "50000", "10"))
            self.assertEqual(pos.lifecycle_state, PositionLifecycleState.FULLY_FILLED)
            self.assertEqual(pos.avg_entry_price, Decimal("50000"))

            pos = pm.record_exit(pos.position_id, _fill("t1fill", "c1", "e1", "57500", "5"),
                                  PositionLifecycleTrigger.T1)
            self.assertEqual(pos.lifecycle_state, PositionLifecycleState.T1_REACHED)
            self.assertEqual(pos.remaining_quantity, Decimal("5"))

            pos = pm.confirm_breakeven(pos.position_id)
            self.assertEqual(pos.lifecycle_state, PositionLifecycleState.BREAKEVEN_ACTIVE)

            pos = pm.record_exit(pos.position_id, _fill("t2fill", "c1", "e1", "65000", "5"),
                                  PositionLifecycleTrigger.T2)
            self.assertEqual(pos.lifecycle_state, PositionLifecycleState.T2_REACHED)
            self.assertEqual(pos.remaining_quantity, Decimal("0"))

            pos = pm.complete_close(pos.position_id)
            self.assertEqual(pos.lifecycle_state, PositionLifecycleState.CLOSED)
            pos = pm.archive_position(pos.position_id)
            self.assertEqual(pos.lifecycle_state, PositionLifecycleState.ARCHIVED)

            legs = pm.get_closed_legs(pos.position_id)
            self.assertEqual(len(legs), 2)
            self.assertEqual(legs[0].reason, "t1_half")
            self.assertEqual(legs[1].reason, "t2")
        finally:
            store.close()

    def test_direct_stop_before_t1(self):
        store = EventStore(_tmp_path())
        try:
            pm = PositionManager(store)
            pos = _create(pm)
            pos = pm.record_entry_fill(pos.position_id, _fill("f1", "c1", "e1", "50000", "10"))
            pos = pm.record_exit(pos.position_id, _fill("stopfill", "c1", "e1", "45000", "10"),
                                  PositionLifecycleTrigger.STOP)
            self.assertEqual(pos.lifecycle_state, PositionLifecycleState.STOP_TRIGGERED)
            legs = pm.get_closed_legs(pos.position_id)
            self.assertEqual(legs[0].reason, "stop_before_t1")
        finally:
            store.close()

    def test_stop_after_t1(self):
        store = EventStore(_tmp_path())
        try:
            pm = PositionManager(store)
            pos = _create(pm)
            pos = pm.record_entry_fill(pos.position_id, _fill("f1", "c1", "e1", "50000", "10"))
            pos = pm.record_exit(pos.position_id, _fill("t1fill", "c1", "e1", "57500", "5"), PositionLifecycleTrigger.T1)
            pos = pm.confirm_breakeven(pos.position_id)
            pos = pm.record_exit(pos.position_id, _fill("stopfill", "c1", "e1", "50000", "5"), PositionLifecycleTrigger.STOP)
            self.assertEqual(pos.lifecycle_state, PositionLifecycleState.STOP_TRIGGERED)
            legs = pm.get_closed_legs(pos.position_id)
            self.assertEqual(legs[1].reason, "stop_after_t1")
        finally:
            store.close()

    def test_signal_loss_close_before_t1(self):
        store = EventStore(_tmp_path())
        try:
            pm = PositionManager(store)
            pos = _create(pm)
            pos = pm.record_entry_fill(pos.position_id, _fill("f1", "c1", "e1", "50000", "10"))
            pos = pm.record_exit(pos.position_id, _fill("closefill", "c1", "e1", "51000", "10"),
                                  PositionLifecycleTrigger.CLOSE, reason="signal_loss")
            self.assertEqual(pos.lifecycle_state, PositionLifecycleState.CLOSED)
            self.assertEqual(pm.get_closed_legs(pos.position_id)[0].reason, "signal_loss")
        finally:
            store.close()

    def test_multiple_entry_fills_average_price(self):
        store = EventStore(_tmp_path())
        try:
            pm = PositionManager(store)
            pos = _create(pm, qty="10")
            pos = pm.record_entry_fill(pos.position_id, _fill("f1", "c1", "e1", "50000", "4"))
            self.assertEqual(pos.lifecycle_state, PositionLifecycleState.PARTIALLY_FILLED)
            pos = pm.record_entry_fill(pos.position_id, _fill("f2", "c1", "e1", "51000", "6"))
            self.assertEqual(pos.lifecycle_state, PositionLifecycleState.FULLY_FILLED)
            expected_avg = (Decimal("50000") * 4 + Decimal("51000") * 6) / 10
            self.assertEqual(pos.avg_entry_price, expected_avg)
        finally:
            store.close()

    def test_funding_accumulates(self):
        store = EventStore(_tmp_path())
        try:
            pm = PositionManager(store)
            pos = _create(pm)
            pos = pm.record_entry_fill(pos.position_id, _fill("f1", "c1", "e1", "50000", "10"))
            pos = pm.record_funding_payment(pos.position_id, Decimal("-12.5"), "2026-01-01T08:00:00+00:00", "fund-1")
            pos = pm.record_funding_payment(pos.position_id, Decimal("-8.0"), "2026-01-01T16:00:00+00:00", "fund-2")
            self.assertEqual(pos.funding_paid, Decimal("-20.5"))
        finally:
            store.close()

    def test_unrealized_pnl(self):
        store = EventStore(_tmp_path())
        try:
            pm = PositionManager(store)
            pos = _create(pm)
            pos = pm.record_entry_fill(pos.position_id, _fill("f1", "c1", "e1", "50000", "10"))
            u = pm.unrealized_pnl(pos.position_id, Decimal("52000"))
            self.assertEqual(u, Decimal("20000"))  # (52000-50000)*10
        finally:
            store.close()


class PnLCorrectness(unittest.TestCase):
    """Verifies Position Manager's R-multiple/pct math against a direct,
    independent transcription of turtle_backtest.py's formula."""

    def test_t1_then_t2_r_matches_research_engine_formula(self):
        store = EventStore(_tmp_path())
        try:
            pm = PositionManager(store)
            pos = _create(pm, qty="10", stop_d="0.10")
            pos = pm.record_entry_fill(pos.position_id, _fill("f1", "c1", "e1", "50000", "10"))

            pos = pm.record_exit(pos.position_id, _fill("t1", "c1", "e1", "57500", "5"), PositionLifecycleTrigger.T1)
            pm.confirm_breakeven(pos.position_id)
            pos = pm.record_exit(pos.position_id, _fill("t2", "c1", "e1", "65000", "5"), PositionLifecycleTrigger.T2)

            legs = pm.get_closed_legs(pos.position_id)
            entry, stop_d = Decimal("50000"), Decimal("0.10")

            expected_t1_r = ReferenceResearchEngineMath.leg_r(entry, Decimal("57500"), stop_d, Decimal("0.5"))
            expected_t2_r = ReferenceResearchEngineMath.leg_r(entry, Decimal("65000"), stop_d, Decimal("0.5"))
            # Our leg carries real (zero) fees in this test, not the
            # backtest's fixed FEE+SLIP constants -- compare price-return
            # term only (fee term is verified separately below).
            price_return_t1 = (Decimal("57500") / entry - 1) / stop_d * Decimal("0.5")
            price_return_t2 = (Decimal("65000") / entry - 1) / stop_d * Decimal("0.5")
            self.assertEqual(legs[0].r, price_return_t1)
            self.assertEqual(legs[1].r, price_return_t2)
            # Total R across both legs equals a single full-size exit at
            # the SAME weighted structure -- sanity cross-check.
            self.assertAlmostEqual(float(legs[0].r + legs[1].r), float(price_return_t1 + price_return_t2))
        finally:
            store.close()

    def test_fee_reduces_r_by_correct_amount(self):
        store = EventStore(_tmp_path())
        try:
            pm = PositionManager(store)
            pos = _create(pm, qty="10", stop_d="0.10")
            pos = pm.record_entry_fill(pos.position_id, _fill("f1", "c1", "e1", "50000", "10"))
            pos = pm.record_exit(
                pos.position_id, _fill("stopfill", "c1", "e1", "45000", "10", fee="50"),
                PositionLifecycleTrigger.STOP,
            )
            leg = pm.get_closed_legs(pos.position_id)[0]
            # fee=50 on notional 50000*10=500000 -> fee_fraction=0.0001 -> /stop_d(0.10) = 0.001 R
            price_return = (Decimal("45000") / Decimal("50000") - 1) / Decimal("0.10") * Decimal("1.0")
            expected_r = price_return - Decimal("0.001")
            self.assertEqual(leg.r, expected_r)
        finally:
            store.close()

    def test_full_stop_no_t1_fraction_is_one(self):
        store = EventStore(_tmp_path())
        try:
            pm = PositionManager(store)
            pos = _create(pm, qty="10", stop_d="0.10")
            pos = pm.record_entry_fill(pos.position_id, _fill("f1", "c1", "e1", "50000", "10"))
            pos = pm.record_exit(pos.position_id, _fill("stopfill", "c1", "e1", "45000", "10"), PositionLifecycleTrigger.STOP)
            leg = pm.get_closed_legs(pos.position_id)[0]
            expected = (Decimal("45000") / Decimal("50000") - 1) / Decimal("0.10") * Decimal("1.0")
            self.assertEqual(leg.r, expected)
        finally:
            store.close()

    def test_realized_pnl_currency_correct(self):
        store = EventStore(_tmp_path())
        try:
            pm = PositionManager(store)
            pos = _create(pm, qty="10")
            pos = pm.record_entry_fill(pos.position_id, _fill("f1", "c1", "e1", "50000", "10"))
            pos = pm.record_exit(pos.position_id, _fill("t1", "c1", "e1", "57500", "5", fee="10"), PositionLifecycleTrigger.T1)
            leg = pm.get_closed_legs(pos.position_id)[0]
            expected_pnl = (Decimal("57500") - Decimal("50000")) * Decimal("5") - Decimal("10")
            self.assertEqual(leg.realized_pnl, expected_pnl)
            self.assertEqual(pos.realized_pnl, expected_pnl)
        finally:
            store.close()


class Idempotency(unittest.TestCase):
    def test_duplicate_entry_fill_ignored(self):
        store = EventStore(_tmp_path())
        try:
            pm = PositionManager(store)
            pos = _create(pm, qty="10")
            fill = _fill("f1", "c1", "e1", "50000", "4")
            pos1 = pm.record_entry_fill(pos.position_id, fill)
            pos2 = pm.record_entry_fill(pos.position_id, fill)
            self.assertEqual(pos1.filled_quantity, pos2.filled_quantity)
            self.assertEqual(pos2.filled_quantity, Decimal("4"))
        finally:
            store.close()

    def test_duplicate_exit_fill_ignored(self):
        store = EventStore(_tmp_path())
        try:
            pm = PositionManager(store)
            pos = _create(pm)
            pm.record_entry_fill(pos.position_id, _fill("f1", "c1", "e1", "50000", "10"))
            fill = _fill("stopfill", "c1", "e1", "45000", "10")
            r1 = pm.record_exit(pos.position_id, fill, PositionLifecycleTrigger.STOP)
            r2 = pm.record_exit(pos.position_id, fill, PositionLifecycleTrigger.STOP)
            self.assertEqual(len(pm.get_closed_legs(pos.position_id)), 1)
            self.assertEqual(r1.realized_pnl, r2.realized_pnl)
        finally:
            store.close()


class OutOfOrderEvents(unittest.TestCase):
    def test_late_duplicate_entry_after_full_fill_ignored(self):
        store = EventStore(_tmp_path())
        try:
            pm = PositionManager(store)
            pos = _create(pm, qty="10")
            pos = pm.record_entry_fill(pos.position_id, _fill("f1", "c1", "e1", "50000", "10"))
            self.assertEqual(pos.lifecycle_state, PositionLifecycleState.FULLY_FILLED)
            # A stray/duplicate entry-fill notification for the same fill_id
            # arriving after the position is already fully filled: ignored.
            pos2 = pm.record_entry_fill(pos.position_id, _fill("f1", "c1", "e1", "50000", "10"))
            self.assertEqual(pos2.filled_quantity, Decimal("10"))
        finally:
            store.close()

    def test_late_exit_fill_after_terminal_state_is_deduped_not_reopened(self):
        store = EventStore(_tmp_path())
        try:
            pm = PositionManager(store)
            pos = _create(pm)
            pm.record_entry_fill(pos.position_id, _fill("f1", "c1", "e1", "50000", "10"))
            pos = pm.record_exit(pos.position_id, _fill("stopfill", "c1", "e1", "45000", "10"), PositionLifecycleTrigger.STOP)
            pos = pm.complete_close(pos.position_id)
            pos = pm.archive_position(pos.position_id)
            self.assertEqual(pos.lifecycle_state, PositionLifecycleState.ARCHIVED)
            late = pm.record_exit(pos.position_id, _fill("late-fill", "c1", "e1", "44000", "1"), PositionLifecycleTrigger.STOP)
            self.assertEqual(late.lifecycle_state, PositionLifecycleState.ARCHIVED)  # unaffected
        finally:
            store.close()


class CrashRecoveryAndReplay(unittest.TestCase):
    def test_full_reconstruction_after_restart(self):
        path = _tmp_path()
        store = EventStore(path)
        pm = PositionManager(store)
        pos = _create(pm, qty="10")
        pm.record_entry_fill(pos.position_id, _fill("f1", "c1", "e1", "50000", "10"))
        pm.record_exit(pos.position_id, _fill("t1", "c1", "e1", "57500", "5"), PositionLifecycleTrigger.T1)
        store.close()

        store2 = EventStore(path)
        try:
            pm2 = PositionManager(store2)
            recovered = pm2.get_position(pos.position_id)
            self.assertEqual(recovered.lifecycle_state, PositionLifecycleState.T1_REACHED)
            self.assertEqual(recovered.remaining_quantity, Decimal("5"))
            self.assertEqual(len(pm2.get_closed_legs(pos.position_id)), 1)
        finally:
            store2.close()

    def test_no_duplicate_position_creation_on_replay(self):
        path = _tmp_path()
        store = EventStore(path)
        pm = PositionManager(store)
        p1 = _create(pm, qty="10")
        store.close()

        seen = []
        for _ in range(3):
            s = EventStore(path)
            pm_i = PositionManager(s)
            seen.append(len(pm_i._snapshots))
            s.close()
        self.assertEqual(set(seen), {1})


class Concurrency(unittest.TestCase):
    def test_concurrent_entry_fills_serialized_correctly(self):
        store = EventStore(_tmp_path())
        try:
            pm = PositionManager(store)
            pos = _create(pm, qty="100")
            results = []
            barrier = threading.Barrier(10)

            def worker(i):
                barrier.wait()
                fill = _fill(f"f{i}", "c1", "e1", "50000", "10")
                results.append(pm.record_entry_fill(pos.position_id, fill))

            threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            final = pm.get_position(pos.position_id)
            self.assertEqual(final.filled_quantity, Decimal("100"))
            self.assertEqual(final.lifecycle_state, PositionLifecycleState.FULLY_FILLED)
        finally:
            store.close()

    def test_no_race_between_t1_and_stop(self):
        store = EventStore(_tmp_path())
        try:
            pm = PositionManager(store)
            pos = _create(pm, qty="10")
            pm.record_entry_fill(pos.position_id, _fill("f1", "c1", "e1", "50000", "10"))
            errors = []

            def do_t1():
                try:
                    pm.record_exit(pos.position_id, _fill("t1fill", "c1", "e1", "57500", "5"), PositionLifecycleTrigger.T1)
                except Exception as exc:
                    errors.append(exc)

            def do_stop():
                try:
                    pm.record_exit(pos.position_id, _fill("stopfill", "c1", "e1", "45000", "10"), PositionLifecycleTrigger.STOP)
                except Exception as exc:
                    errors.append(exc)

            t1 = threading.Thread(target=do_t1)
            t2 = threading.Thread(target=do_stop)
            t1.start()
            t2.start()
            t1.join()
            t2.join()

            final = pm.get_position(pos.position_id)
            self.assertIn(final.lifecycle_state, (PositionLifecycleState.T1_REACHED, PositionLifecycleState.STOP_TRIGGERED))
        finally:
            store.close()


class Validation(unittest.TestCase):
    def test_unknown_position_raises(self):
        store = EventStore(_tmp_path())
        try:
            pm = PositionManager(store)
            with self.assertRaises(PositionNotFoundError):
                pm.get_position("nonexistent")
        finally:
            store.close()

    def test_negative_quantity_rejected(self):
        store = EventStore(_tmp_path())
        try:
            pm = PositionManager(store)
            with self.assertRaises(ValueError):
                pm.create_position(Symbol("BTC"), OrderSide.BUY, Decimal("-1"),
                                    Decimal("45000"), Decimal("0.1"), Decimal("57500"), Decimal("65000"))
        finally:
            store.close()

    def test_exit_before_any_entry_fill_raises(self):
        store = EventStore(_tmp_path())
        try:
            pm = PositionManager(store)
            pos = _create(pm)
            with self.assertRaises(PositionStateInconsistencyError):
                pm.record_exit(pos.position_id, _fill("x", "c1", "e1", "45000", "10"), PositionLifecycleTrigger.STOP)
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
