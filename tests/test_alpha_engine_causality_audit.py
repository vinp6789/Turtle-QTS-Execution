"""Verification tests for the leakage & causality audit stage (Alpha
Engine Milestone 4.3).

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
    CausalityAuditResult,
    ValidationError,
    ValidationSample,
    evidence_package_from_validation_result,
    run_causality_audit,
    run_validation,
)


def _feature(value, computed_at, symbol=None):
    return FeatureValue(
        feature_name="funding_rate_raw", feature_version="v1", symbol=symbol or Symbol("BTC"),
        computed_at_utc=computed_at, available=True, value=value,
    )


def _sample(value, outcome, computed_at="2026-01-01T00:00:00+00:00", observed_at=None, symbol=None):
    return ValidationSample(
        feature_value=_feature(value, computed_at, symbol=symbol),
        realized_outcome=Decimal(outcome),
        outcome_observed_at_utc=observed_at,
    )


class TestValidationSampleAdditiveField(unittest.TestCase):
    def test_defaults_to_none(self):
        sample = _sample(Decimal("0.001"), "0.01")
        self.assertIsNone(sample.outcome_observed_at_utc)

    def test_accepts_a_valid_string(self):
        sample = _sample(Decimal("0.001"), "0.01", observed_at="2026-01-02T00:00:00+00:00")
        self.assertEqual(sample.outcome_observed_at_utc, "2026-01-02T00:00:00+00:00")

    def test_rejects_blank_string(self):
        with self.assertRaises(ValidationError):
            ValidationSample(
                feature_value=_feature(Decimal("0.001"), "2026-01-01T00:00:00+00:00"),
                realized_outcome=Decimal("0.01"), outcome_observed_at_utc="  ",
            )


class TestCausalityAuditResultValidation(unittest.TestCase):
    def _valid_kwargs(self, **overrides):
        kwargs = dict(
            total_samples=2, unique_sample_keys=2, duplicate_samples=0,
            ordering_verified=2, ordering_violated=0, ordering_not_verifiable=0,
            violation_details=(), audited_at_utc="2026-01-01T00:00:00+00:00", passed=True,
        )
        kwargs.update(overrides)
        return kwargs

    def test_valid_result_constructs(self):
        CausalityAuditResult(**self._valid_kwargs())

    def test_negative_count_raises(self):
        with self.assertRaises(ValidationError):
            CausalityAuditResult(**self._valid_kwargs(duplicate_samples=-1))

    def test_key_count_mismatch_raises(self):
        with self.assertRaises(ValidationError):
            CausalityAuditResult(**self._valid_kwargs(unique_sample_keys=99))

    def test_ordering_bucket_mismatch_raises(self):
        with self.assertRaises(ValidationError):
            CausalityAuditResult(**self._valid_kwargs(ordering_verified=99))

    def test_violation_details_non_tuple_raises(self):
        with self.assertRaises(ValidationError):
            CausalityAuditResult(**self._valid_kwargs(violation_details=["x"]))

    def test_violation_details_blank_entry_raises(self):
        with self.assertRaises(ValidationError):
            CausalityAuditResult(**self._valid_kwargs(violation_details=("  ",)))

    def test_blank_audited_at_utc_raises(self):
        with self.assertRaises(ValidationError):
            CausalityAuditResult(**self._valid_kwargs(audited_at_utc=""))

    def test_passed_inconsistent_raises(self):
        with self.assertRaises(ValidationError):
            CausalityAuditResult(**self._valid_kwargs(duplicate_samples=0, passed=False))

    def test_to_dict_shape_and_json_serializable(self):
        result = CausalityAuditResult(**self._valid_kwargs())
        d = result.to_dict()
        self.assertEqual(d["total_samples"], 2)
        self.assertEqual(d["violation_details"], [])
        self.assertTrue(d["passed"])
        json.dumps(d)


class TestRunCausalityAuditInputValidation(unittest.TestCase):
    def test_empty_samples_raises(self):
        with self.assertRaises(ValidationError):
            run_causality_audit(())

    def test_non_tuple_raises(self):
        with self.assertRaises(ValidationError):
            run_causality_audit([_sample(Decimal("0.001"), "0.01")])

    def test_non_sample_items_raise(self):
        with self.assertRaises(ValidationError):
            run_causality_audit(("not-a-sample",))

    def test_unparseable_observed_timestamp_raises(self):
        sample = _sample(Decimal("0.001"), "0.01", observed_at="not-a-timestamp")
        with self.assertRaises(ValidationError):
            run_causality_audit((sample,))


class TestDuplicateDetection(unittest.TestCase):
    def test_no_duplicates_when_all_keys_distinct(self):
        samples = (
            _sample(Decimal("0.001"), "0.01", computed_at="2026-01-01T00:00:00+00:00"),
            _sample(Decimal("0.002"), "0.02", computed_at="2026-01-02T00:00:00+00:00"),
        )
        result = run_causality_audit(samples)
        self.assertEqual(result.duplicate_samples, 0)
        self.assertEqual(result.unique_sample_keys, 2)

    def test_duplicate_symbol_and_timestamp_detected(self):
        samples = (
            _sample(Decimal("0.001"), "0.01", computed_at="2026-01-01T00:00:00+00:00"),
            _sample(Decimal("0.001"), "0.01", computed_at="2026-01-01T00:00:00+00:00"),  # exact duplicate
        )
        result = run_causality_audit(samples)
        self.assertEqual(result.duplicate_samples, 1)
        self.assertEqual(result.unique_sample_keys, 1)
        self.assertFalse(result.passed)
        self.assertTrue(any("duplicate" in v for v in result.violation_details))

    def test_same_timestamp_different_symbol_is_not_a_duplicate(self):
        samples = (
            _sample(Decimal("0.001"), "0.01", computed_at="2026-01-01T00:00:00+00:00", symbol=Symbol("BTC")),
            _sample(Decimal("0.001"), "0.01", computed_at="2026-01-01T00:00:00+00:00", symbol=Symbol("ETH")),
        )
        result = run_causality_audit(samples)
        self.assertEqual(result.duplicate_samples, 0)

    def test_triple_duplicate_counts_two_extras(self):
        samples = tuple(
            _sample(Decimal("0.001"), "0.01", computed_at="2026-01-01T00:00:00+00:00") for _ in range(3)
        )
        result = run_causality_audit(samples)
        self.assertEqual(result.duplicate_samples, 2)
        self.assertEqual(result.unique_sample_keys, 1)


class TestOrderingCheck(unittest.TestCase):
    def test_outcome_strictly_after_feature_is_verified(self):
        sample = _sample(
            Decimal("0.001"), "0.01",
            computed_at="2026-01-01T00:00:00+00:00", observed_at="2026-01-02T00:00:00+00:00",
        )
        result = run_causality_audit((sample,))
        self.assertEqual(result.ordering_verified, 1)
        self.assertEqual(result.ordering_violated, 0)

    def test_outcome_before_feature_is_violated(self):
        sample = _sample(
            Decimal("0.001"), "0.01",
            computed_at="2026-01-02T00:00:00+00:00", observed_at="2026-01-01T00:00:00+00:00",
        )
        result = run_causality_audit((sample,))
        self.assertEqual(result.ordering_violated, 1)
        self.assertFalse(result.passed)
        self.assertTrue(any("does not strictly follow" in v for v in result.violation_details))

    def test_outcome_exactly_equal_to_feature_time_is_violated(self):
        sample = _sample(
            Decimal("0.001"), "0.01",
            computed_at="2026-01-01T00:00:00+00:00", observed_at="2026-01-01T00:00:00+00:00",
        )
        result = run_causality_audit((sample,))
        self.assertEqual(result.ordering_violated, 1)  # strict inequality required, not >=

    def test_missing_observed_at_is_not_verifiable_and_blocks_pass(self):
        sample = _sample(Decimal("0.001"), "0.01")  # no observed_at
        result = run_causality_audit((sample,))
        self.assertEqual(result.ordering_not_verifiable, 1)
        self.assertEqual(result.ordering_violated, 0)
        self.assertFalse(result.passed)  # not-verifiable still blocks a clean pass


class TestOverallPass(unittest.TestCase):
    def test_clean_batch_passes(self):
        samples = (
            _sample(Decimal("0.001"), "0.01", computed_at="2026-01-01T00:00:00+00:00",
                    observed_at="2026-01-02T00:00:00+00:00"),
            _sample(Decimal("-0.002"), "-0.02", computed_at="2026-01-03T00:00:00+00:00",
                    observed_at="2026-01-04T00:00:00+00:00"),
        )
        result = run_causality_audit(samples)
        self.assertTrue(result.passed)
        self.assertEqual(result.violation_details, ())

    def test_determinism_with_fixed_clock(self):
        samples = (
            _sample(Decimal("0.001"), "0.01", computed_at="2026-01-01T00:00:00+00:00",
                    observed_at="2026-01-02T00:00:00+00:00"),
        )
        clock = lambda: "2026-05-01T00:00:00+00:00"
        r1 = run_causality_audit(samples, clock=clock)
        r2 = run_causality_audit(samples, clock=clock)
        self.assertEqual(r1, r2)


class TestEvidencePackageIntegration(unittest.TestCase):
    """Proves the mechanism this milestone exists to demonstrate: a new
    validation technique attaches to an existing EvidencePackage via
    with_stage_result() with ZERO change to EvidencePackage itself."""

    def test_causality_audit_attaches_as_a_second_stage(self):
        spec = funding_rate_candidate_specification(
            version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
            parameters={"threshold": "0.0005"}, acceptance_criteria={"min_hit_rate": 0.5},
        )
        samples = (
            ValidationSample(
                feature_value=_feature(Decimal("0.0010"), "2026-01-01T00:00:00+00:00"),
                realized_outcome=Decimal("-0.02"), outcome_observed_at_utc="2026-01-02T00:00:00+00:00",
            ),
            ValidationSample(
                feature_value=_feature(Decimal("-0.0010"), "2026-01-03T00:00:00+00:00"),
                realized_outcome=Decimal("0.02"), outcome_observed_at_utc="2026-01-04T00:00:00+00:00",
            ),
        )

        validation_result = run_validation(FundingRateThresholdRuleCandidate.evaluate, spec, samples)
        package = evidence_package_from_validation_result(spec, "single_pass_threshold", validation_result)

        audit_result = run_causality_audit(samples)
        extended = package.with_stage_result("leakage_causality_audit", audit_result.to_dict())

        self.assertEqual(set(extended.validation_results.keys()), {"single_pass_threshold", "leakage_causality_audit"})
        self.assertEqual(
            extended.validation_results["single_pass_threshold"], package.validation_results["single_pass_threshold"]
        )
        self.assertNotEqual(extended.fingerprint, package.fingerprint)
        self.assertTrue(extended.validation_results["leakage_causality_audit"]["passed"])

        reloaded = json.loads(json.dumps(extended.to_dict()))
        self.assertEqual(reloaded, extended.to_dict())


if __name__ == "__main__":
    unittest.main()
