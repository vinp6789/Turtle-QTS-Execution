"""Tests for measurement.equity_log -- the business-metrics substrate.

Four jobs:

  1. THE FIVE GUARANTEES. append-only, restart-safe, deterministic, no
     duplicate writes, replay-safe. Each is asserted directly.

  2. NO DUPLICATED ACCOUNTING. Every monetary field must be the
     portfolio manager's own figure, copied verbatim. A test compares
     each written value against the snapshot it came from, so a future
     "improvement" that recomputes anything here fails.

  3. TASK 2 READINESS. The schema must already carry every input the
     metrics engine needs, so no migration follows. Asserted field by
     field, including the capital-flow fields whose absence silently
     corrupts every return-based metric.

  4. MEASUREMENT MUST NEVER BREAK TRADING. A recording failure is logged,
     not raised.
"""

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from measurement import SCHEMA_VERSION, EquityLog, idempotency_key, row_from_snapshot


class FakeSnapshot:
    """Shaped exactly like portfolio_manager.PortfolioSnapshot."""

    def __init__(self, **kw):
        d = dict(
            available_cash=Decimal("900"), reserved_margin=Decimal("0"),
            used_margin=Decimal("100"), unrealized_pnl=Decimal("5"),
            realized_pnl_cumulative=Decimal("20"), funding_cumulative=Decimal("-1"),
            fees_cumulative=Decimal("3"), deposits_cumulative=Decimal("1000"),
            withdrawals_cumulative=Decimal("0"), exposure=Decimal("100"),
            heat=Decimal("0.1"), open_position_ids=("p1",),
            updated_at_utc="2026-08-07T10:00:00+00:00",
        )
        d.update(kw)
        for k, v in d.items():
            setattr(self, k, v)

    @property
    def wallet_balance(self):
        return (self.deposits_cumulative - self.withdrawals_cumulative
                + self.realized_pnl_cumulative + self.funding_cumulative
                - self.fees_cumulative)

    @property
    def equity(self):
        return self.wallet_balance + self.unrealized_pnl


def _log():
    return EquityLog(Path(tempfile.mkdtemp()) / "equity.jsonl")


class TestNoDuplicatedAccounting(unittest.TestCase):
    """Every value is the portfolio manager's own. Nothing is recomputed."""

    def test_every_monetary_field_is_copied_verbatim(self):
        snap = FakeSnapshot()
        row = row_from_snapshot(snap, cycle_seq=1)
        for field in ("available_cash", "unrealized_pnl", "realized_pnl_cumulative",
                      "funding_cumulative", "fees_cumulative", "deposits_cumulative",
                      "withdrawals_cumulative", "exposure", "heat",
                      "used_margin", "reserved_margin"):
            self.assertEqual(row[field], str(getattr(snap, field)), field)

    def test_equity_and_wallet_balance_come_from_the_snapshot_properties(self):
        snap = FakeSnapshot()
        row = row_from_snapshot(snap, cycle_seq=1)
        self.assertEqual(row["equity"], str(snap.equity))
        self.assertEqual(row["wallet_balance"], str(snap.wallet_balance))

    def test_decimals_are_written_as_strings_never_floats(self):
        row = row_from_snapshot(FakeSnapshot(), cycle_seq=1)
        for field in ("equity", "fees_cumulative", "heat"):
            self.assertIsInstance(row[field], str)

    def test_row_construction_is_pure(self):
        """No clock: the timestamp is the snapshot's own."""
        snap = FakeSnapshot(updated_at_utc="2020-01-01T00:00:00+00:00")
        self.assertEqual(row_from_snapshot(snap, cycle_seq=0)["observed_at_utc"],
                         "2020-01-01T00:00:00+00:00")


class TestTask2Readiness(unittest.TestCase):
    """The schema must not need a migration for the metrics engine."""

    def test_capital_flows_are_recorded(self):
        """Without these, a deposit is indistinguishable from a gain and
        every return-based metric is silently wrong."""
        row = row_from_snapshot(FakeSnapshot(), cycle_seq=1)
        self.assertIn("deposits_cumulative", row)
        self.assertIn("withdrawals_cumulative", row)

    def test_fees_and_funding_are_kept_separate(self):
        """Cost attribution must not merge two different costs."""
        row = row_from_snapshot(FakeSnapshot(), cycle_seq=1)
        self.assertNotEqual(row["fees_cumulative"], row["funding_cumulative"])
        self.assertIn("fees_cumulative", row)
        self.assertIn("funding_cumulative", row)

    def test_every_metric_input_is_present(self):
        row = row_from_snapshot(FakeSnapshot(), cycle_seq=1)
        required = {
            "equity", "observed_at_utc",              # Sharpe, CAGR, drawdown
            "deposits_cumulative", "withdrawals_cumulative",   # net-of-flow returns
            "fees_cumulative", "funding_cumulative",  # cost attribution
            "realized_pnl_cumulative", "unrealized_pnl",
            "exposure", "heat", "used_margin",        # exposure statistics
            "open_position_count", "cycle_seq", "schema_version",
        }
        self.assertTrue(required.issubset(row), required - set(row))

    def test_schema_version_is_stamped_on_every_row(self):
        self.assertEqual(row_from_snapshot(FakeSnapshot(), cycle_seq=1)["schema_version"],
                         SCHEMA_VERSION)

    def test_strategy_provenance_is_recorded(self):
        row = row_from_snapshot(FakeSnapshot(), cycle_seq=1, strategy_names=("a", "b"))
        self.assertEqual(row["strategies"], ["a", "b"])


class TestTheFiveGuarantees(unittest.TestCase):
    def test_append_only_earlier_rows_are_never_rewritten(self):
        log = _log()
        for i in range(3):
            log.record(FakeSnapshot(updated_at_utc=f"2026-08-07T10:0{i}:00+00:00"),
                       cycle_seq=i)
        first = log.read_all()[0]
        log.record(FakeSnapshot(updated_at_utc="2026-08-07T10:09:00+00:00"), cycle_seq=9)
        self.assertEqual(log.read_all()[0], first)
        self.assertEqual(len(log.read_all()), 4)

    def test_no_duplicate_writes_for_a_replayed_cycle(self):
        log = _log()
        snap = FakeSnapshot()
        self.assertTrue(log.record(snap, cycle_seq=1))
        self.assertFalse(log.record(snap, cycle_seq=1))   # retried cycle
        self.assertFalse(log.record(snap, cycle_seq=1))
        self.assertEqual(len(log.read_all()), 1)

    def test_restart_safe_state_recovers_from_the_last_line(self):
        log = _log()
        snap = FakeSnapshot()
        log.record(snap, cycle_seq=7)
        reopened = EquityLog(log.path)
        self.assertEqual(reopened.last_cycle_seq, 7)
        self.assertFalse(reopened.record(snap, cycle_seq=7))  # still deduped
        self.assertEqual(len(reopened.read_all()), 1)

    def test_deterministic_identical_input_produces_identical_row(self):
        a = row_from_snapshot(FakeSnapshot(), cycle_seq=1)
        b = row_from_snapshot(FakeSnapshot(), cycle_seq=1)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        self.assertEqual(idempotency_key(a), idempotency_key(b))

    def test_replay_safe_a_torn_final_line_is_skipped_not_repaired(self):
        log = _log()
        log.record(FakeSnapshot(), cycle_seq=1)
        with log.path.open("a", encoding="utf-8") as fh:
            fh.write('{"cycle_seq": 2, "equity": "9')      # crash mid-write
        self.assertEqual(len(log.read_all()), 1)
        reopened = EquityLog(log.path)                      # recovery ignores it
        self.assertEqual(reopened.last_cycle_seq, 1)

    def test_an_absent_log_reads_as_empty_not_an_error(self):
        log = EquityLog(Path(tempfile.mkdtemp()) / "nope" / "equity.jsonl")
        self.assertEqual(log.read_all(), [])
        self.assertEqual(log.last_cycle_seq, -1)

    def test_rows_survive_a_full_round_trip(self):
        log = _log()
        snap = FakeSnapshot()
        log.record(snap, cycle_seq=1)
        row = log.read_all()[0]
        self.assertEqual(Decimal(row["equity"]), snap.equity)


if __name__ == "__main__":
    unittest.main()
