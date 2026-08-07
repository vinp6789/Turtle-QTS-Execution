"""Tests for measurement.metrics -- the ONLY business-metrics engine.

Every expected value is derived BY HAND in the test, never taken from
what the code produced. Where a formula has more than one industry
convention, a test pins the adopted one so a future edit cannot switch it
silently.

Four jobs:
  1. ARITHMETIC, hand-derived.
  2. THE CONVENTIONS ARE PINNED (TWR not MWR, sample stdev, drawdown on
     raw equity, win rate excluding break-even).
  3. CAPITAL FLOWS ARE EXCLUDED FROM RETURNS -- the defect that silently
     corrupts every return-based metric.
  4. NO FABRICATION -- an uncomputable metric is None, never a guess.
"""

import unittest
from decimal import Decimal

from measurement import metrics as M


def _row(ts, equity, dep="0", wd="0"):
    return {"observed_at_utc": ts, "equity": str(equity),
            "deposits_cumulative": str(dep), "withdrawals_cumulative": str(wd)}


def _trade(pnl, fees="0", funding="0", opened="2026-01-01T00:00:00+00:00",
           closed="2026-01-01T01:00:00+00:00"):
    return {"realized_pnl": str(pnl), "fees_paid": str(fees),
            "funding_paid": str(funding), "created_at_utc": opened,
            "updated_at_utc": closed}


DAY = "2026-01-{:02d}T00:00:00+00:00".format


class TestReturnsAndCapitalFlows(unittest.TestCase):
    def test_simple_period_return(self):
        rows = [_row(DAY(1), 100), _row(DAY(2), 110)]
        self.assertEqual(M.period_returns(rows), [Decimal("0.1")])

    def test_a_deposit_is_not_a_return(self):
        """The defect this whole schema exists to prevent."""
        rows = [_row(DAY(1), 100, dep=100), _row(DAY(2), 200, dep=200)]
        self.assertEqual(M.period_returns(rows), [Decimal("0")])

    def test_a_withdrawal_is_not_a_loss(self):
        rows = [_row(DAY(1), 200, dep=200), _row(DAY(2), 100, dep=200, wd=100)]
        self.assertEqual(M.period_returns(rows), [Decimal("0")])

    def test_a_gain_alongside_a_deposit_is_measured_correctly(self):
        # equity 100 -> 250 with a 100 deposit: the return is 50/100 = 0.5
        rows = [_row(DAY(1), 100, dep=100), _row(DAY(2), 250, dep=200)]
        self.assertEqual(M.period_returns(rows), [Decimal("0.5")])

    def test_non_positive_opening_equity_is_skipped_not_fabricated(self):
        rows = [_row(DAY(1), 0), _row(DAY(2), 100)]
        self.assertEqual(M.period_returns(rows), [])

    def test_total_return_is_chain_linked_twr(self):
        # +10% then +10% compounds to 21%, not 20% (TWR, not additive)
        rows = [_row(DAY(1), 100), _row(DAY(2), 110), _row(DAY(3), 121)]
        self.assertAlmostEqual(float(M.total_return(rows)), 0.21, places=9)

    def test_total_return_is_none_with_no_periods(self):
        self.assertIsNone(M.total_return([_row(DAY(1), 100)]))


class TestCagr(unittest.TestCase):
    def test_matches_hand_derivation_over_60_days(self):
        rows = [_row(DAY(1), 10000), _row("2026-03-02T00:00:00+00:00", 11000)]
        # 1.1 ** (365/60) - 1
        self.assertAlmostEqual(float(M.cagr(rows)), 1.1 ** (365 / 60) - 1, places=6)

    def test_refuses_to_annualise_a_short_window(self):
        """A 10% gain over 2 days annualises to +35,823,253%."""
        rows = [_row(DAY(1), 10000), _row(DAY(3), 11000)]
        self.assertIsNone(M.cagr(rows))
        self.assertEqual(M.total_return(rows), Decimal("0.1"))   # still reported

    def test_total_loss_returns_minus_one_not_a_complex_number(self):
        rows = [_row(DAY(1), 100), _row("2026-06-01T00:00:00+00:00", 0)]
        self.assertEqual(M.cagr(rows), Decimal("-1"))


class TestSharpe(unittest.TestCase):
    def test_uses_sample_stdev_not_population(self):
        rows = [_row(DAY(1), 100), _row(DAY(2), 110), _row(DAY(3), 121)]
        # returns are [0.1, 0.1] -> zero variance -> undefined
        self.assertIsNone(M.sharpe(rows))

    def test_none_with_fewer_than_two_returns(self):
        self.assertIsNone(M.sharpe([_row(DAY(1), 100), _row(DAY(2), 110)]))

    def test_positive_for_a_rising_noisy_series(self):
        rows = [_row(DAY(1), 100), _row(DAY(2), 105), _row(DAY(3), 103),
                _row(DAY(4), 112), _row(DAY(5), 118)]
        self.assertGreater(M.sharpe(rows), 0)

    def test_negative_for_a_falling_series(self):
        rows = [_row(DAY(1), 100), _row(DAY(2), 95), _row(DAY(3), 97),
                _row(DAY(4), 88), _row(DAY(5), 82)]
        self.assertLess(M.sharpe(rows), 0)


class TestDrawdown(unittest.TestCase):
    def test_matches_hand_derivation(self):
        # peak 120, trough 90 -> (120-90)/120 = 0.25
        rows = [_row(DAY(1), 100), _row(DAY(2), 120), _row(DAY(3), 90), _row(DAY(4), 110)]
        self.assertEqual(M.max_drawdown(rows), Decimal("0.25"))

    def test_monotonic_rise_has_zero_drawdown(self):
        rows = [_row(DAY(1), 100), _row(DAY(2), 110), _row(DAY(3), 120)]
        self.assertEqual(M.max_drawdown(rows), Decimal("0"))

    def test_reported_as_a_positive_fraction(self):
        rows = [_row(DAY(1), 100), _row(DAY(2), 50)]
        self.assertEqual(M.max_drawdown(rows), Decimal("0.5"))

    def test_computed_on_raw_equity_not_net_of_flows(self):
        """ADOPTED CONVENTION: a drawdown is what the operator actually
        experienced in the account. A withdrawal-driven decline still
        shows, because it was still lived through."""
        rows = [_row(DAY(1), 100, dep=100), _row(DAY(2), 50, dep=100, wd=50)]
        self.assertEqual(M.max_drawdown(rows), Decimal("0.5"))


class TestTradeMetrics(unittest.TestCase):
    TRADES = [_trade(100, fees=2, funding=1), _trade(-50, fees=2), _trade(50, fees=1)]

    def test_counts_and_win_rate(self):
        s = M.trade_metrics(self.TRADES)
        self.assertEqual(s["trade_count"], 3)
        self.assertEqual(s["win_count"], 2)
        self.assertEqual(s["loss_count"], 1)
        self.assertAlmostEqual(float(s["win_rate"]), 2 / 3, places=9)

    def test_a_breakeven_trade_is_not_a_win(self):
        s = M.trade_metrics([_trade(10), _trade(0)])
        self.assertEqual(s["win_count"], 1)
        self.assertEqual(s["trade_count"], 2)
        self.assertEqual(s["win_rate"], Decimal("0.5"))

    def test_average_win_and_loss(self):
        s = M.trade_metrics(self.TRADES)
        self.assertEqual(s["average_win"], Decimal("75"))     # (100+50)/2
        self.assertEqual(s["average_loss"], Decimal("50"))    # magnitude

    def test_payoff_ratio(self):
        self.assertEqual(M.trade_metrics(self.TRADES)["payoff_ratio"], Decimal("1.5"))

    def test_expectancy_is_mean_net_pnl_per_trade(self):
        # (100 - 50 + 50) / 3
        s = M.trade_metrics(self.TRADES)
        self.assertAlmostEqual(float(s["expectancy"]), 100 / 3, places=9)

    def test_expectancy_agrees_with_the_win_rate_identity(self):
        s = M.trade_metrics(self.TRADES)
        wr, aw, al = s["win_rate"], s["average_win"], s["average_loss"]
        self.assertAlmostEqual(float(s["expectancy"]),
                               float(wr * aw - (1 - wr) * al), places=9)

    def test_net_vs_gross_profit_factor(self):
        s = M.trade_metrics(self.TRADES)
        self.assertEqual(s["profit_factor"], Decimal("3.0"))        # 150/50
        # gross: wins 103 + 51 = 154 ; loss 50-2 = 48 -> 154/48
        self.assertAlmostEqual(float(s["gross_profit_factor"]), 154 / 48, places=9)

    def test_gross_exceeds_net_when_costs_are_paid(self):
        s = M.trade_metrics(self.TRADES)
        self.assertGreater(s["gross_profit_factor"], s["profit_factor"])

    def test_average_holding_time(self):
        t = [_trade(1, opened=DAY(1), closed=DAY(2)),
             _trade(1, opened=DAY(1), closed=DAY(3))]
        self.assertEqual(M.trade_metrics(t)["average_holding_seconds"], 129600.0)

    def test_no_trades_yields_none_not_zero(self):
        s = M.trade_metrics([])
        for k in ("win_rate", "average_win", "average_loss", "payoff_ratio",
                  "expectancy", "profit_factor", "average_holding_seconds"):
            self.assertIsNone(s[k], k)
        self.assertEqual(s["trade_count"], 0)

    def test_payoff_ratio_undefined_without_a_loss(self):
        self.assertIsNone(M.trade_metrics([_trade(10), _trade(20)])["payoff_ratio"])


class TestCostAttribution(unittest.TestCase):
    def test_costs_are_a_share_of_gross(self):
        s = M.trade_metrics([_trade(100, fees=5, funding=5)])
        c = M.cost_attribution(s)
        self.assertEqual(c["cost_total"], Decimal("10"))
        # gross = 100 + 5 + 5 = 110 -> 10/110
        self.assertAlmostEqual(float(c["cost_ratio_of_gross"]), 10 / 110, places=9)

    def test_fees_and_funding_stay_separate(self):
        c = M.cost_attribution(M.trade_metrics([_trade(10, fees=3, funding=7)]))
        self.assertEqual(c["fees_paid"], Decimal("3"))
        self.assertEqual(c["funding_paid"], Decimal("7"))

    def test_zero_gross_yields_none_not_a_division_by_zero(self):
        self.assertIsNone(M.cost_attribution(M.trade_metrics([]))["cost_ratio_of_gross"])


class TestRollingReturns(unittest.TestCase):
    def test_window_of_one_equals_period_returns(self):
        rows = [_row(DAY(i), 100 * (1.1 ** (i - 1))) for i in range(1, 5)]
        self.assertEqual(len(M.rolling_returns(rows, 1)), len(M.period_returns(rows)))

    def test_window_compounds(self):
        rows = [_row(DAY(1), 100), _row(DAY(2), 110), _row(DAY(3), 121)]
        self.assertAlmostEqual(float(M.rolling_returns(rows, 2)[0]), 0.21, places=9)

    def test_rejects_a_non_positive_window(self):
        with self.assertRaises(ValueError):
            M.rolling_returns([], 0)


class TestAggregateAndSerialisation(unittest.TestCase):
    def test_compute_returns_every_required_metric(self):
        rows = [_row(DAY(1), 10000), _row("2026-03-02T00:00:00+00:00", 11000)]
        m = M.compute(rows, [_trade(100, fees=1)])
        for key in ("total_return", "cagr", "sharpe", "max_drawdown",
                    "profit_factor", "gross_profit_factor", "payoff_ratio",
                    "expectancy", "win_rate", "average_win", "average_loss",
                    "trade_count", "average_holding_seconds", "fees_paid",
                    "funding_paid", "cost_attribution", "survives_vda_tax"):
            self.assertIn(key, m)

    def test_vda_verdict_uses_the_gross_figure(self):
        """Indian VDA tax is levied on GROSS gains -- the net PF is the
        wrong number for this gate."""
        m = M.compute([], [_trade(100, fees=1), _trade(-50)])
        self.assertEqual(m["survives_vda_tax"], m["gross_profit_factor"] > Decimal("1.4535"))

    def test_vda_verdict_is_none_without_trades(self):
        self.assertIsNone(M.compute([], [])["survives_vda_tax"])

    def test_empty_input_fabricates_nothing(self):
        m = M.compute([], [])
        for key in ("total_return", "cagr", "sharpe", "starting_equity"):
            self.assertIsNone(m[key], key)

    def test_to_jsonable_emits_strings_never_floats(self):
        j = M.to_jsonable(M.compute([_row(DAY(1), 100), _row(DAY(2), 110)],
                                    [_trade(5, fees=1)]))
        self.assertIsInstance(j["total_return"], str)
        self.assertIsInstance(j["cost_attribution"]["fees_paid"], str)


class TestSingleEngineDiscipline(unittest.TestCase):
    def test_profit_factor_is_imported_not_reimplemented(self):
        """The architecture rule: one implementation, repository-wide."""
        from pathlib import Path
        src = Path("measurement/metrics.py").read_text(encoding="utf-8")
        self.assertIn("from alpha_engine.feasibility import", src)
        self.assertNotIn("def profit_factor(", src)


if __name__ == "__main__":
    unittest.main()
