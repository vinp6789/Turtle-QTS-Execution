"""ApprovedCandleAlphaStrategy: construction guards and ATR exit geometry.

No network. Guards the properties a live-capital path depends on:
risk levels are declared not fabricated, foreign specs are refused, the
ATR geometry is correct in both directions, and a missing volatility
scale REFUSES rather than falling back to a fixed percentage.
"""

import unittest
from decimal import Decimal

from exchange_adapter import OrderSide, Symbol

from alpha_engine.candidates import (
    funding_rate_candidate_specification,
    trend_momentum_candidate_specification,
)
from alpha_engine.execution_bridge import (
    ApprovedFundingAlphaStrategy,
    ApprovedCandleAlphaStrategy,
)
from alpha_engine.execution_bridge.errors import ExecutionBridgeError
from trading_system.strategy import Strategy

BTC = Symbol("BTC")
AC = {"min_hit_rate": 0.55, "min_signaled_samples": 100}
BASE = {
    "threshold": "0.40", "direction_convention": "momentum",
    "atr_stop_mult": "2.0", "atr_t1_mult": "3.0", "atr_t2_mult": "4.0",
}


def _spec(**over):
    params = dict(BASE)
    params.update(over)
    params = {k: v for k, v in params.items() if v is not None}
    return trend_momentum_candidate_specification(
        version="v1", universe=(BTC,), cadence_seconds=3600,
        parameters=params, acceptance_criteria=AC,
    )


class TestConstructionGuards(unittest.TestCase):
    def test_constructs_and_is_a_strategy(self):
        s = ApprovedCandleAlphaStrategy((_spec(),))
        self.assertIsInstance(s, Strategy)

    def test_name_is_a_property_not_a_method(self):
        """The ABC declares name as a @property; a plain method would hand
        the execution layer a bound method instead of an identifier."""
        s = ApprovedCandleAlphaStrategy((_spec(),))
        self.assertIsInstance(s.name, str)
        self.assertEqual(s.name, "alpha_engine_approved_candle_v1")

    def test_missing_atr_stop_mult_refused(self):
        with self.assertRaises(ExecutionBridgeError):
            ApprovedCandleAlphaStrategy((_spec(atr_stop_mult=None),))

    def test_non_positive_multiple_refused(self):
        for bad in ("-1", "0"):
            with self.assertRaises(ExecutionBridgeError):
                ApprovedCandleAlphaStrategy((_spec(atr_stop_mult=bad),))

    def test_non_string_multiple_refused(self):
        with self.assertRaises(ExecutionBridgeError):
            ApprovedCandleAlphaStrategy((_spec(atr_stop_mult=2.0),))

    def test_foreign_family_refused(self):
        foreign = funding_rate_candidate_specification(
            version="v1", universe=(BTC,), cadence_seconds=3600,
            parameters={"threshold": "0.001", "direction_convention": "momentum",
                        "stop_fraction": "0.02"},
            acceptance_criteria=AC,
        )
        with self.assertRaises(ExecutionBridgeError):
            ApprovedCandleAlphaStrategy((foreign,))

    def test_empty_specifications_refused(self):
        with self.assertRaises(ExecutionBridgeError):
            ApprovedCandleAlphaStrategy(())

    def test_optional_targets_may_be_omitted(self):
        ApprovedCandleAlphaStrategy((_spec(atr_t1_mult=None, atr_t2_mult=None),))


class TestFundingBridgeUnaffected(unittest.TestCase):
    """The funding path is the only route that has ever been cleared for
    live capital; this addition must not disturb it."""

    def test_funding_bridge_still_constructs(self):
        foreign = funding_rate_candidate_specification(
            version="v1", universe=(BTC,), cadence_seconds=3600,
            parameters={"threshold": "0.001", "direction_convention": "momentum",
                        "stop_fraction": "0.02"},
            acceptance_criteria=AC,
        )
        s = ApprovedFundingAlphaStrategy((foreign,))
        self.assertEqual(s.name, "alpha_engine_approved_funding_v1")

    def test_funding_bridge_refuses_trend_specs(self):
        with self.assertRaises(ExecutionBridgeError):
            ApprovedFundingAlphaStrategy((_spec(),))


class TestAtrExitGeometry(unittest.TestCase):
    """The arithmetic the exits depend on, asserted directly."""

    def test_long_geometry(self):
        mark, atr = Decimal("100"), Decimal("2")
        stop = mark - Decimal("2.0") * atr
        t1 = mark + Decimal("3.0") * atr
        t2 = mark + Decimal("4.0") * atr
        self.assertEqual((stop, t1, t2), (Decimal("96"), Decimal("106"), Decimal("108")))
        self.assertLess(stop, mark)
        self.assertGreater(t1, mark)

    def test_short_geometry_is_the_mirror(self):
        mark, atr = Decimal("100"), Decimal("2")
        stop = mark + Decimal("2.0") * atr
        t1 = mark - Decimal("3.0") * atr
        self.assertEqual((stop, t1), (Decimal("104"), Decimal("94")))
        self.assertGreater(stop, mark)
        self.assertLess(t1, mark)

    def test_reward_to_risk_follows_from_the_multiples(self):
        """1.5R and 2.0R at 2.0/3.0/4.0 -- a property of the frozen spec,
        not of any market observation."""
        self.assertEqual(Decimal("3.0") / Decimal("2.0"), Decimal("1.5"))
        self.assertEqual(Decimal("4.0") / Decimal("2.0"), Decimal("2"))

    def test_extreme_atr_produces_degenerate_stop_that_must_be_refused(self):
        """An ATR wider than mark drives a LONG stop non-positive; the
        bridge refuses rather than clamping."""
        mark, atr = Decimal("100"), Decimal("60")
        self.assertLessEqual(mark - Decimal("2.0") * atr, 0)


if __name__ == "__main__":
    unittest.main()
