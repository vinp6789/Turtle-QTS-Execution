"""Verification tests for the regime stratification stage (Alpha Engine
Milestone 4.6).

Synthetic test fixture data throughout -- see
test_alpha_engine_validation_runner.py's own note; the same applies here.
Regime labels ("risk_on"/"risk_off") are arbitrary test taxonomy, not a
claim this system detects real market regimes.
"""

import json
import unittest
from decimal import Decimal

from exchange_adapter import Symbol

from alpha_engine.candidates import FundingRateThresholdRuleCandidate, funding_rate_candidate_specification
from alpha_engine.features import FeatureValue
from alpha_engine.validation import (
    RegimeStratificationResult,
    ValidationError,
    ValidationResult,
    ValidationSample,
    evidence_package_from_validation_result,
    run_regime_stratified_validation,
    run_validation,
)


def _feature(value, computed_at="2026-01-01T00:00:00+00:00", symbol=None):
    return FeatureValue(
        feature_name="funding_rate_raw", feature_version="v1", symbol=symbol or Symbol("BTC"),
        computed_at_utc=computed_at, available=True, value=value,
    )


def _sample(value, outcome, computed_at="2026-01-01T00:00:00+00:00", regime=None):
    return ValidationSample(
        feature_value=_feature(value, computed_at=computed_at),
        realized_outcome=Decimal(outcome), regime_label=regime,
    )


def _spec(threshold="0.0005", acceptance_criteria=None):
    return funding_rate_candidate_specification(
        version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
        parameters={"threshold": threshold},
        acceptance_criteria=acceptance_criteria or {"min_hit_rate": 0.5},
    )


class TestValidationSampleRegimeLabel(unittest.TestCase):
    def test_defaults_to_none(self):
        self.assertIsNone(_sample(Decimal("0.001"), "0.01").regime_label)

    def test_accepts_a_valid_string(self):
        self.assertEqual(_sample(Decimal("0.001"), "0.01", regime="risk_on").regime_label, "risk_on")

    def test_rejects_blank_string(self):
        with self.assertRaises(ValidationError):
            ValidationSample(feature_value=_feature(Decimal("0.001")), realized_outcome=Decimal("0.01"), regime_label="  ")


class TestInputValidation(unittest.TestCase):
    def test_non_callable_evaluate_fn_raises(self):
        with self.assertRaises(ValidationError):
            run_regime_stratified_validation(
                "not-callable", _spec(), (_sample(Decimal("0.001"), "0.01", regime="risk_on"),)
            )

    def test_non_specification_raises(self):
        with self.assertRaises(ValidationError):
            run_regime_stratified_validation(
                FundingRateThresholdRuleCandidate.evaluate, "not-a-spec",
                (_sample(Decimal("0.001"), "0.01", regime="risk_on"),),
            )

    def test_empty_samples_raises(self):
        with self.assertRaises(ValidationError):
            run_regime_stratified_validation(FundingRateThresholdRuleCandidate.evaluate, _spec(), ())

    def test_non_tuple_samples_raises(self):
        with self.assertRaises(ValidationError):
            run_regime_stratified_validation(
                FundingRateThresholdRuleCandidate.evaluate, _spec(),
                [_sample(Decimal("0.001"), "0.01", regime="risk_on")],
            )

    def test_non_sample_items_raise(self):
        with self.assertRaises(ValidationError):
            run_regime_stratified_validation(FundingRateThresholdRuleCandidate.evaluate, _spec(), ("not-a-sample",))


class TestGrouping(unittest.TestCase):
    def test_samples_grouped_by_regime_label(self):
        samples = (
            _sample(Decimal("0.0010"), "-0.02", regime="risk_on"),
            _sample(Decimal("-0.0010"), "0.02", regime="risk_off"),
            _sample(Decimal("0.0010"), "-0.03", regime="risk_on"),
        )
        result = run_regime_stratified_validation(FundingRateThresholdRuleCandidate.evaluate, _spec(), samples)
        self.assertEqual(set(result.regime_results.keys()), {"risk_on", "risk_off"})
        self.assertEqual(result.regime_results["risk_on"].total_samples, 2)
        self.assertEqual(result.regime_results["risk_off"].total_samples, 1)

    def test_unlabeled_samples_are_not_placed_in_any_regime(self):
        samples = (
            _sample(Decimal("0.0010"), "-0.02", regime="risk_on"),
            _sample(Decimal("0.0010"), "-0.02", regime=None),
        )
        result = run_regime_stratified_validation(FundingRateThresholdRuleCandidate.evaluate, _spec(), samples)
        self.assertEqual(result.unstratified_sample_count, 1)
        self.assertEqual(result.regime_results["risk_on"].total_samples, 1)

    def test_n_regimes_observed_matches_distinct_labels(self):
        samples = (
            _sample(Decimal("0.0010"), "-0.02", regime="a"),
            _sample(Decimal("0.0010"), "-0.02", regime="b"),
            _sample(Decimal("0.0010"), "-0.02", regime="c"),
        )
        result = run_regime_stratified_validation(FundingRateThresholdRuleCandidate.evaluate, _spec(), samples)
        self.assertEqual(result.n_regimes_observed, 3)

    def test_all_unlabeled_yields_zero_regimes(self):
        samples = (_sample(Decimal("0.0010"), "-0.02", regime=None),)
        result = run_regime_stratified_validation(FundingRateThresholdRuleCandidate.evaluate, _spec(), samples)
        self.assertEqual(result.n_regimes_observed, 0)
        self.assertEqual(result.unstratified_sample_count, 1)
        self.assertEqual(result.regime_results, {})


class TestOverallPassed(unittest.TestCase):
    def test_passes_when_every_regime_clears_criteria_and_none_unstratified(self):
        samples = (
            _sample(Decimal("0.0010"), "-0.02", regime="risk_on"),   # hit
            _sample(Decimal("-0.0010"), "0.02", regime="risk_off"),  # hit
        )
        spec = _spec(acceptance_criteria={"min_hit_rate": 0.5})
        result = run_regime_stratified_validation(FundingRateThresholdRuleCandidate.evaluate, spec, samples)
        self.assertTrue(result.overall_passed)

    def test_fails_when_any_regime_fails_its_own_criteria(self):
        samples = (
            _sample(Decimal("0.0010"), "-0.02", regime="risk_on"),  # hit
            _sample(Decimal("0.0010"), "0.02", regime="risk_off"),  # miss
        )
        spec = _spec(acceptance_criteria={"min_hit_rate": 0.9})
        result = run_regime_stratified_validation(FundingRateThresholdRuleCandidate.evaluate, spec, samples)
        self.assertFalse(result.overall_passed)
        self.assertTrue(result.regime_results["risk_on"].overall_passed)
        self.assertFalse(result.regime_results["risk_off"].overall_passed)

    def test_fails_when_any_sample_is_unstratified_even_if_all_regimes_pass(self):
        samples = (
            _sample(Decimal("0.0010"), "-0.02", regime="risk_on"),  # hit
            _sample(Decimal("0.0010"), "-0.02", regime=None),       # unlabeled
        )
        spec = _spec(acceptance_criteria={"min_hit_rate": 0.5})
        result = run_regime_stratified_validation(FundingRateThresholdRuleCandidate.evaluate, spec, samples)
        self.assertTrue(result.regime_results["risk_on"].overall_passed)
        self.assertFalse(result.overall_passed)  # blocked by the unlabeled sample

    def test_fails_when_zero_regimes_observed(self):
        samples = (_sample(Decimal("0.0010"), "-0.02", regime=None),)
        result = run_regime_stratified_validation(FundingRateThresholdRuleCandidate.evaluate, _spec(), samples)
        self.assertFalse(result.overall_passed)


class TestRegimeStratificationResultValidation(unittest.TestCase):
    def _valid_result(self):
        samples = (_sample(Decimal("0.0010"), "-0.02", regime="risk_on"),)
        return run_regime_stratified_validation(FundingRateThresholdRuleCandidate.evaluate, _spec(), samples)

    def test_n_regimes_observed_mismatch_raises(self):
        result = self._valid_result()
        with self.assertRaises(ValidationError):
            RegimeStratificationResult(
                candidate_name=result.candidate_name, candidate_version=result.candidate_version,
                regime_results=result.regime_results, n_regimes_observed=99,
                unstratified_sample_count=0, validated_at_utc=result.validated_at_utc, overall_passed=True,
            )

    def test_non_validation_result_value_raises(self):
        with self.assertRaises(ValidationError):
            RegimeStratificationResult(
                candidate_name="x", candidate_version="v1", regime_results={"risk_on": "not-a-validation-result"},
                n_regimes_observed=1, unstratified_sample_count=0,
                validated_at_utc="2026-01-01T00:00:00+00:00", overall_passed=False,
            )

    def test_blank_regime_key_raises(self):
        result = self._valid_result()
        with self.assertRaises(ValidationError):
            RegimeStratificationResult(
                candidate_name=result.candidate_name, candidate_version=result.candidate_version,
                regime_results={" ": next(iter(result.regime_results.values()))},
                n_regimes_observed=1, unstratified_sample_count=0,
                validated_at_utc=result.validated_at_utc, overall_passed=True,
            )

    def test_overall_passed_inconsistency_raises(self):
        result = self._valid_result()
        with self.assertRaises(ValidationError):
            RegimeStratificationResult(
                candidate_name=result.candidate_name, candidate_version=result.candidate_version,
                regime_results=result.regime_results, n_regimes_observed=result.n_regimes_observed,
                unstratified_sample_count=result.unstratified_sample_count,
                validated_at_utc=result.validated_at_utc, overall_passed=not result.overall_passed,
            )

    def test_to_dict_shape_sorted_and_json_serializable(self):
        samples = (
            _sample(Decimal("0.0010"), "-0.02", regime="b_regime"),
            _sample(Decimal("-0.0010"), "0.02", regime="a_regime"),
        )
        result = run_regime_stratified_validation(FundingRateThresholdRuleCandidate.evaluate, _spec(), samples)
        d = result.to_dict()
        self.assertEqual(list(d["regime_results"].keys()), ["a_regime", "b_regime"])  # sorted
        json.dumps(d)


class TestDeterminism(unittest.TestCase):
    def test_identical_inputs_yield_identical_result_with_fixed_clock(self):
        samples = (
            _sample(Decimal("0.0010"), "-0.02", regime="risk_on"),
            _sample(Decimal("-0.0010"), "0.02", regime="risk_off"),
        )
        spec = _spec()
        clock = lambda: "2026-08-01T00:00:00+00:00"
        r1 = run_regime_stratified_validation(FundingRateThresholdRuleCandidate.evaluate, spec, samples, clock=clock)
        r2 = run_regime_stratified_validation(FundingRateThresholdRuleCandidate.evaluate, spec, samples, clock=clock)
        self.assertEqual(r1, r2)


class TestEvidencePackageIntegration(unittest.TestCase):
    def test_regime_stratification_attaches_as_a_new_stage(self):
        samples = (
            _sample(Decimal("0.0010"), "-0.02", regime="risk_on"),
            _sample(Decimal("-0.0010"), "0.02", regime="risk_off"),
        )
        spec = _spec()
        single_pass = run_validation(FundingRateThresholdRuleCandidate.evaluate, spec, samples)
        package = evidence_package_from_validation_result(spec, "single_pass_threshold", single_pass)

        regime_result = run_regime_stratified_validation(FundingRateThresholdRuleCandidate.evaluate, spec, samples)
        extended = package.with_stage_result("regime_stratification", regime_result.to_dict())

        self.assertEqual(set(extended.validation_results.keys()), {"single_pass_threshold", "regime_stratification"})
        self.assertNotEqual(extended.fingerprint, package.fingerprint)
        reloaded = json.loads(json.dumps(extended.to_dict()))
        self.assertEqual(reloaded, extended.to_dict())


if __name__ == "__main__":
    unittest.main()
