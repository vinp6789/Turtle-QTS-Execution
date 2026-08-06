"""Tests for the liquidation_density_rule family (Campaign 08, Backlog 3.7b).

Two jobs:

  1. PROVENANCE. This family exists because reusing
     funding_rate_threshold_rule would stamp feature_name="funding_rate_raw"
     into every Campaign 08 evidence package while actually testing
     liquidation density. Several tests assert the correct identity
     directly -- that is the whole point of the family, not a detail.

  2. SEMANTICS. A liquidation count is non-negative, so the rule is
     ONE-TAILED, unlike the signed funding rule it mirrors. Tests pin
     that difference so a future "consistency" refactor cannot quietly
     reintroduce an unreachable lower tail.

Also asserts the existing families are untouched (additive-only).
"""

import unittest
from decimal import Decimal

from exchange_adapter import Symbol

from alpha_engine.candidates import (
    CANDIDATE_CATALOG,
    CandidateError,
    LiquidationDensityRuleCandidate,
    SignalDirection,
    funding_rate_candidate_specification,
    liquidation_density_candidate_specification,
    list_candidate_types,
)
from alpha_engine.features import FeatureError, FeatureValue, LiquidationDensityFeature

_SYM = Symbol("BTC")
_TS = "2026-01-09T09:00:00+00:00"


def _spec(threshold="77", direction="contrarian", version="v1"):
    return liquidation_density_candidate_specification(
        version=version, universe=(_SYM,), cadence_seconds=3600,
        parameters={"threshold": threshold, "direction_convention": direction},
        acceptance_criteria={"min_hit_rate": 0.55, "min_signaled_samples": 100},
    )


class TestFeatureIdentityAndProvenance(unittest.TestCase):
    """The reason this family exists."""

    def test_feature_name_is_liquidation_density_never_funding_rate(self):
        md = LiquidationDensityFeature.metadata()
        self.assertEqual(md.name, "liquidation_density_hourly")
        self.assertEqual(md.version, "v1")
        self.assertNotIn("funding", md.name)

    def test_specification_carries_the_liquidation_feature_identity(self):
        spec = _spec()
        self.assertEqual(spec.feature_name, "liquidation_density_hourly")
        self.assertEqual(spec.feature_version, "v1")
        self.assertEqual(spec.name, "liquidation_density_rule")

    def test_specification_identity_cannot_be_overridden_by_the_caller(self):
        """Read from metadata(), never passed in -- so it can never desync."""
        with self.assertRaises(TypeError):
            liquidation_density_candidate_specification(
                version="v1", universe=(_SYM,), cadence_seconds=3600,
                parameters={"threshold": "1", "direction_convention": "contrarian"},
                acceptance_criteria={"min_hit_rate": 0.55}, feature_name="funding_rate_raw",
            )

    def test_the_funding_family_would_have_stamped_the_wrong_feature(self):
        """Documents precisely the defect this family avoids."""
        funding = funding_rate_candidate_specification(
            version="v1", universe=(_SYM,), cadence_seconds=3600,
            parameters={"threshold": "77", "direction_convention": "contrarian"},
            acceptance_criteria={"min_hit_rate": 0.55},
        )
        self.assertEqual(funding.feature_name, "funding_rate_raw")
        self.assertNotEqual(funding.feature_name, _spec().feature_name)

    def test_catalog_entry_reports_the_liquidation_feature(self):
        entry = CANDIDATE_CATALOG["liquidation_density_rule"]
        self.assertEqual(entry.feature_name, "liquidation_density_hourly")
        self.assertEqual(entry.candidate_type, "rule_based")
        self.assertIs(entry.evaluate_fn, LiquidationDensityRuleCandidate.evaluate)


class TestFeatureCompute(unittest.TestCase):
    def test_count_becomes_the_feature_value(self):
        fv = LiquidationDensityFeature.compute(_SYM, _TS, 123)
        self.assertTrue(fv.available)
        self.assertEqual(fv.value, Decimal(123))
        self.assertEqual(fv.feature_name, "liquidation_density_hourly")

    def test_zero_is_available_not_missing(self):
        """RD-14: an absent (symbol, hour) inside coverage is a VERIFIED
        zero-event hour, not unknown."""
        fv = LiquidationDensityFeature.compute(_SYM, _TS, 0)
        self.assertTrue(fv.available)
        self.assertEqual(fv.value, Decimal(0))
        self.assertIsNone(fv.reason)

    def test_none_requires_a_reason_and_is_unavailable(self):
        fv = LiquidationDensityFeature.compute(_SYM, _TS, None,
                                               unavailable_reason="outside archive coverage")
        self.assertFalse(fv.available)
        self.assertIsNone(fv.value)
        self.assertIn("coverage", fv.reason)

    def test_none_without_a_reason_raises(self):
        """An unknown hour must never degrade silently into a quiet hour."""
        with self.assertRaises(FeatureError):
            LiquidationDensityFeature.compute(_SYM, _TS, None)

    def test_negative_count_raises(self):
        with self.assertRaises(FeatureError):
            LiquidationDensityFeature.compute(_SYM, _TS, -1)

    def test_bool_is_not_accepted_as_a_count(self):
        with self.assertRaises(FeatureError):
            LiquidationDensityFeature.compute(_SYM, _TS, True)

    def test_wrong_symbol_type_raises(self):
        with self.assertRaises(FeatureError):
            LiquidationDensityFeature.compute("BTC", _TS, 5)

    def test_compute_is_deterministic(self):
        a = LiquidationDensityFeature.compute(_SYM, _TS, 42)
        b = LiquidationDensityFeature.compute(_SYM, _TS, 42)
        self.assertEqual(a, b)


class TestOneTailedSemantics(unittest.TestCase):
    """A count is non-negative: there is no lower extreme."""

    def _sig(self, count, direction="contrarian", threshold="77"):
        fv = LiquidationDensityFeature.compute(_SYM, _TS, count)
        return LiquidationDensityRuleCandidate.evaluate(fv, _spec(threshold, direction))

    def test_at_or_above_threshold_signals(self):
        self.assertEqual(self._sig(77).direction, SignalDirection.SHORT)
        self.assertEqual(self._sig(1000).direction, SignalDirection.SHORT)

    def test_below_threshold_is_flat(self):
        self.assertEqual(self._sig(76).direction, SignalDirection.FLAT)
        self.assertEqual(self._sig(0).direction, SignalDirection.FLAT)

    def test_momentum_inverts_the_direction(self):
        self.assertEqual(self._sig(1000, "momentum").direction, SignalDirection.LONG)
        self.assertEqual(self._sig(0, "momentum").direction, SignalDirection.FLAT)

    def test_zero_threshold_signals_on_every_hour(self):
        """Degenerate but well-defined -- must not crash or invert."""
        self.assertEqual(self._sig(0, threshold="0").direction, SignalDirection.SHORT)

    def test_no_lower_tail_exists(self):
        """The signed funding rule fires on rate < -threshold. For counts
        that branch is unreachable; a low count is FLAT, never a signal."""
        for count in (0, 1, 5, 76):
            with self.subTest(count=count):
                self.assertEqual(self._sig(count).direction, SignalDirection.FLAT)

    def test_signal_carries_feature_value_and_threshold(self):
        s = self._sig(500)
        self.assertEqual(s.feature_value, Decimal(500))
        self.assertEqual(s.threshold, Decimal("77"))


class TestEvaluateGuards(unittest.TestCase):
    def test_unavailable_feature_degrades_never_crashes(self):
        fv = LiquidationDensityFeature.compute(_SYM, _TS, None, unavailable_reason="gap")
        sig = LiquidationDensityRuleCandidate.evaluate(fv, _spec())
        self.assertFalse(sig.available)
        self.assertIn("gap", sig.reason)
        self.assertIsNone(sig.direction)

    def test_refuses_a_specification_from_another_family(self):
        fv = LiquidationDensityFeature.compute(_SYM, _TS, 100)
        other = funding_rate_candidate_specification(
            version="v1", universe=(_SYM,), cadence_seconds=3600,
            parameters={"threshold": "1", "direction_convention": "contrarian"},
            acceptance_criteria={"min_hit_rate": 0.55})
        with self.assertRaises(CandidateError):
            LiquidationDensityRuleCandidate.evaluate(fv, other)

    def test_refuses_a_mismatched_feature(self):
        wrong = FeatureValue(feature_name="funding_rate_raw", feature_version="v1",
                             symbol=_SYM, computed_at_utc=_TS, available=True,
                             value=Decimal(5))
        with self.assertRaises(CandidateError):
            LiquidationDensityRuleCandidate.evaluate(wrong, _spec())

    def test_negative_threshold_raises(self):
        fv = LiquidationDensityFeature.compute(_SYM, _TS, 10)
        with self.assertRaises(CandidateError):
            LiquidationDensityRuleCandidate.evaluate(fv, _spec(threshold="-1"))

    def test_missing_threshold_raises(self):
        fv = LiquidationDensityFeature.compute(_SYM, _TS, 10)
        spec = liquidation_density_candidate_specification(
            version="v1", universe=(_SYM,), cadence_seconds=3600,
            parameters={"direction_convention": "contrarian"}, acceptance_criteria={"min_hit_rate": 0.55})
        with self.assertRaises(CandidateError):
            LiquidationDensityRuleCandidate.evaluate(fv, spec)

    def test_unknown_direction_convention_raises(self):
        fv = LiquidationDensityFeature.compute(_SYM, _TS, 10)
        with self.assertRaises(CandidateError):
            LiquidationDensityRuleCandidate.evaluate(fv, _spec(direction="sideways"))

    def test_wrong_argument_types_raise(self):
        with self.assertRaises(CandidateError):
            LiquidationDensityRuleCandidate.evaluate("nope", _spec())
        fv = LiquidationDensityFeature.compute(_SYM, _TS, 10)
        with self.assertRaises(CandidateError):
            LiquidationDensityRuleCandidate.evaluate(fv, "nope")


class TestAdditiveOnly(unittest.TestCase):
    """The existing families must be untouched."""

    def test_all_four_families_registered(self):
        """Inventory guard. Named "four" when liquidation_density was the
        fourth family; trend_momentum_rule (EMA+MACD+ATR, the first
        candle-derived family) is the fifth. The assertion, not the name,
        is what this test enforces: adding a family must be a deliberate,
        reviewed change that updates this list."""
        self.assertEqual(list_candidate_types(), (
            "funding_rate_threshold_rule",
            "liquidation_density_rule",
            "open_interest_extremeness_rule",
            "open_interest_threshold_rule",
            "trend_momentum_rule",
        ))

    def test_existing_families_keep_their_feature_identities(self):
        self.assertEqual(CANDIDATE_CATALOG["funding_rate_threshold_rule"].feature_name,
                         "funding_rate_raw")
        self.assertEqual(CANDIDATE_CATALOG["open_interest_threshold_rule"].feature_name,
                         "open_interest_raw")
        self.assertEqual(CANDIDATE_CATALOG["open_interest_extremeness_rule"].feature_name,
                         "open_interest_pctrank_centered")

    def test_funding_rule_still_two_tailed(self):
        """The new one-tailed rule must not have leaked into the signed one."""
        from alpha_engine.candidates import FundingRateThresholdRuleCandidate
        from alpha_engine.features import FundingRateFeature
        spec = funding_rate_candidate_specification(
            version="v1", universe=(_SYM,), cadence_seconds=3600,
            parameters={"threshold": "0.001", "direction_convention": "contrarian"},
            acceptance_criteria={"min_hit_rate": 0.55})
        fv = FeatureValue(feature_name=FundingRateFeature.NAME,
                          feature_version=FundingRateFeature.VERSION, symbol=_SYM,
                          computed_at_utc=_TS, available=True, value=Decimal("-0.005"))
        sig = FundingRateThresholdRuleCandidate.evaluate(fv, spec)
        self.assertEqual(sig.direction, SignalDirection.LONG)  # lower tail still live


if __name__ == "__main__":
    unittest.main()
