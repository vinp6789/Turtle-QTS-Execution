"""Verification tests for the Evidence Package (Alpha Engine Milestone
4.2).

All feature/outcome data here is SYNTHETIC test fixture data -- see
test_alpha_engine_validation_runner.py's own note; the same applies here.
"""

import json
import unittest
from decimal import Decimal

from exchange_adapter import Symbol

from alpha_engine.candidates import (
    CandidateSpecification,
    FundingRateThresholdRuleCandidate,
    funding_rate_candidate_specification,
)
from alpha_engine.features import FeatureValue, FundingRateFeature
from alpha_engine.validation import (
    EvidencePackage,
    ValidationError,
    ValidationSample,
    evidence_package_from_validation_result,
    run_validation,
)


def _spec(threshold="0.0005"):
    return funding_rate_candidate_specification(
        version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
        parameters={"threshold": threshold},
        acceptance_criteria={"min_hit_rate": 0.5},
    )


def _feature(value):
    return FeatureValue(
        feature_name="funding_rate_raw", feature_version="v1", symbol=Symbol("BTC"),
        computed_at_utc="2026-01-01T00:00:00+00:00", available=True, value=value,
    )


def _validation_result(spec, clock=lambda: "2026-01-02T00:00:00+00:00"):
    samples = (
        ValidationSample(feature_value=_feature(Decimal("0.0010")), realized_outcome=Decimal("-0.02")),
        ValidationSample(feature_value=_feature(Decimal("-0.0010")), realized_outcome=Decimal("0.02")),
    )
    return run_validation(FundingRateThresholdRuleCandidate.evaluate, spec, samples, clock=clock)


class TestEvidencePackageValidation(unittest.TestCase):
    def _valid_kwargs(self, **overrides):
        kwargs = dict(
            candidate_name="x", candidate_version="v1",
            candidate_specification={"a": 1},
            validation_results={"stage_1": {"metric": 1}},
            known_limitations=(),
            assembled_at_utc="2026-01-01T00:00:00+00:00",
            fingerprint="abc123",
        )
        kwargs.update(overrides)
        return kwargs

    def test_valid_package_constructs(self):
        EvidencePackage(**self._valid_kwargs())

    def test_blank_candidate_name_raises(self):
        with self.assertRaises(ValidationError):
            EvidencePackage(**self._valid_kwargs(candidate_name=" "))

    def test_blank_candidate_version_raises(self):
        with self.assertRaises(ValidationError):
            EvidencePackage(**self._valid_kwargs(candidate_version=""))

    def test_non_mapping_candidate_specification_raises(self):
        with self.assertRaises(ValidationError):
            EvidencePackage(**self._valid_kwargs(candidate_specification=["a", 1]))

    def test_empty_candidate_specification_raises(self):
        with self.assertRaises(ValidationError):
            EvidencePackage(**self._valid_kwargs(candidate_specification={}))

    def test_non_json_native_candidate_specification_raises(self):
        with self.assertRaises(ValidationError):
            EvidencePackage(**self._valid_kwargs(candidate_specification={"a": Decimal("1")}))

    def test_non_mapping_validation_results_raises(self):
        with self.assertRaises(ValidationError):
            EvidencePackage(**self._valid_kwargs(validation_results=["stage_1"]))

    def test_empty_validation_results_raises(self):
        with self.assertRaises(ValidationError):
            EvidencePackage(**self._valid_kwargs(validation_results={}))

    def test_validation_results_stage_value_not_a_mapping_raises(self):
        with self.assertRaises(ValidationError):
            EvidencePackage(**self._valid_kwargs(validation_results={"stage_1": "not-a-mapping"}))

    def test_validation_results_non_json_native_stage_raises(self):
        with self.assertRaises(ValidationError):
            EvidencePackage(**self._valid_kwargs(validation_results={"stage_1": {"a": Decimal("1")}}))

    def test_validation_results_empty_stage_raises(self):
        with self.assertRaises(ValidationError):
            EvidencePackage(**self._valid_kwargs(validation_results={"stage_1": {}}))

    def test_known_limitations_non_tuple_raises(self):
        with self.assertRaises(ValidationError):
            EvidencePackage(**self._valid_kwargs(known_limitations=["a caveat"]))

    def test_known_limitations_blank_entry_raises(self):
        with self.assertRaises(ValidationError):
            EvidencePackage(**self._valid_kwargs(known_limitations=("  ",)))

    def test_known_limitations_empty_tuple_is_allowed(self):
        EvidencePackage(**self._valid_kwargs(known_limitations=()))

    def test_blank_assembled_at_utc_raises(self):
        with self.assertRaises(ValidationError):
            EvidencePackage(**self._valid_kwargs(assembled_at_utc=""))

    def test_blank_fingerprint_raises(self):
        with self.assertRaises(ValidationError):
            EvidencePackage(**self._valid_kwargs(fingerprint=""))


class TestEvidencePackageImmutability(unittest.TestCase):
    def test_cannot_reassign_a_field(self):
        package = evidence_package_from_validation_result(_spec(), "single_pass", _validation_result(_spec()))
        with self.assertRaises(Exception):
            package.candidate_name = "y"

    def test_candidate_specification_is_read_only(self):
        package = evidence_package_from_validation_result(_spec(), "single_pass", _validation_result(_spec()))
        with self.assertRaises(TypeError):
            package.candidate_specification["new_key"] = 1

    def test_validation_results_outer_mapping_is_read_only(self):
        package = evidence_package_from_validation_result(_spec(), "single_pass", _validation_result(_spec()))
        with self.assertRaises(TypeError):
            package.validation_results["new_stage"] = {}

    def test_validation_results_inner_mapping_is_read_only(self):
        package = evidence_package_from_validation_result(_spec(), "single_pass", _validation_result(_spec()))
        with self.assertRaises(TypeError):
            package.validation_results["single_pass"]["new_key"] = 1


class TestToDict(unittest.TestCase):
    def test_shape_and_json_serializable(self):
        spec = _spec()
        result = _validation_result(spec)
        package = evidence_package_from_validation_result(spec, "single_pass", result)
        d = package.to_dict()
        self.assertEqual(d["candidate_name"], "funding_rate_threshold_rule")
        self.assertEqual(d["candidate_version"], "v1")
        self.assertIn("single_pass", d["validation_results"])
        self.assertEqual(d["known_limitations"], [])
        json.dumps(d)  # must not raise

    def test_known_limitations_included(self):
        spec = _spec()
        package = evidence_package_from_validation_result(
            spec, "single_pass", _validation_result(spec),
            known_limitations=("only 2 synthetic samples", "not real market data"),
        )
        self.assertEqual(
            package.to_dict()["known_limitations"],
            ["only 2 synthetic samples", "not real market data"],
        )


class TestFactoryValidation(unittest.TestCase):
    def test_rejects_non_specification(self):
        with self.assertRaises(ValidationError):
            evidence_package_from_validation_result("not-a-spec", "single_pass", _validation_result(_spec()))

    def test_rejects_blank_stage_name(self):
        with self.assertRaises(ValidationError):
            evidence_package_from_validation_result(_spec(), " ", _validation_result(_spec()))

    def test_rejects_non_validation_result(self):
        with self.assertRaises(ValidationError):
            evidence_package_from_validation_result(_spec(), "single_pass", "not-a-validation-result")

    def test_candidate_name_version_match_specification(self):
        spec = _spec()
        package = evidence_package_from_validation_result(spec, "single_pass", _validation_result(spec))
        self.assertEqual(package.candidate_name, spec.name)
        self.assertEqual(package.candidate_version, spec.version)

    def test_stage_name_used_as_the_validation_results_key(self):
        spec = _spec()
        package = evidence_package_from_validation_result(spec, "my_custom_stage", _validation_result(spec))
        self.assertEqual(set(package.validation_results.keys()), {"my_custom_stage"})


class TestFingerprintDeterminism(unittest.TestCase):
    def test_identical_inputs_produce_identical_fingerprint(self):
        spec = _spec()
        result = _validation_result(spec)
        p1 = evidence_package_from_validation_result(spec, "single_pass", result, clock=lambda: "t")
        p2 = evidence_package_from_validation_result(spec, "single_pass", result, clock=lambda: "t")
        self.assertEqual(p1.fingerprint, p2.fingerprint)
        self.assertEqual(p1, p2)

    def test_different_validation_result_produces_different_fingerprint(self):
        spec = _spec()
        result_a = _validation_result(spec)
        different_samples = (
            ValidationSample(feature_value=_feature(Decimal("0.0010")), realized_outcome=Decimal("0.05")),
        )
        result_b = run_validation(FundingRateThresholdRuleCandidate.evaluate, spec, different_samples)
        p1 = evidence_package_from_validation_result(spec, "single_pass", result_a)
        p2 = evidence_package_from_validation_result(spec, "single_pass", result_b)
        self.assertNotEqual(p1.fingerprint, p2.fingerprint)

    def test_different_specification_produces_different_fingerprint(self):
        spec_a = _spec(threshold="0.0005")
        spec_b = _spec(threshold="0.0009")
        p1 = evidence_package_from_validation_result(spec_a, "single_pass", _validation_result(spec_a))
        p2 = evidence_package_from_validation_result(spec_b, "single_pass", _validation_result(spec_b))
        self.assertNotEqual(p1.fingerprint, p2.fingerprint)


class TestWithStageResult(unittest.TestCase):
    def test_adds_a_new_stage_without_mutating_the_original(self):
        spec = _spec()
        original = evidence_package_from_validation_result(spec, "single_pass", _validation_result(spec))
        extended = original.with_stage_result("walk_forward", {"folds": 5, "pass": True})

        self.assertEqual(set(original.validation_results.keys()), {"single_pass"})  # unchanged
        self.assertEqual(set(extended.validation_results.keys()), {"single_pass", "walk_forward"})

    def test_extended_package_fingerprint_differs_from_original(self):
        spec = _spec()
        original = evidence_package_from_validation_result(spec, "single_pass", _validation_result(spec))
        extended = original.with_stage_result("walk_forward", {"folds": 5})
        self.assertNotEqual(original.fingerprint, extended.fingerprint)

    def test_extended_package_assembled_at_utc_uses_provided_clock(self):
        spec = _spec()
        original = evidence_package_from_validation_result(spec, "single_pass", _validation_result(spec))
        extended = original.with_stage_result("walk_forward", {"folds": 5}, clock=lambda: "2099-01-01T00:00:00+00:00")
        self.assertEqual(extended.assembled_at_utc, "2099-01-01T00:00:00+00:00")

    def test_refuses_to_overwrite_an_existing_stage(self):
        spec = _spec()
        original = evidence_package_from_validation_result(spec, "single_pass", _validation_result(spec))
        with self.assertRaises(ValidationError):
            original.with_stage_result("single_pass", {"anything": 1})

    def test_rejects_blank_stage_name(self):
        spec = _spec()
        original = evidence_package_from_validation_result(spec, "single_pass", _validation_result(spec))
        with self.assertRaises(ValidationError):
            original.with_stage_result(" ", {"folds": 5})

    def test_rejects_non_json_native_stage_result(self):
        spec = _spec()
        original = evidence_package_from_validation_result(spec, "single_pass", _validation_result(spec))
        with self.assertRaises(ValidationError):
            original.with_stage_result("walk_forward", {"threshold": Decimal("1")})

    def test_extended_package_retains_original_stage_content(self):
        spec = _spec()
        original = evidence_package_from_validation_result(spec, "single_pass", _validation_result(spec))
        extended = original.with_stage_result("walk_forward", {"folds": 5})
        self.assertEqual(
            extended.validation_results["single_pass"], original.validation_results["single_pass"]
        )

    def test_chained_extension_accumulates_multiple_stages(self):
        spec = _spec()
        p = evidence_package_from_validation_result(spec, "single_pass", _validation_result(spec))
        p = p.with_stage_result("walk_forward", {"folds": 5})
        p = p.with_stage_result("monte_carlo", {"n_resamples": 1000})
        self.assertEqual(set(p.validation_results.keys()), {"single_pass", "walk_forward", "monte_carlo"})


class TestEndToEndResearchLoop(unittest.TestCase):
    """Closes the requested lifecycle: Funding Provider (shape) -> Funding
    Feature -> Candidate -> Validation -> Evidence Package."""

    def test_full_chain_produces_a_serializable_evidence_package(self):
        from alpha_engine.data_sources import FundingRateReading

        readings = [
            FundingRateReading(symbol=Symbol("BTC"), fetched_at_utc=f"2026-01-0{i}T00:00:00+00:00",
                                available=True, value=value, observed_at_utc=f"2026-01-0{i}T00:00:00+00:00")
            for i, value in enumerate([Decimal("0.0012"), Decimal("-0.0015"), Decimal("0.0009")], start=1)
        ]
        outcomes = [Decimal("-0.03"), Decimal("0.04"), Decimal("0.01")]
        samples = tuple(
            ValidationSample(feature_value=FundingRateFeature.compute(reading), realized_outcome=outcome)
            for reading, outcome in zip(readings, outcomes)
        )
        spec = funding_rate_candidate_specification(
            version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
            parameters={"threshold": "0.0005"}, acceptance_criteria={"min_hit_rate": 0.5},
        )
        result = run_validation(FundingRateThresholdRuleCandidate.evaluate, spec, samples)
        package = evidence_package_from_validation_result(
            spec, "single_pass_threshold", result,
            known_limitations=("3 synthetic samples, not real market data",),
        )

        self.assertEqual(package.candidate_name, "funding_rate_threshold_rule")
        d = package.to_dict()
        reloaded = json.loads(json.dumps(d))
        self.assertEqual(reloaded, d)  # lossless JSON round-trip


if __name__ == "__main__":
    unittest.main()
