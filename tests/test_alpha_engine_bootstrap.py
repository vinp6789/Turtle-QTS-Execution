"""Verification tests for the bootstrap resampling stage (Alpha Engine
Milestone 4.5).

Synthetic test fixture data throughout -- see
test_alpha_engine_validation_runner.py's own note; the same applies here.
"""

import json
import unittest
from decimal import Decimal

from exchange_adapter import Symbol

from alpha_engine.candidates import FundingRateThresholdRuleCandidate, funding_rate_candidate_specification
from alpha_engine.features import FeatureValue
from alpha_engine.validation import (
    BootstrapResult,
    ValidationError,
    ValidationSample,
    evidence_package_from_validation_result,
    run_bootstrap_resampling,
    run_validation,
)


def _feature(value, computed_at, symbol=None):
    return FeatureValue(
        feature_name="funding_rate_raw", feature_version="v1", symbol=symbol or Symbol("BTC"),
        computed_at_utc=computed_at, available=True, value=value,
    )


def _sample(value, outcome, computed_at):
    return ValidationSample(feature_value=_feature(value, computed_at), realized_outcome=Decimal(outcome))


def _spec(threshold="0.0005", acceptance_criteria=None):
    return funding_rate_candidate_specification(
        version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
        parameters={"threshold": threshold},
        acceptance_criteria=acceptance_criteria or {"min_hit_rate": 0.5},
    )


class TestInputValidation(unittest.TestCase):
    def _samples(self):
        return (_sample(Decimal("0.0010"), "-0.02", "2026-01-01T00:00:00+00:00"),)

    def test_non_callable_evaluate_fn_raises(self):
        with self.assertRaises(ValidationError):
            run_bootstrap_resampling("not-callable", _spec(), self._samples(), n_resamples=5, seed=1)

    def test_non_specification_raises(self):
        with self.assertRaises(ValidationError):
            run_bootstrap_resampling(
                FundingRateThresholdRuleCandidate.evaluate, "not-a-spec", self._samples(), n_resamples=5, seed=1
            )

    def test_empty_samples_raises(self):
        with self.assertRaises(ValidationError):
            run_bootstrap_resampling(FundingRateThresholdRuleCandidate.evaluate, _spec(), (), n_resamples=5, seed=1)

    def test_non_tuple_samples_raises(self):
        with self.assertRaises(ValidationError):
            run_bootstrap_resampling(
                FundingRateThresholdRuleCandidate.evaluate, _spec(), list(self._samples()), n_resamples=5, seed=1
            )

    def test_non_sample_items_raise(self):
        with self.assertRaises(ValidationError):
            run_bootstrap_resampling(
                FundingRateThresholdRuleCandidate.evaluate, _spec(), ("not-a-sample",), n_resamples=5, seed=1
            )

    def test_zero_n_resamples_raises(self):
        with self.assertRaises(ValidationError):
            run_bootstrap_resampling(
                FundingRateThresholdRuleCandidate.evaluate, _spec(), self._samples(), n_resamples=0, seed=1
            )

    def test_negative_n_resamples_raises(self):
        with self.assertRaises(ValidationError):
            run_bootstrap_resampling(
                FundingRateThresholdRuleCandidate.evaluate, _spec(), self._samples(), n_resamples=-5, seed=1
            )

    def test_bool_n_resamples_raises(self):
        with self.assertRaises(ValidationError):
            run_bootstrap_resampling(
                FundingRateThresholdRuleCandidate.evaluate, _spec(), self._samples(), n_resamples=True, seed=1
            )

    def test_non_int_seed_raises(self):
        with self.assertRaises(ValidationError):
            run_bootstrap_resampling(
                FundingRateThresholdRuleCandidate.evaluate, _spec(), self._samples(), n_resamples=5, seed="not-an-int"
            )

    def test_bool_seed_raises(self):
        with self.assertRaises(ValidationError):
            run_bootstrap_resampling(
                FundingRateThresholdRuleCandidate.evaluate, _spec(), self._samples(), n_resamples=5, seed=True
            )

    def test_malformed_min_hit_rate_criterion_raises(self):
        spec = _spec(acceptance_criteria={"min_hit_rate": "not-a-number"})
        with self.assertRaises(ValidationError):
            run_bootstrap_resampling(
                FundingRateThresholdRuleCandidate.evaluate, spec, self._samples(), n_resamples=5, seed=1
            )


class TestBootstrapResultValidation(unittest.TestCase):
    def _valid_kwargs(self, **overrides):
        kwargs = dict(
            candidate_name="x", candidate_version="v1", n_resamples=10, resample_size=3, seed=1,
            resamples_with_hit_rate=10, mean_hit_rate=Decimal("0.5"),
            min_hit_rate_observed=Decimal("0.3"), max_hit_rate_observed=Decimal("0.7"),
            fraction_meeting_min_hit_rate=Decimal("0.4"), validated_at_utc="2026-01-01T00:00:00+00:00",
        )
        kwargs.update(overrides)
        return kwargs

    def test_valid_result_constructs(self):
        BootstrapResult(**self._valid_kwargs())

    def test_negative_count_raises(self):
        with self.assertRaises(ValidationError):
            BootstrapResult(**self._valid_kwargs(n_resamples=-1))

    def test_non_int_seed_raises(self):
        with self.assertRaises(ValidationError):
            BootstrapResult(**self._valid_kwargs(seed="1"))

    def test_bool_seed_raises(self):
        with self.assertRaises(ValidationError):
            BootstrapResult(**self._valid_kwargs(seed=True))

    def test_resamples_with_hit_rate_exceeding_n_resamples_raises(self):
        with self.assertRaises(ValidationError):
            BootstrapResult(**self._valid_kwargs(resamples_with_hit_rate=99))

    def test_zero_resamples_with_hit_rate_requires_none_stats(self):
        with self.assertRaises(ValidationError):
            BootstrapResult(**self._valid_kwargs(resamples_with_hit_rate=0, mean_hit_rate=Decimal("0.5")))

    def test_positive_resamples_with_hit_rate_requires_decimal_stats(self):
        with self.assertRaises(ValidationError):
            BootstrapResult(**self._valid_kwargs(mean_hit_rate=None))

    def test_mean_outside_min_max_range_raises(self):
        with self.assertRaises(ValidationError):
            BootstrapResult(**self._valid_kwargs(
                mean_hit_rate=Decimal("0.9"), min_hit_rate_observed=Decimal("0.3"), max_hit_rate_observed=Decimal("0.7"),
            ))

    def test_fraction_out_of_range_raises(self):
        with self.assertRaises(ValidationError):
            BootstrapResult(**self._valid_kwargs(fraction_meeting_min_hit_rate=Decimal("1.5")))

    def test_blank_validated_at_utc_raises(self):
        with self.assertRaises(ValidationError):
            BootstrapResult(**self._valid_kwargs(validated_at_utc=""))

    def test_to_dict_shape_and_json_serializable(self):
        result = BootstrapResult(**self._valid_kwargs())
        d = result.to_dict()
        self.assertEqual(d["seed"], 1)
        self.assertEqual(d["mean_hit_rate"], "0.5")
        json.dumps(d)

    def test_to_dict_none_when_zero_resamples_with_hit_rate(self):
        result = BootstrapResult(**self._valid_kwargs(
            resamples_with_hit_rate=0, mean_hit_rate=None, min_hit_rate_observed=None,
            max_hit_rate_observed=None, fraction_meeting_min_hit_rate=None,
        ))
        d = result.to_dict()
        self.assertIsNone(d["mean_hit_rate"])
        self.assertIsNone(d["fraction_meeting_min_hit_rate"])


class TestDeterministicSingleSample(unittest.TestCase):
    """With exactly one sample, every resample (with replacement, size 1)
    is trivially that same sample -- a fully hand-verifiable case
    regardless of seed or RNG internals."""

    def _single_hit_sample(self):
        # threshold=0.0005, contrarian: rate=0.0010 (>threshold) -> SHORT; outcome negative -> hit
        return (_sample(Decimal("0.0010"), "-0.02", "2026-01-01T00:00:00+00:00"),)

    def test_every_resample_is_identical_to_the_single_sample(self):
        result = run_bootstrap_resampling(
            FundingRateThresholdRuleCandidate.evaluate, _spec(threshold="0.0005"),
            self._single_hit_sample(), n_resamples=20, seed=7,
        )
        self.assertEqual(result.resamples_with_hit_rate, 20)
        self.assertEqual(result.mean_hit_rate, Decimal("1"))
        self.assertEqual(result.min_hit_rate_observed, Decimal("1"))
        self.assertEqual(result.max_hit_rate_observed, Decimal("1"))

    def test_fraction_meeting_min_hit_rate_is_one_when_bar_is_clearable(self):
        spec = _spec(threshold="0.0005", acceptance_criteria={"min_hit_rate": 0.5})
        result = run_bootstrap_resampling(
            FundingRateThresholdRuleCandidate.evaluate, spec, self._single_hit_sample(), n_resamples=10, seed=1,
        )
        self.assertEqual(result.fraction_meeting_min_hit_rate, Decimal("1"))

    def test_fraction_meeting_min_hit_rate_is_zero_when_bar_is_too_high(self):
        # every resample achieves hit_rate exactly 1.0; requiring > 1 makes it unmeetable... use a
        # deliberately unattainable bar via a losing sample instead: rate beyond threshold but a MISS.
        losing_sample = (_sample(Decimal("0.0010"), "0.02", "2026-01-01T00:00:00+00:00"),)  # SHORT signal, positive outcome -> miss
        spec = _spec(threshold="0.0005", acceptance_criteria={"min_hit_rate": 0.5})
        result = run_bootstrap_resampling(
            FundingRateThresholdRuleCandidate.evaluate, spec, losing_sample, n_resamples=10, seed=1,
        )
        self.assertEqual(result.mean_hit_rate, Decimal("0"))
        self.assertEqual(result.fraction_meeting_min_hit_rate, Decimal("0"))

    def test_fraction_meeting_min_hit_rate_is_none_when_criterion_not_declared(self):
        spec = _spec(threshold="0.0005", acceptance_criteria={"min_signaled_samples": 1})
        result = run_bootstrap_resampling(
            FundingRateThresholdRuleCandidate.evaluate, spec, self._single_hit_sample(), n_resamples=10, seed=1,
        )
        self.assertIsNone(result.fraction_meeting_min_hit_rate)


class TestAllFlatSamples(unittest.TestCase):
    def test_zero_resamples_with_hit_rate_when_every_sample_is_flat(self):
        flat_samples = (_sample(Decimal("0.0001"), "0.01", "2026-01-01T00:00:00+00:00"),)  # within threshold band -> FLAT
        result = run_bootstrap_resampling(
            FundingRateThresholdRuleCandidate.evaluate, _spec(threshold="0.0005"),
            flat_samples, n_resamples=10, seed=1,
        )
        self.assertEqual(result.resamples_with_hit_rate, 0)
        self.assertIsNone(result.mean_hit_rate)
        self.assertIsNone(result.min_hit_rate_observed)
        self.assertIsNone(result.max_hit_rate_observed)


class TestSelfDocumentation(unittest.TestCase):
    def test_seed_and_resample_size_recorded(self):
        samples = (_sample(Decimal("0.0010"), "-0.02", "2026-01-01T00:00:00+00:00"),)
        result = run_bootstrap_resampling(
            FundingRateThresholdRuleCandidate.evaluate, _spec(), samples, n_resamples=15, seed=999,
        )
        self.assertEqual(result.seed, 999)
        self.assertEqual(result.n_resamples, 15)
        self.assertEqual(result.resample_size, 1)

    def test_candidate_name_and_version_match_specification(self):
        spec = _spec()
        samples = (_sample(Decimal("0.0010"), "-0.02", "2026-01-01T00:00:00+00:00"),)
        result = run_bootstrap_resampling(FundingRateThresholdRuleCandidate.evaluate, spec, samples, n_resamples=5, seed=1)
        self.assertEqual(result.candidate_name, spec.name)
        self.assertEqual(result.candidate_version, spec.version)


class TestDeterminism(unittest.TestCase):
    def test_identical_seed_and_inputs_yield_identical_result(self):
        samples = (
            _sample(Decimal("0.0010"), "-0.02", "2026-01-01T00:00:00+00:00"),
            _sample(Decimal("-0.0010"), "0.02", "2026-01-02T00:00:00+00:00"),
            _sample(Decimal("0.0010"), "0.01", "2026-01-03T00:00:00+00:00"),
        )
        spec = _spec()
        clock = lambda: "2026-07-01T00:00:00+00:00"
        r1 = run_bootstrap_resampling(FundingRateThresholdRuleCandidate.evaluate, spec, samples, n_resamples=25, seed=42, clock=clock)
        r2 = run_bootstrap_resampling(FundingRateThresholdRuleCandidate.evaluate, spec, samples, n_resamples=25, seed=42, clock=clock)
        self.assertEqual(r1, r2)


class TestEvidencePackageIntegration(unittest.TestCase):
    def test_bootstrap_attaches_as_a_new_stage(self):
        samples = (
            _sample(Decimal("0.0010"), "-0.02", "2026-01-01T00:00:00+00:00"),
            _sample(Decimal("-0.0010"), "0.02", "2026-01-02T00:00:00+00:00"),
        )
        spec = _spec()
        single_pass = run_validation(FundingRateThresholdRuleCandidate.evaluate, spec, samples)
        package = evidence_package_from_validation_result(spec, "single_pass_threshold", single_pass)

        bootstrap_result = run_bootstrap_resampling(
            FundingRateThresholdRuleCandidate.evaluate, spec, samples, n_resamples=20, seed=5,
        )
        extended = package.with_stage_result("bootstrap_resampling", bootstrap_result.to_dict())

        self.assertEqual(set(extended.validation_results.keys()), {"single_pass_threshold", "bootstrap_resampling"})
        self.assertNotEqual(extended.fingerprint, package.fingerprint)
        reloaded = json.loads(json.dumps(extended.to_dict()))
        self.assertEqual(reloaded, extended.to_dict())


if __name__ == "__main__":
    unittest.main()
