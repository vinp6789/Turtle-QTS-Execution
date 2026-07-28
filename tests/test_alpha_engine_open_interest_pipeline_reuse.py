"""Proof-of-reuse test for the Open Interest vertical slice (Alpha
Engine Milestone 3.3): the full research pipeline -- run_validation,
run_causality_audit, run_walk_forward_validation, run_bootstrap_
resampling, run_regime_stratified_validation, and EvidencePackage --
consumes an entirely new orthogonal strategy family with ZERO changes to
any of that code. This file exists specifically to demonstrate that,
not merely to assert it in a docstring.

All feature/outcome data is SYNTHETIC test fixture data -- see
test_alpha_engine_validation_runner.py's own note; the same applies here.
"""

import json
import unittest
from decimal import Decimal

from exchange_adapter import Symbol

from alpha_engine.candidates import OpenInterestThresholdRuleCandidate, open_interest_candidate_specification
from alpha_engine.data_sources import OpenInterestReading
from alpha_engine.features import OpenInterestFeature
from alpha_engine.validation import (
    ValidationSample,
    evidence_package_from_validation_result,
    run_bootstrap_resampling,
    run_causality_audit,
    run_regime_stratified_validation,
    run_validation,
    run_walk_forward_validation,
)


def _reading(value, fetched_at, symbol=None):
    return OpenInterestReading(
        symbol=symbol or Symbol("BTC"), fetched_at_utc=fetched_at, available=True,
        value=value, observed_at_utc=fetched_at,
    )


class TestFullPipelineReuse(unittest.TestCase):
    def setUp(self):
        self.spec = open_interest_candidate_specification(
            version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
            parameters={"threshold": "10000", "direction_convention": "contrarian"},
            acceptance_criteria={"min_hit_rate": 0.5},
        )
        readings = [
            _reading(Decimal("50000"), "2026-01-01T00:00:00+00:00"),  # beyond threshold
            _reading(Decimal("5000"), "2026-01-02T00:00:00+00:00"),   # below threshold
            _reading(Decimal("60000"), "2026-01-03T00:00:00+00:00"),  # beyond threshold
            _reading(Decimal("70000"), "2026-01-04T00:00:00+00:00"),  # beyond threshold
        ]
        outcomes = [Decimal("-0.03"), Decimal("0.01"), Decimal("-0.02"), Decimal("0.01")]
        self.samples = tuple(
            ValidationSample(
                feature_value=OpenInterestFeature.compute(reading), realized_outcome=outcome,
                outcome_observed_at_utc=fetched_at_utc_plus_one_day, regime_label="test_regime",
            )
            for reading, outcome, fetched_at_utc_plus_one_day in zip(
                readings, outcomes,
                ["2026-01-02T00:00:00+00:00", "2026-01-03T00:00:00+00:00",
                 "2026-01-04T00:00:00+00:00", "2026-01-05T00:00:00+00:00"],
            )
        )

    def test_run_validation_scores_the_new_candidate_unchanged(self):
        result = run_validation(OpenInterestThresholdRuleCandidate.evaluate, self.spec, self.samples)
        self.assertEqual(result.total_samples, 4)
        self.assertEqual(result.candidate_name, "open_interest_threshold_rule")

    def test_causality_audit_scores_the_new_candidate_unchanged(self):
        result = run_causality_audit(self.samples)
        self.assertEqual(result.total_samples, 4)
        self.assertTrue(result.passed)  # distinct timestamps, all outcomes strictly after

    def test_walk_forward_scores_the_new_candidate_unchanged(self):
        result = run_walk_forward_validation(
            OpenInterestThresholdRuleCandidate.evaluate, self.spec, self.samples, n_folds=2
        )
        self.assertEqual(result.n_folds, 2)
        self.assertEqual(result.candidate_name, "open_interest_threshold_rule")

    def test_bootstrap_resampling_scores_the_new_candidate_unchanged(self):
        result = run_bootstrap_resampling(
            OpenInterestThresholdRuleCandidate.evaluate, self.spec, self.samples, n_resamples=15, seed=3
        )
        self.assertEqual(result.candidate_name, "open_interest_threshold_rule")
        self.assertEqual(result.resample_size, 4)

    def test_regime_stratification_scores_the_new_candidate_unchanged(self):
        result = run_regime_stratified_validation(OpenInterestThresholdRuleCandidate.evaluate, self.spec, self.samples)
        self.assertEqual(result.n_regimes_observed, 1)
        self.assertEqual(result.unstratified_sample_count, 0)

    def test_evidence_package_captures_all_stages_for_the_new_candidate_unchanged(self):
        single_pass = run_validation(OpenInterestThresholdRuleCandidate.evaluate, self.spec, self.samples)
        package = evidence_package_from_validation_result(self.spec, "single_pass_threshold", single_pass)

        causality = run_causality_audit(self.samples)
        package = package.with_stage_result("leakage_causality_audit", causality.to_dict())

        walk_forward = run_walk_forward_validation(
            OpenInterestThresholdRuleCandidate.evaluate, self.spec, self.samples, n_folds=2
        )
        package = package.with_stage_result("walk_forward", walk_forward.to_dict())

        bootstrap = run_bootstrap_resampling(
            OpenInterestThresholdRuleCandidate.evaluate, self.spec, self.samples, n_resamples=10, seed=1
        )
        package = package.with_stage_result("bootstrap_resampling", bootstrap.to_dict())

        regime = run_regime_stratified_validation(OpenInterestThresholdRuleCandidate.evaluate, self.spec, self.samples)
        package = package.with_stage_result("regime_stratification", regime.to_dict())

        self.assertEqual(
            set(package.validation_results.keys()),
            {"single_pass_threshold", "leakage_causality_audit", "walk_forward",
             "bootstrap_resampling", "regime_stratification"},
        )
        self.assertEqual(package.candidate_name, "open_interest_threshold_rule")

        # Lossless JSON round-trip of the fully-assembled package.
        reloaded = json.loads(json.dumps(package.to_dict()))
        self.assertEqual(reloaded, package.to_dict())


if __name__ == "__main__":
    unittest.main()
