import os
import tempfile
import threading
import unittest
from decimal import Decimal
from pathlib import Path

from event_store import EventStore
from portfolio_manager import (
    InsufficientFundsError,
    InsufficientMarginError,
    PortfolioManager,
)


def _tmp_path() -> Path:
    fd, name = tempfile.mkstemp(suffix=".log")
    os.close(fd)
    os.unlink(name)
    return Path(name)


def _assert_balanced(test, snap):
    test.assertEqual(snap.assets, snap.liabilities + snap.equity)
    test.assertEqual(snap.liabilities, Decimal("0"))


class HappyPath(unittest.TestCase):
    def test_deposit_and_withdraw(self):
        store = EventStore(_tmp_path())
        try:
            pm = PortfolioManager(store)
            s1 = pm.deposit(Decimal("10000"), "dep-1")
            self.assertEqual(s1.available_cash, Decimal("10000"))
            self.assertEqual(s1.equity, Decimal("10000"))
            _assert_balanced(self, s1)

            s2 = pm.withdraw(Decimal("3000"), "wd-1")
            self.assertEqual(s2.available_cash, Decimal("7000"))
            self.assertEqual(s2.equity, Decimal("7000"))
            _assert_balanced(self, s2)
        finally:
            store.close()

    def test_full_margin_lifecycle(self):
        store = EventStore(_tmp_path())
        try:
            pm = PortfolioManager(store)
            pm.deposit(Decimal("10000"), "dep-1")
            s = pm.reserve_margin("pos-1", Decimal("1000"), "res-1")
            self.assertEqual(s.available_cash, Decimal("9000"))
            self.assertEqual(s.reserved_margin, Decimal("1000"))
            _assert_balanced(self, s)

            s = pm.allocate_margin("pos-1", Decimal("1000"), "alloc-1")
            self.assertEqual(s.reserved_margin, Decimal("0"))
            self.assertEqual(s.used_margin, Decimal("1000"))
            self.assertIn("pos-1", s.open_position_ids)
            _assert_balanced(self, s)

            s = pm.release_margin("pos-1", "rel-1")
            self.assertEqual(s.used_margin, Decimal("0"))
            self.assertEqual(s.available_cash, Decimal("10000"))
            self.assertNotIn("pos-1", s.open_position_ids)
            _assert_balanced(self, s)
        finally:
            store.close()

    def test_realized_pnl_gain_and_loss(self):
        store = EventStore(_tmp_path())
        try:
            pm = PortfolioManager(store)
            pm.deposit(Decimal("10000"), "dep-1")
            s = pm.apply_realized_pnl("pos-1", "leg-1", Decimal("500"), "r1")
            self.assertEqual(s.realized_pnl_cumulative, Decimal("500"))
            self.assertEqual(s.available_cash, Decimal("10500"))
            _assert_balanced(self, s)

            s = pm.apply_realized_pnl("pos-1", "leg-2", Decimal("-200"), "r2")
            self.assertEqual(s.realized_pnl_cumulative, Decimal("300"))
            self.assertEqual(s.available_cash, Decimal("10300"))
            _assert_balanced(self, s)
        finally:
            store.close()

    def test_funding_positive_and_negative(self):
        store = EventStore(_tmp_path())
        try:
            pm = PortfolioManager(store)
            pm.deposit(Decimal("10000"), "dep-1")
            s = pm.apply_funding("pos-1", "f1", Decimal("-12.5"), "r1")
            self.assertEqual(s.funding_cumulative, Decimal("-12.5"))
            _assert_balanced(self, s)
            s = pm.apply_funding("pos-1", "f2", Decimal("8.0"), "r2")
            self.assertEqual(s.funding_cumulative, Decimal("-4.5"))
            _assert_balanced(self, s)
        finally:
            store.close()

    def test_fee(self):
        store = EventStore(_tmp_path())
        try:
            pm = PortfolioManager(store)
            pm.deposit(Decimal("10000"), "dep-1")
            s = pm.apply_fee("order-1", "fee-1", Decimal("15"), "r1")
            self.assertEqual(s.fees_cumulative, Decimal("15"))
            self.assertEqual(s.available_cash, Decimal("9985"))
            _assert_balanced(self, s)
        finally:
            store.close()

    def test_update_marks(self):
        store = EventStore(_tmp_path())
        try:
            pm = PortfolioManager(store)
            pm.deposit(Decimal("10000"), "dep-1")
            s = pm.update_marks(Decimal("250"), Decimal("50000"), Decimal("0.02"), "marks-1")
            self.assertEqual(s.unrealized_pnl, Decimal("250"))
            self.assertEqual(s.equity, Decimal("10250"))
            self.assertEqual(s.exposure, Decimal("50000"))
            self.assertEqual(s.heat, Decimal("0.02"))
            _assert_balanced(self, s)
            self.assertEqual(s.leverage, Decimal("50000") / Decimal("10250"))
        finally:
            store.close()


class AccountingConservation(unittest.TestCase):
    def test_full_trade_lifecycle_conserves_capital(self):
        store = EventStore(_tmp_path())
        try:
            pm = PortfolioManager(store)
            pm.deposit(Decimal("100000"), "dep-1")
            pm.reserve_margin("pos-1", Decimal("5000"), "res-1")
            pm.allocate_margin("pos-1", Decimal("5000"), "alloc-1")
            pm.update_marks(Decimal("300"), Decimal("50000"), Decimal("0.05"), "marks-1")
            pm.apply_funding("pos-1", "f1", Decimal("-2"), "fund-1")
            s = pm.apply_realized_pnl("pos-1", "leg-1", Decimal("1200"), "pnl-1")
            s = pm.apply_fee("order-1", "fee-1", Decimal("10"), "fee-r1")
            s = pm.release_margin("pos-1", "rel-1")

            expected_equity = Decimal("100000") + Decimal("1200") - Decimal("2") - Decimal("10") + Decimal("300")
            self.assertEqual(s.equity, expected_equity)
            _assert_balanced(self, s)
            self.assertEqual(s.available_cash, Decimal("100000") + Decimal("1200") - Decimal("2") - Decimal("10"))
        finally:
            store.close()

    def test_invariant_holds_after_every_single_operation_in_a_long_sequence(self):
        store = EventStore(_tmp_path())
        try:
            pm = PortfolioManager(store)
            ops = [
                lambda: pm.deposit(Decimal("50000"), "d1"),
                lambda: pm.reserve_margin("p1", Decimal("2000"), "r1"),
                lambda: pm.allocate_margin("p1", Decimal("2000"), "a1"),
                lambda: pm.update_marks(Decimal("100"), Decimal("20000"), Decimal("0.01"), "m1"),
                lambda: pm.apply_fee("o1", "fee1", Decimal("5"), "fr1"),
                lambda: pm.apply_funding("p1", "fu1", Decimal("3"), "ffr1"),
                lambda: pm.apply_realized_pnl("p1", "leg1", Decimal("-50"), "pr1"),
                lambda: pm.reserve_margin("p2", Decimal("1000"), "r2"),
                lambda: pm.allocate_margin("p2", Decimal("1000"), "a2"),
                lambda: pm.release_margin("p1", "rel1"),
                lambda: pm.withdraw(Decimal("1000"), "w1"),
            ]
            for op in ops:
                snap = op()
                _assert_balanced(self, snap)
        finally:
            store.close()


class ExactlyOnce(unittest.TestCase):
    def test_fee_applied_exactly_once(self):
        store = EventStore(_tmp_path())
        try:
            pm = PortfolioManager(store)
            pm.deposit(Decimal("10000"), "d1")
            pm.apply_fee("o1", "fee-1", Decimal("10"), "r1")
            s2 = pm.apply_fee("o1", "fee-1", Decimal("10"), "r1")
            self.assertEqual(s2.fees_cumulative, Decimal("10"))
        finally:
            store.close()

    def test_funding_applied_exactly_once(self):
        store = EventStore(_tmp_path())
        try:
            pm = PortfolioManager(store)
            pm.deposit(Decimal("10000"), "d1")
            pm.apply_funding("p1", "f1", Decimal("-5"), "r1")
            s2 = pm.apply_funding("p1", "f1", Decimal("-5"), "r1")
            self.assertEqual(s2.funding_cumulative, Decimal("-5"))
        finally:
            store.close()

    def test_margin_released_exactly_once_even_with_different_request_ids(self):
        store = EventStore(_tmp_path())
        try:
            pm = PortfolioManager(store)
            pm.deposit(Decimal("10000"), "d1")
            pm.reserve_margin("p1", Decimal("1000"), "r1")
            pm.allocate_margin("p1", Decimal("1000"), "a1")
            s1 = pm.release_margin("p1", "rel-attempt-1")
            s2 = pm.release_margin("p1", "rel-attempt-2")
            self.assertEqual(s1.available_cash, s2.available_cash)
            self.assertEqual(s2.available_cash, Decimal("10000"))
        finally:
            store.close()

    def test_realized_pnl_applied_exactly_once(self):
        store = EventStore(_tmp_path())
        try:
            pm = PortfolioManager(store)
            pm.deposit(Decimal("10000"), "d1")
            pm.apply_realized_pnl("p1", "leg-1", Decimal("500"), "r1")
            s2 = pm.apply_realized_pnl("p1", "leg-1", Decimal("500"), "r1")
            self.assertEqual(s2.realized_pnl_cumulative, Decimal("500"))
        finally:
            store.close()


class Validation(unittest.TestCase):
    def test_withdraw_more_than_available_rejected(self):
        store = EventStore(_tmp_path())
        try:
            pm = PortfolioManager(store)
            pm.deposit(Decimal("1000"), "d1")
            with self.assertRaises(InsufficientFundsError):
                pm.withdraw(Decimal("2000"), "w1")
        finally:
            store.close()

    def test_reserve_more_than_available_rejected(self):
        store = EventStore(_tmp_path())
        try:
            pm = PortfolioManager(store)
            pm.deposit(Decimal("1000"), "d1")
            with self.assertRaises(InsufficientFundsError):
                pm.reserve_margin("p1", Decimal("2000"), "r1")
        finally:
            store.close()

    def test_allocate_more_than_reserved_rejected(self):
        store = EventStore(_tmp_path())
        try:
            pm = PortfolioManager(store)
            pm.deposit(Decimal("10000"), "d1")
            pm.reserve_margin("p1", Decimal("500"), "r1")
            with self.assertRaises(InsufficientMarginError):
                pm.allocate_margin("p1", Decimal("600"), "a1")
        finally:
            store.close()

    def test_negative_deposit_rejected(self):
        store = EventStore(_tmp_path())
        try:
            pm = PortfolioManager(store)
            with self.assertRaises(ValueError):
                pm.deposit(Decimal("-100"), "d1")
        finally:
            store.close()


class CrashRecoveryAndReplay(unittest.TestCase):
    def test_full_reconstruction_after_restart(self):
        path = _tmp_path()
        store = EventStore(path)
        pm = PortfolioManager(store)
        pm.deposit(Decimal("10000"), "d1")
        pm.reserve_margin("p1", Decimal("1000"), "r1")
        pm.allocate_margin("p1", Decimal("1000"), "a1")
        pm.apply_realized_pnl("p1", "leg-1", Decimal("200"), "pnl-1")
        store.close()

        store2 = EventStore(path)
        try:
            pm2 = PortfolioManager(store2)
            snap = pm2.get_snapshot()
            self.assertEqual(snap.available_cash, Decimal("9000") + Decimal("200"))
            self.assertEqual(snap.used_margin, Decimal("1000"))
            self.assertIn("p1", snap.open_position_ids)
            _assert_balanced(self, snap)
        finally:
            store2.close()

    def test_replay_deterministic_and_no_duplicate_accounting(self):
        path = _tmp_path()
        store = EventStore(path)
        pm = PortfolioManager(store)
        pm.deposit(Decimal("5000"), "d1")
        pm.apply_fee("o1", "fee1", Decimal("5"), "r1")
        store.close()

        balances = []
        for _ in range(3):
            s = EventStore(path)
            pm_i = PortfolioManager(s)
            balances.append(pm_i.get_snapshot().available_cash)
            s.close()
        self.assertEqual(set(balances), {Decimal("4995")})


class Concurrency(unittest.TestCase):
    def test_concurrent_deposits_all_conserved(self):
        store = EventStore(_tmp_path())
        try:
            pm = PortfolioManager(store)
            barrier = threading.Barrier(10)

            def worker(i):
                barrier.wait()
                pm.deposit(Decimal("100"), f"dep-{i}")

            threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            snap = pm.get_snapshot()
            self.assertEqual(snap.available_cash, Decimal("1000"))
            _assert_balanced(self, snap)
        finally:
            store.close()

    def test_no_race_between_position_close_and_equity_update(self):
        store = EventStore(_tmp_path())
        try:
            pm = PortfolioManager(store)
            pm.deposit(Decimal("10000"), "d1")
            pm.reserve_margin("p1", Decimal("1000"), "r1")
            pm.allocate_margin("p1", Decimal("1000"), "a1")
            errors = []

            def do_release():
                try:
                    pm.release_margin("p1", "rel-1")
                except Exception as exc:
                    errors.append(exc)

            def do_marks():
                try:
                    pm.update_marks(Decimal("42"), Decimal("1000"), Decimal("0.01"), "marks-race")
                except Exception as exc:
                    errors.append(exc)

            t1 = threading.Thread(target=do_release)
            t2 = threading.Thread(target=do_marks)
            t1.start()
            t2.start()
            t1.join()
            t2.join()

            self.assertEqual(len(errors), 0)
            snap = pm.get_snapshot()
            _assert_balanced(self, snap)
        finally:
            store.close()

    def test_no_race_between_funding_and_realized_pnl(self):
        store = EventStore(_tmp_path())
        try:
            pm = PortfolioManager(store)
            pm.deposit(Decimal("10000"), "d1")
            results = []
            barrier = threading.Barrier(2)

            def do_funding():
                barrier.wait()
                results.append(pm.apply_funding("p1", "f1", Decimal("-3"), "fr1"))

            def do_pnl():
                barrier.wait()
                results.append(pm.apply_realized_pnl("p1", "leg1", Decimal("100"), "pr1"))

            t1 = threading.Thread(target=do_funding)
            t2 = threading.Thread(target=do_pnl)
            t1.start()
            t2.start()
            t1.join()
            t2.join()

            snap = pm.get_snapshot()
            self.assertEqual(snap.funding_cumulative, Decimal("-3"))
            self.assertEqual(snap.realized_pnl_cumulative, Decimal("100"))
            _assert_balanced(self, snap)
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
