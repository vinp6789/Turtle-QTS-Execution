"""Verification tests for the Funding Rate Threshold Rule Candidate
(Alpha Engine Milestone 3.2).

Tests the evaluation layer in isolation: a FeatureValue and a
CandidateSpecification are constructed directly (no real provider/engine
needed), since FundingRateThresholdRuleCandidate.evaluate() is a pure
function of exactly those two arguments. Mirrors the layering already
used for M2.1's feature tests.
"""

import unittest
from decimal import Decimal

from exchange_adapter import Symbol

from alpha_engine.candidates import (
    CandidateError,
    CandidateSignal,
    FundingRateThresholdRuleCandidate,
    SignalDirection,
    funding_rate_candidate_specification,
)
from alpha_engine.features import FeatureValue


def _feature_value(value=Decimal("0.0001"), symbol=None, computed_at="2026-01-01T00:00:00+00:00",
                    feature_name="funding_rate_raw", feature_version="v1", available=True, reason=None):
    return FeatureValue(
        feature_name=feature_name, feature_version=feature_version, symbol=symbol or Symbol("BTC"),
        computed_at_utc=computed_at, available=available,
        value=value if available else None, reason=reason,
    )


def _spec(threshold="0.0005", direction_convention=None, symbol=None, version="v1"):
    parameters = {"threshold": threshold}
    if direction_convention is not None:
        parameters["direction_convention"] = direction_convention
    return funding_rate_candidate_specification(
        version=version, universe=(symbol or Symbol("BTC"),), cadence_seconds=60,
        parameters=parameters, acceptance_criteria={"min_sharpe": 0.5},
    )


class TestCandidateSignalValidation(unittest.TestCase):
    def test_available_without_direction_raises(self):
        with self.assertRaises(CandidateError):
            CandidateSignal(
                candidate_name="x", candidate_version="v1", symbol=Symbol("BTC"),
                evaluated_at_utc="2026-01-01T00:00:00+00:00", available=True,
                direction=None, feature_value=Decimal("1"), threshold=Decimal("1"),
            )

    def test_available_without_feature_value_raises(self):
        with self.assertRaises(CandidateError):
            CandidateSignal(
                candidate_name="x", candidate_version="v1", symbol=Symbol("BTC"),
                evaluated_at_utc="2026-01-01T00:00:00+00:00", available=True,
                direction=SignalDirection.FLAT, feature_value=None, threshold=Decimal("1"),
            )

    def test_available_without_threshold_raises(self):
        with self.assertRaises(CandidateError):
            CandidateSignal(
                candidate_name="x", candidate_version="v1", symbol=Symbol("BTC"),
                evaluated_at_utc="2026-01-01T00:00:00+00:00", available=True,
                direction=SignalDirection.FLAT, feature_value=Decimal("1"), threshold=None,
            )

    def test_available_with_reason_raises(self):
        with self.assertRaises(CandidateError):
            CandidateSignal(
                candidate_name="x", candidate_version="v1", symbol=Symbol("BTC"),
                evaluated_at_utc="2026-01-01T00:00:00+00:00", available=True,
                direction=SignalDirection.FLAT, feature_value=Decimal("1"), threshold=Decimal("1"),
                reason="should not be set",
            )

    def test_unavailable_with_direction_raises(self):
        with self.assertRaises(CandidateError):
            CandidateSignal(
                candidate_name="x", candidate_version="v1", symbol=Symbol("BTC"),
                evaluated_at_utc="2026-01-01T00:00:00+00:00", available=False,
                direction=SignalDirection.FLAT, reason="x",
            )

    def test_unavailable_without_reason_raises(self):
        with self.assertRaises(CandidateError):
            CandidateSignal(
                candidate_name="x", candidate_version="v1", symbol=Symbol("BTC"),
                evaluated_at_utc="2026-01-01T00:00:00+00:00", available=False, reason=None,
            )


class TestSignalDirectionEnum(unittest.TestCase):
    def test_exactly_three_directions(self):
        self.assertEqual({d.value for d in SignalDirection}, {"long", "short", "flat"})


class TestEvaluateInputValidation(unittest.TestCase):
    def test_rejects_non_feature_value(self):
        with self.assertRaises(CandidateError):
            FundingRateThresholdRuleCandidate.evaluate("not-a-feature-value", _spec())

    def test_rejects_non_specification(self):
        with self.assertRaises(CandidateError):
            FundingRateThresholdRuleCandidate.evaluate(_feature_value(), "not-a-spec")

    def test_rejects_specification_for_a_different_candidate_name(self):
        spec = _spec()
        # Construct via CandidateSpecification directly to defeat the factory's own fixed name.
        from alpha_engine.candidates import CandidateSpecification
        wrong = CandidateSpecification(
            name="something_else", version="v1", candidate_type="rule_based",
            universe=spec.universe, feature_name=spec.feature_name, feature_version=spec.feature_version,
            cadence_seconds=60, acceptance_criteria={"min_sharpe": 0.5}, parameters={"threshold": "0.0005"},
        )
        with self.assertRaises(CandidateError):
            FundingRateThresholdRuleCandidate.evaluate(_feature_value(), wrong)

    def test_rejects_specification_for_a_different_candidate_type(self):
        from alpha_engine.candidates import CandidateSpecification
        spec = _spec()
        wrong = CandidateSpecification(
            name="funding_rate_threshold_rule", version="v1", candidate_type="statistical",
            universe=spec.universe, feature_name=spec.feature_name, feature_version=spec.feature_version,
            cadence_seconds=60, acceptance_criteria={"min_sharpe": 0.5}, parameters={"threshold": "0.0005"},
        )
        with self.assertRaises(CandidateError):
            FundingRateThresholdRuleCandidate.evaluate(_feature_value(), wrong)

    def test_rejects_mismatched_feature_name(self):
        mismatched = _feature_value(feature_name="some_other_feature")
        with self.assertRaises(CandidateError):
            FundingRateThresholdRuleCandidate.evaluate(mismatched, _spec())

    def test_rejects_mismatched_feature_version(self):
        mismatched = _feature_value(feature_version="v2")
        with self.assertRaises(CandidateError):
            FundingRateThresholdRuleCandidate.evaluate(mismatched, _spec())

    def test_missing_threshold_parameter_raises(self):
        spec = funding_rate_candidate_specification(
            version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
            parameters={}, acceptance_criteria={"min_sharpe": 0.5},
        )
        with self.assertRaises(CandidateError):
            FundingRateThresholdRuleCandidate.evaluate(_feature_value(), spec)

    def test_non_numeric_threshold_raises(self):
        with self.assertRaises(CandidateError):
            FundingRateThresholdRuleCandidate.evaluate(_feature_value(), _spec(threshold="not-a-number"))

    def test_zero_threshold_raises(self):
        with self.assertRaises(CandidateError):
            FundingRateThresholdRuleCandidate.evaluate(_feature_value(), _spec(threshold="0"))

    def test_negative_threshold_raises(self):
        with self.assertRaises(CandidateError):
            FundingRateThresholdRuleCandidate.evaluate(_feature_value(), _spec(threshold="-0.0005"))

    def test_invalid_direction_convention_raises(self):
        with self.assertRaises(CandidateError):
            FundingRateThresholdRuleCandidate.evaluate(
                _feature_value(), _spec(direction_convention="sideways")
            )


class TestEvaluateUnavailableFeature(unittest.TestCase):
    def test_unavailable_feature_yields_unavailable_signal(self):
        feature = _feature_value(available=False, reason="input reading unavailable: stale")
        result = FundingRateThresholdRuleCandidate.evaluate(feature, _spec())
        self.assertFalse(result.available)
        self.assertIsNone(result.direction)
        self.assertIn("stale", result.reason)

    def test_unavailable_feature_never_raises(self):
        feature = _feature_value(available=False, reason="ExchangeConnectionError: outage")
        try:
            result = FundingRateThresholdRuleCandidate.evaluate(feature, _spec())
        except Exception as exc:  # noqa: BLE001
            self.fail(f"evaluate() must never raise for an unavailable feature, raised {exc!r}")
        self.assertFalse(result.available)


class TestEvaluateContrarian(unittest.TestCase):
    def test_positive_beyond_threshold_is_short(self):
        feature = _feature_value(value=Decimal("0.0010"))
        result = FundingRateThresholdRuleCandidate.evaluate(feature, _spec(threshold="0.0005"))
        self.assertTrue(result.available)
        self.assertEqual(result.direction, SignalDirection.SHORT)

    def test_negative_beyond_threshold_is_long(self):
        feature = _feature_value(value=Decimal("-0.0010"))
        result = FundingRateThresholdRuleCandidate.evaluate(feature, _spec(threshold="0.0005"))
        self.assertEqual(result.direction, SignalDirection.LONG)

    def test_within_band_is_flat(self):
        feature = _feature_value(value=Decimal("0.0001"))
        result = FundingRateThresholdRuleCandidate.evaluate(feature, _spec(threshold="0.0005"))
        self.assertEqual(result.direction, SignalDirection.FLAT)

    def test_exactly_at_positive_threshold_is_flat(self):
        feature = _feature_value(value=Decimal("0.0005"))
        result = FundingRateThresholdRuleCandidate.evaluate(feature, _spec(threshold="0.0005"))
        self.assertEqual(result.direction, SignalDirection.FLAT)

    def test_exactly_at_negative_threshold_is_flat(self):
        feature = _feature_value(value=Decimal("-0.0005"))
        result = FundingRateThresholdRuleCandidate.evaluate(feature, _spec(threshold="0.0005"))
        self.assertEqual(result.direction, SignalDirection.FLAT)

    def test_contrarian_is_the_default_convention(self):
        feature = _feature_value(value=Decimal("0.0010"))
        result = FundingRateThresholdRuleCandidate.evaluate(feature, _spec(threshold="0.0005"))  # no direction_convention given
        self.assertEqual(result.direction, SignalDirection.SHORT)


class TestEvaluateMomentum(unittest.TestCase):
    def test_positive_beyond_threshold_is_long(self):
        feature = _feature_value(value=Decimal("0.0010"))
        result = FundingRateThresholdRuleCandidate.evaluate(
            feature, _spec(threshold="0.0005", direction_convention="momentum")
        )
        self.assertEqual(result.direction, SignalDirection.LONG)

    def test_negative_beyond_threshold_is_short(self):
        feature = _feature_value(value=Decimal("-0.0010"))
        result = FundingRateThresholdRuleCandidate.evaluate(
            feature, _spec(threshold="0.0005", direction_convention="momentum")
        )
        self.assertEqual(result.direction, SignalDirection.SHORT)


class TestEvaluateSignalContent(unittest.TestCase):
    def test_evaluated_at_utc_matches_feature_computed_at(self):
        feature = _feature_value(value=Decimal("0.0001"), computed_at="2026-03-01T12:00:00+00:00")
        result = FundingRateThresholdRuleCandidate.evaluate(feature, _spec())
        self.assertEqual(result.evaluated_at_utc, "2026-03-01T12:00:00+00:00")

    def test_symbol_carried_through(self):
        feature = _feature_value(symbol=Symbol("ETH"))
        spec = _spec(symbol=Symbol("ETH"))
        result = FundingRateThresholdRuleCandidate.evaluate(feature, spec)
        self.assertEqual(result.symbol, Symbol("ETH"))

    def test_candidate_name_and_version_match_specification(self):
        feature = _feature_value()
        spec = _spec(version="v7")
        result = FundingRateThresholdRuleCandidate.evaluate(feature, spec)
        self.assertEqual(result.candidate_name, "funding_rate_threshold_rule")
        self.assertEqual(result.candidate_version, "v7")

    def test_feature_value_and_threshold_recorded_exactly(self):
        feature = _feature_value(value=Decimal("0.0013"))
        result = FundingRateThresholdRuleCandidate.evaluate(feature, _spec(threshold="0.0005"))
        self.assertEqual(result.feature_value, Decimal("0.0013"))
        self.assertEqual(result.threshold, Decimal("0.0005"))


class TestEvaluatePurityAndDeterminism(unittest.TestCase):
    def test_repeated_calls_with_identical_input_yield_identical_output(self):
        feature = _feature_value(value=Decimal("0.0010"))
        spec = _spec()
        first = FundingRateThresholdRuleCandidate.evaluate(feature, spec)
        second = FundingRateThresholdRuleCandidate.evaluate(feature, spec)
        self.assertEqual(first, second)

    def test_an_intervening_different_call_does_not_affect_a_later_identical_call(self):
        feature_a = _feature_value(value=Decimal("0.0010"), symbol=Symbol("BTC"))
        spec_a = _spec(symbol=Symbol("BTC"))
        feature_b = _feature_value(value=Decimal("-0.0020"), symbol=Symbol("ETH"))
        spec_b = _spec(symbol=Symbol("ETH"))

        result_a1 = FundingRateThresholdRuleCandidate.evaluate(feature_a, spec_a)
        FundingRateThresholdRuleCandidate.evaluate(feature_b, spec_b)
        result_a2 = FundingRateThresholdRuleCandidate.evaluate(feature_a, spec_a)

        self.assertEqual(result_a1, result_a2)

    def test_two_separate_instances_evaluate_identically(self):
        feature = _feature_value(value=Decimal("0.0010"))
        spec = _spec()
        instance_1 = FundingRateThresholdRuleCandidate()
        instance_2 = FundingRateThresholdRuleCandidate()
        self.assertEqual(instance_1.evaluate(feature, spec), instance_2.evaluate(feature, spec))


if __name__ == "__main__":
    unittest.main()
