"""Verification tests for the Open Interest Candidate (Alpha Engine
Milestone 3.3).

Mirrors test_alpha_engine_funding_rate_rule_candidate.py's structure,
adapted for the single-sided threshold rule (open interest is an
unsigned magnitude -- see open_interest_candidate.py's docstring).
Synthetic test fixture data throughout.
"""

import unittest
from decimal import Decimal

from exchange_adapter import Symbol

from alpha_engine.candidates import (
    CandidateError,
    CandidateSignal,
    CandidateSpecification,
    OpenInterestThresholdRuleCandidate,
    SignalDirection,
    open_interest_candidate_specification,
)
from alpha_engine.features import FeatureValue


def _feature(value, computed_at="2026-01-01T00:00:00+00:00", symbol=None, available=True, reason=None):
    return FeatureValue(
        feature_name="open_interest_raw", feature_version="v1", symbol=symbol or Symbol("BTC"),
        computed_at_utc=computed_at, available=available,
        value=value if available else None, reason=reason,
    )


def _spec(threshold="10000", direction_convention=None, symbol=None, version="v1"):
    parameters = {"threshold": threshold}
    if direction_convention is not None:
        parameters["direction_convention"] = direction_convention
    return open_interest_candidate_specification(
        version=version, universe=(symbol or Symbol("BTC"),), cadence_seconds=60,
        parameters=parameters, acceptance_criteria={"min_hit_rate": 0.5},
    )


class TestFactory(unittest.TestCase):
    def test_name_and_type_are_fixed(self):
        spec = _spec()
        self.assertEqual(spec.name, "open_interest_threshold_rule")
        self.assertEqual(spec.candidate_type, "rule_based")

    def test_feature_reference_matches_open_interest_feature_metadata(self):
        from alpha_engine.features import OpenInterestFeature
        meta = OpenInterestFeature.metadata()
        spec = _spec()
        self.assertEqual(spec.feature_name, meta.name)
        self.assertEqual(spec.feature_version, meta.version)


class TestEvaluateInputValidation(unittest.TestCase):
    def test_rejects_non_feature_value(self):
        with self.assertRaises(CandidateError):
            OpenInterestThresholdRuleCandidate.evaluate("not-a-feature-value", _spec())

    def test_rejects_non_specification(self):
        with self.assertRaises(CandidateError):
            OpenInterestThresholdRuleCandidate.evaluate(_feature(Decimal("100")), "not-a-spec")

    def test_rejects_specification_for_a_different_candidate_name(self):
        spec = _spec()
        wrong = CandidateSpecification(
            name="something_else", version="v1", candidate_type="rule_based",
            universe=spec.universe, feature_name=spec.feature_name, feature_version=spec.feature_version,
            cadence_seconds=60, acceptance_criteria={"min_hit_rate": 0.5}, parameters={"threshold": "10000"},
        )
        with self.assertRaises(CandidateError):
            OpenInterestThresholdRuleCandidate.evaluate(_feature(Decimal("100")), wrong)

    def test_rejects_specification_for_a_different_candidate_type(self):
        spec = _spec()
        wrong = CandidateSpecification(
            name="open_interest_threshold_rule", version="v1", candidate_type="statistical",
            universe=spec.universe, feature_name=spec.feature_name, feature_version=spec.feature_version,
            cadence_seconds=60, acceptance_criteria={"min_hit_rate": 0.5}, parameters={"threshold": "10000"},
        )
        with self.assertRaises(CandidateError):
            OpenInterestThresholdRuleCandidate.evaluate(_feature(Decimal("100")), wrong)

    def test_rejects_mismatched_feature_name(self):
        mismatched = FeatureValue(
            feature_name="some_other_feature", feature_version="v1", symbol=Symbol("BTC"),
            computed_at_utc="2026-01-01T00:00:00+00:00", available=True, value=Decimal("100"),
        )
        with self.assertRaises(CandidateError):
            OpenInterestThresholdRuleCandidate.evaluate(mismatched, _spec())

    def test_rejects_mismatched_feature_version(self):
        mismatched = FeatureValue(
            feature_name="open_interest_raw", feature_version="v2", symbol=Symbol("BTC"),
            computed_at_utc="2026-01-01T00:00:00+00:00", available=True, value=Decimal("100"),
        )
        with self.assertRaises(CandidateError):
            OpenInterestThresholdRuleCandidate.evaluate(mismatched, _spec())

    def test_missing_threshold_parameter_raises(self):
        spec = open_interest_candidate_specification(
            version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
            parameters={}, acceptance_criteria={"min_hit_rate": 0.5},
        )
        with self.assertRaises(CandidateError):
            OpenInterestThresholdRuleCandidate.evaluate(_feature(Decimal("100")), spec)

    def test_non_numeric_threshold_raises(self):
        with self.assertRaises(CandidateError):
            OpenInterestThresholdRuleCandidate.evaluate(_feature(Decimal("100")), _spec(threshold="not-a-number"))

    def test_zero_threshold_raises(self):
        with self.assertRaises(CandidateError):
            OpenInterestThresholdRuleCandidate.evaluate(_feature(Decimal("100")), _spec(threshold="0"))

    def test_negative_threshold_raises(self):
        with self.assertRaises(CandidateError):
            OpenInterestThresholdRuleCandidate.evaluate(_feature(Decimal("100")), _spec(threshold="-10000"))

    def test_invalid_direction_convention_raises(self):
        with self.assertRaises(CandidateError):
            OpenInterestThresholdRuleCandidate.evaluate(
                _feature(Decimal("100")), _spec(direction_convention="sideways")
            )


class TestEvaluateUnavailableFeature(unittest.TestCase):
    def test_unavailable_feature_yields_unavailable_signal(self):
        feature = _feature(None, available=False, reason="ConnectionError: simulated outage")
        result = OpenInterestThresholdRuleCandidate.evaluate(feature, _spec())
        self.assertFalse(result.available)
        self.assertIsNone(result.direction)
        self.assertIn("ConnectionError", result.reason)

    def test_unavailable_never_raises(self):
        feature = _feature(None, available=False, reason="symbol not found")
        try:
            result = OpenInterestThresholdRuleCandidate.evaluate(feature, _spec())
        except Exception as exc:  # noqa: BLE001
            self.fail(f"evaluate() must never raise for an unavailable feature, raised {exc!r}")
        self.assertFalse(result.available)


class TestSingleSidedThreshold(unittest.TestCase):
    """Open interest is never negative -- there is no symmetric
    'below-negative-threshold' branch the way funding rate has one."""

    def test_value_beyond_threshold_contrarian_is_short(self):
        result = OpenInterestThresholdRuleCandidate.evaluate(
            _feature(Decimal("50000")), _spec(threshold="10000")
        )
        self.assertTrue(result.available)
        self.assertEqual(result.direction, SignalDirection.SHORT)

    def test_value_beyond_threshold_momentum_is_long(self):
        result = OpenInterestThresholdRuleCandidate.evaluate(
            _feature(Decimal("50000")), _spec(threshold="10000", direction_convention="momentum")
        )
        self.assertEqual(result.direction, SignalDirection.LONG)

    def test_value_below_threshold_is_flat(self):
        result = OpenInterestThresholdRuleCandidate.evaluate(
            _feature(Decimal("5000")), _spec(threshold="10000")
        )
        self.assertEqual(result.direction, SignalDirection.FLAT)

    def test_value_exactly_at_threshold_is_flat(self):
        result = OpenInterestThresholdRuleCandidate.evaluate(
            _feature(Decimal("10000")), _spec(threshold="10000")
        )
        self.assertEqual(result.direction, SignalDirection.FLAT)  # strict >, boundary is flat

    def test_zero_value_is_flat(self):
        # A literal zero open-interest reading (e.g. an inactive contract) must
        # never be treated as "beyond a negative threshold" -- there is no such
        # branch at all for this rule.
        result = OpenInterestThresholdRuleCandidate.evaluate(
            _feature(Decimal("0")), _spec(threshold="10000")
        )
        self.assertEqual(result.direction, SignalDirection.FLAT)

    def test_contrarian_is_the_default_convention(self):
        result = OpenInterestThresholdRuleCandidate.evaluate(
            _feature(Decimal("50000")), _spec(threshold="10000")  # no direction_convention given
        )
        self.assertEqual(result.direction, SignalDirection.SHORT)


class TestEvaluateSignalContent(unittest.TestCase):
    def test_evaluated_at_utc_matches_feature_computed_at(self):
        feature = _feature(Decimal("100"), computed_at="2026-03-01T12:00:00+00:00")
        result = OpenInterestThresholdRuleCandidate.evaluate(feature, _spec())
        self.assertEqual(result.evaluated_at_utc, "2026-03-01T12:00:00+00:00")

    def test_symbol_carried_through(self):
        feature = _feature(Decimal("100"), symbol=Symbol("ETH"))
        spec = _spec(symbol=Symbol("ETH"))
        result = OpenInterestThresholdRuleCandidate.evaluate(feature, spec)
        self.assertEqual(result.symbol, Symbol("ETH"))

    def test_candidate_name_and_version_match_specification(self):
        feature = _feature(Decimal("100"))
        spec = _spec(version="v9")
        result = OpenInterestThresholdRuleCandidate.evaluate(feature, spec)
        self.assertEqual(result.candidate_name, "open_interest_threshold_rule")
        self.assertEqual(result.candidate_version, "v9")

    def test_feature_value_and_threshold_recorded_exactly(self):
        feature = _feature(Decimal("54321.987"))
        result = OpenInterestThresholdRuleCandidate.evaluate(feature, _spec(threshold="10000"))
        self.assertEqual(result.feature_value, Decimal("54321.987"))
        self.assertEqual(result.threshold, Decimal("10000"))


class TestEvaluatePurityAndDeterminism(unittest.TestCase):
    def test_repeated_calls_with_identical_input_yield_identical_output(self):
        feature = _feature(Decimal("50000"))
        spec = _spec()
        first = OpenInterestThresholdRuleCandidate.evaluate(feature, spec)
        second = OpenInterestThresholdRuleCandidate.evaluate(feature, spec)
        self.assertEqual(first, second)

    def test_an_intervening_different_call_does_not_affect_a_later_identical_call(self):
        feature_a = _feature(Decimal("50000"), symbol=Symbol("BTC"))
        spec_a = _spec(symbol=Symbol("BTC"))
        feature_b = _feature(Decimal("5"), symbol=Symbol("ETH"))
        spec_b = _spec(symbol=Symbol("ETH"))

        result_a1 = OpenInterestThresholdRuleCandidate.evaluate(feature_a, spec_a)
        OpenInterestThresholdRuleCandidate.evaluate(feature_b, spec_b)
        result_a2 = OpenInterestThresholdRuleCandidate.evaluate(feature_a, spec_a)

        self.assertEqual(result_a1, result_a2)

    def test_two_separate_instances_evaluate_identically(self):
        feature = _feature(Decimal("50000"))
        spec = _spec()
        instance_1 = OpenInterestThresholdRuleCandidate()
        instance_2 = OpenInterestThresholdRuleCandidate()
        self.assertEqual(instance_1.evaluate(feature, spec), instance_2.evaluate(feature, spec))


if __name__ == "__main__":
    unittest.main()
