"""Tests for measurement.validity -- does this number mean anything yet?

The framework exists because the first scoreboard reported a Sharpe of
340.39 from ten cycles spanning two minutes: arithmetically correct, pure
noise. Validity is decided from the SHAPE of the data, never from a
metric's value, and these tests assert that separation directly.
"""

import unittest
from decimal import Decimal

from measurement.validity import (
    MIN_DAYS_FOR_CAGR, MIN_DAYS_FOR_SHARPE, MIN_RETURNS_FOR_SHARPE,
    REQUIREMENTS, Metric, MetricStatus, classify,
)


def _m(**kw):
    base = {"observations": 100, "trade_count": 10, "win_count": 5, "loss_count": 5}
    base.update(kw)
    return base


def _c(metrics, returns=99, days="60"):
    return classify(metrics, return_count=returns,
                    elapsed_days=Decimal(days) if days is not None else None)


class TestSharpe(unittest.TestCase):
    def test_the_defect_that_created_this_framework(self):
        """10 cycles over 2 minutes gave Sharpe 340.39."""
        r = _c(_m(observations=10, sharpe=Decimal("340.39")), returns=9, days="0.0015")["sharpe"]
        self.assertEqual(r.status, MetricStatus.INSUFFICIENT_DATA)
        self.assertIn("insufficient observations", r.reason)

    def test_enough_returns_but_too_little_elapsed_time(self):
        r = _c(_m(sharpe=Decimal("2")), returns=50, days="1")["sharpe"]
        self.assertEqual(r.status, MetricStatus.INSUFFICIENT_DATA)
        self.assertIn("insufficient elapsed time", r.reason)

    def test_valid_with_both(self):
        self.assertEqual(_c(_m(sharpe=Decimal("2")), returns=50, days="60")["sharpe"].status,
                         MetricStatus.VALID)

    def test_value_is_passed_through_untouched(self):
        """Validity never rounds, adjusts or suppresses a value."""
        r = _c(_m(sharpe=Decimal("340.39")), returns=5, days="0.001")["sharpe"]
        self.assertEqual(r.value, Decimal("340.39"))


class TestCagr(unittest.TestCase):
    def test_short_window_is_insufficient_not_invalid(self):
        r = _c(_m(cagr=None), days="2")["cagr"]
        self.assertEqual(r.status, MetricStatus.INSUFFICIENT_DATA)
        self.assertIn(f"< {MIN_DAYS_FOR_CAGR}d", r.reason)

    def test_valid_past_the_threshold(self):
        self.assertEqual(_c(_m(cagr=Decimal("0.2")), days="31")["cagr"].status,
                         MetricStatus.VALID)

    def test_unknown_elapsed_time_is_insufficient(self):
        self.assertEqual(_c(_m(cagr=None), days=None)["cagr"].status,
                         MetricStatus.INSUFFICIENT_DATA)


class TestNotApplicableVsInsufficient(unittest.TestCase):
    """The distinction that matters: would more data of the same kind help?"""

    def test_profit_factor_without_a_loss_is_not_applicable(self):
        r = _c(_m(loss_count=0, profit_factor=None))["profit_factor"]
        self.assertEqual(r.status, MetricStatus.NOT_APPLICABLE)
        self.assertIn("no losing trade", r.reason)

    def test_average_win_without_a_win_is_not_applicable(self):
        self.assertEqual(_c(_m(win_count=0, average_win=None))["average_win"].status,
                         MetricStatus.NOT_APPLICABLE)

    def test_payoff_ratio_needs_both_legs(self):
        self.assertEqual(_c(_m(win_count=0, payoff_ratio=None))["payoff_ratio"].status,
                         MetricStatus.NOT_APPLICABLE)
        self.assertEqual(_c(_m(loss_count=0, payoff_ratio=None))["payoff_ratio"].status,
                         MetricStatus.NOT_APPLICABLE)

    def test_win_rate_without_trades_is_insufficient_not_not_applicable(self):
        """More trades WOULD produce a win rate, so it is under-sampled,
        not undefined."""
        self.assertEqual(_c(_m(trade_count=0, win_rate=None))["win_rate"].status,
                         MetricStatus.INSUFFICIENT_DATA)

    def test_expectancy_without_trades_is_insufficient(self):
        self.assertEqual(_c(_m(trade_count=0, expectancy=None))["expectancy"].status,
                         MetricStatus.INSUFFICIENT_DATA)


class TestAlwaysValidMetrics(unittest.TestCase):
    def test_counts_and_totals_are_always_valid(self):
        c = _c(_m(trade_count=0, fees_paid=Decimal("0"), funding_paid=Decimal("0")))
        for k in ("trade_count", "fees_paid", "funding_paid"):
            self.assertEqual(c[k].status, MetricStatus.VALID, k)

    def test_a_metric_absent_from_the_table_defaults_to_valid(self):
        self.assertEqual(_c(_m(some_new_metric=42))["some_new_metric"].status,
                         MetricStatus.VALID)


class TestReturnBasedMetrics(unittest.TestCase):
    def test_one_observation_cannot_produce_a_return(self):
        r = _c(_m(observations=1, total_return=None), returns=0)["total_return"]
        self.assertEqual(r.status, MetricStatus.INSUFFICIENT_DATA)
        self.assertIn("insufficient observations", r.reason)

    def test_drawdown_needs_a_return_series(self):
        self.assertEqual(_c(_m(observations=1, max_drawdown=None), returns=0)["max_drawdown"].status,
                         MetricStatus.INSUFFICIENT_DATA)


class TestDesignDiscipline(unittest.TestCase):
    def test_requirements_are_declared_in_one_table(self):
        for name in ("sharpe", "cagr", "profit_factor", "gross_profit_factor",
                     "win_rate", "payoff_ratio", "expectancy", "max_drawdown",
                     "average_win", "average_loss", "total_return"):
            self.assertIn(name, REQUIREMENTS, f"{name} has no declared requirement")

    def test_validity_never_inspects_a_metric_value(self):
        """A wildly different value must not change the status."""
        a = _c(_m(sharpe=Decimal("0.1")), returns=5, days="0.5")["sharpe"].status
        b = _c(_m(sharpe=Decimal("9999")), returns=5, days="0.5")["sharpe"].status
        self.assertEqual(a, b)

    def test_every_non_valid_metric_carries_a_reason(self):
        c = _c(_m(observations=1, trade_count=0, win_count=0, loss_count=0,
                  sharpe=None, cagr=None, profit_factor=None, win_rate=None), returns=0)
        for name, m in c.items():
            if m.status is not MetricStatus.VALID:
                self.assertTrue(m.reason.strip(), f"{name} has no reason")

    def test_as_dict_shape_is_value_status_reason(self):
        d = Metric(Decimal("1.5"), MetricStatus.VALID).as_dict()
        self.assertEqual(set(d), {"value", "status", "reason"})
        self.assertEqual(d["value"], "1.5")       # Decimal -> string
