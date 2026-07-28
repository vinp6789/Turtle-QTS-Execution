"""Verification tests for the rolling OI extremeness transforms
(alpha_engine.features.open_interest_rolling)."""

import unittest
from decimal import Decimal

from alpha_engine.features import percentile_rank_centered, zscore


def _d(seq):
    return [Decimal(str(x)) for x in seq]


class TestPercentileRankCentered(unittest.TestCase):
    def test_upper_tail_positive(self):
        window = _d(range(100))  # 0..99
        r = percentile_rank_centered(window, Decimal("1000"))  # far above all
        self.assertEqual(r, Decimal("0.5"))  # 100% below -> 1.0 - 0.5

    def test_lower_tail_negative(self):
        window = _d(range(100))
        r = percentile_rank_centered(window, Decimal("-1000"))  # below all
        self.assertEqual(r, Decimal("-0.5"))  # 0% below -> 0.0 - 0.5

    def test_median_near_zero(self):
        window = _d(range(101))  # 0..100, median 50
        r = percentile_rank_centered(window, Decimal("50"))
        # 50 below, 1 equal (itself not in window; 50 appears once) -> (50 + 0.5)/101 - 0.5 ~ 0
        self.assertAlmostEqual(float(r), 0.0, places=2)

    def test_99th_percentile_crosses_049_threshold(self):
        # 100-value window; a value above exactly 99 of them -> rank 0.99 -> centered 0.49
        window = _d(range(100))  # 0..99
        r = percentile_rank_centered(window, Decimal("98.5"))  # above 0..98 (99 values)
        self.assertEqual(r, Decimal("0.49"))  # 99 below, 0 equal -> 0.99 - 0.5

    def test_empty_window_returns_none(self):
        self.assertIsNone(percentile_rank_centered([], Decimal("5")))

    def test_ties_use_midrank(self):
        window = _d([10, 10, 10, 10])
        r = percentile_rank_centered(window, Decimal("10"))
        # 0 below, 4 equal -> (0 + 2)/4 - 0.5 = 0.0
        self.assertEqual(r, Decimal("0.0"))

    def test_deterministic(self):
        window = _d([3, 1, 4, 1, 5, 9, 2, 6])
        a = percentile_rank_centered(window, Decimal("4"))
        b = percentile_rank_centered(window, Decimal("4"))
        self.assertEqual(a, b)


class TestZscore(unittest.TestCase):
    def test_above_mean_positive(self):
        window = _d([10, 12, 14, 16, 18])  # mean 14
        z = zscore(window, Decimal("20"))
        self.assertGreater(z, 0)

    def test_below_mean_negative(self):
        window = _d([10, 12, 14, 16, 18])
        z = zscore(window, Decimal("8"))
        self.assertLess(z, 0)

    def test_two_sigma_value(self):
        # window with known mean/std: [0,0,0,0] then... use a simple set.
        window = _d([-2, -1, 0, 1, 2])  # mean 0, pop variance = 2, std = sqrt(2)
        z = zscore(window, Decimal("2") * Decimal("2").sqrt())  # value = 2*std -> z=2
        self.assertAlmostEqual(float(z), 2.0, places=6)

    def test_constant_window_returns_none(self):
        self.assertIsNone(zscore(_d([5, 5, 5]), Decimal("5")))

    def test_single_point_returns_none(self):
        self.assertIsNone(zscore(_d([5]), Decimal("6")))

    def test_deterministic(self):
        window = _d([3, 1, 4, 1, 5, 9, 2, 6])
        self.assertEqual(zscore(window, Decimal("7")), zscore(window, Decimal("7")))


if __name__ == "__main__":
    unittest.main()
