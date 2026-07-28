"""Verification tests for the first validation loop (Alpha Engine
Milestone 4.1).

All feature/outcome data here is SYNTHETIC test fixture data, constructed
to exercise specific arithmetic paths -- never presented as, or intended
to demonstrate, a real market edge. Whether the funding-rate threshold
rule has genuine predictive value is an empirical question for real
historical data to answer later; these tests only prove the validation
MACHINERY computes correctly and deterministically.
"""

import unittest
from decimal import Decimal

from exchange_adapter import Symbol

from alpha_engine.candidates import (
    CandidateSignal,
    FundingRateThresholdRuleCandidate,
    SignalDirection,
    funding_rate_candidate_specification,
)
from alpha_engine.features import FeatureValue, FundingRateFeature
from alpha_engine.validation import (
    CriterionCheck,
    CriterionOutcome,
    ValidationError,
    ValidationResult,
    ValidationSample,
    run_validation,
)


def _feature(value=Decimal("0.0001"), available=True, reason=None, symbol=None,
             computed_at="2026-01-01T00:00:00+00:00"):
    return FeatureValue(
        feature_name="funding_rate_raw", feature_version="v1", symbol=symbol or Symbol("BTC"),
        computed_at_utc=computed_at, available=available,
        value=value if available else None, reason=reason,
    )


def _spec(threshold="0.0005", direction_convention=None, acceptance_criteria=None):
    parameters = {"threshold": threshold}
    if direction_convention is not None:
        parameters["direction_convention"] = direction_convention
    return funding_rate_candidate_specification(
        version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
        parameters=parameters,
        acceptance_criteria=acceptance_criteria or {"min_hit_rate": 0.5},
    )


def _sample(value, outcome, available=True, reason=None):
    return ValidationSample(
        feature_value=_feature(value=value, available=available, reason=reason),
        realized_outcome=Decimal(outcome),
    )


class TestValidationSampleValidation(unittest.TestCase):
    def test_non_feature_value_raises(self):
        with self.assertRaises(ValidationError):
            ValidationSample(feature_value="not-a-feature-value", realized_outcome=Decimal("1"))

    def test_non_decimal_outcome_raises(self):
        with self.assertRaises(ValidationError):
            ValidationSample(feature_value=_feature(), realized_outcome=1.0)


class TestCriterionCheckValidation(unittest.TestCase):
    def test_blank_key_raises(self):
        with self.assertRaises(ValidationError):
            CriterionCheck(criterion_key=" ", required_value=1, observed_value=None, outcome=CriterionOutcome.PASS)

    def test_not_evaluated_with_observed_value_raises(self):
        with self.assertRaises(ValidationError):
            CriterionCheck(
                criterion_key="x", required_value=1, observed_value="unexpected",
                outcome=CriterionOutcome.NOT_EVALUATED,
            )

    def test_to_dict_shape(self):
        c = CriterionCheck(criterion_key="min_hit_rate", required_value=0.5, observed_value="0.6", outcome=CriterionOutcome.PASS)
        self.assertEqual(
            c.to_dict(),
            {"criterion_key": "min_hit_rate", "required_value": 0.5, "observed_value": "0.6", "outcome": "pass"},
        )


class TestCriterionOutcomeEnum(unittest.TestCase):
    def test_exactly_three_outcomes(self):
        self.assertEqual({o.value for o in CriterionOutcome}, {"pass", "fail", "not_evaluated"})


class TestValidationResultValidation(unittest.TestCase):
    def _valid_kwargs(self, **overrides):
        kwargs = dict(
            candidate_name="x", candidate_version="v1", validated_at_utc="2026-01-01T00:00:00+00:00",
            total_samples=3, unavailable_samples=0, flat_samples=1, signaled_samples=2,
            hits=1, hit_rate=Decimal("0.5"), mean_directional_return=Decimal("0.001"),
            criteria_results=(CriterionCheck("min_hit_rate", 0.5, "0.5", CriterionOutcome.PASS),),
            overall_passed=True,
        )
        kwargs.update(overrides)
        return kwargs

    def test_valid_result_constructs(self):
        ValidationResult(**self._valid_kwargs())

    def test_bucket_mismatch_raises(self):
        with self.assertRaises(ValidationError):
            ValidationResult(**self._valid_kwargs(total_samples=99))

    def test_hits_exceeding_signaled_raises(self):
        with self.assertRaises(ValidationError):
            ValidationResult(**self._valid_kwargs(hits=99))

    def test_zero_signaled_with_hit_rate_set_raises(self):
        with self.assertRaises(ValidationError):
            ValidationResult(**self._valid_kwargs(
                total_samples=1, unavailable_samples=0, flat_samples=1, signaled_samples=0,
                hits=0, hit_rate=Decimal("0"), mean_directional_return=None,
            ))

    def test_positive_signaled_with_hit_rate_none_raises(self):
        with self.assertRaises(ValidationError):
            ValidationResult(**self._valid_kwargs(hit_rate=None))

    def test_empty_criteria_results_raises(self):
        with self.assertRaises(ValidationError):
            ValidationResult(**self._valid_kwargs(criteria_results=()))

    def test_overall_passed_inconsistent_with_criteria_raises(self):
        with self.assertRaises(ValidationError):
            ValidationResult(**self._valid_kwargs(
                criteria_results=(CriterionCheck("min_hit_rate", 0.5, "0.5", CriterionOutcome.FAIL),),
                overall_passed=True,
            ))

    def test_to_dict_shape_and_json_serializable(self):
        import json
        result = ValidationResult(**self._valid_kwargs())
        d = result.to_dict()
        self.assertEqual(d["hit_rate"], "0.5")
        self.assertEqual(d["mean_directional_return"], "0.001")
        self.assertEqual(d["criteria_results"], [{
            "criterion_key": "min_hit_rate", "required_value": 0.5, "observed_value": "0.5", "outcome": "pass",
        }])
        json.dumps(d)  # must not raise

    def test_to_dict_none_metrics_when_no_signaled_samples(self):
        result = ValidationResult(**self._valid_kwargs(
            total_samples=1, unavailable_samples=0, flat_samples=1, signaled_samples=0,
            hits=0, hit_rate=None, mean_directional_return=None,
        ))
        d = result.to_dict()
        self.assertIsNone(d["hit_rate"])
        self.assertIsNone(d["mean_directional_return"])


class TestRunValidationInputValidation(unittest.TestCase):
    def test_non_callable_evaluate_fn_raises(self):
        with self.assertRaises(ValidationError):
            run_validation("not-callable", _spec(), (_sample(Decimal("0.001"), "0.01"),))

    def test_non_specification_raises(self):
        with self.assertRaises(ValidationError):
            run_validation(FundingRateThresholdRuleCandidate.evaluate, "not-a-spec", (_sample(Decimal("0.001"), "0.01"),))

    def test_empty_samples_raises(self):
        with self.assertRaises(ValidationError):
            run_validation(FundingRateThresholdRuleCandidate.evaluate, _spec(), ())

    def test_non_tuple_samples_raises(self):
        with self.assertRaises(ValidationError):
            run_validation(FundingRateThresholdRuleCandidate.evaluate, _spec(), [_sample(Decimal("0.001"), "0.01")])

    def test_non_sample_items_raise(self):
        with self.assertRaises(ValidationError):
            run_validation(FundingRateThresholdRuleCandidate.evaluate, _spec(), ("not-a-sample",))

    def test_evaluate_fn_returning_non_signal_raises(self):
        def _bad_evaluate(feature_value, specification):
            return "not-a-signal"
        with self.assertRaises(ValidationError):
            run_validation(_bad_evaluate, _spec(), (_sample(Decimal("0.001"), "0.01"),))


class TestRunValidationAggregation(unittest.TestCase):
    def test_all_unavailable_samples_yield_zero_signaled(self):
        samples = (
            _sample(Decimal("0"), "0.01", available=False, reason="stale"),
            _sample(Decimal("0"), "-0.01", available=False, reason="stale"),
        )
        result = run_validation(FundingRateThresholdRuleCandidate.evaluate, _spec(), samples)
        self.assertEqual(result.total_samples, 2)
        self.assertEqual(result.unavailable_samples, 2)
        self.assertEqual(result.signaled_samples, 0)
        self.assertIsNone(result.hit_rate)
        self.assertIsNone(result.mean_directional_return)

    def test_all_flat_samples_yield_zero_signaled(self):
        # value within [-threshold, threshold] -> FLAT
        samples = (
            _sample(Decimal("0.0001"), "0.01"),
            _sample(Decimal("-0.0001"), "-0.01"),
        )
        result = run_validation(FundingRateThresholdRuleCandidate.evaluate, _spec(threshold="0.0005"), samples)
        self.assertEqual(result.flat_samples, 2)
        self.assertEqual(result.signaled_samples, 0)
        self.assertIsNone(result.hit_rate)

    def test_correct_long_and_short_signals_count_as_hits(self):
        samples = (
            # contrarian: positive funding beyond threshold -> SHORT; outcome negative -> hit
            _sample(Decimal("0.0010"), "-0.02"),
            # contrarian: negative funding beyond threshold -> LONG; outcome positive -> hit
            _sample(Decimal("-0.0010"), "0.02"),
        )
        result = run_validation(FundingRateThresholdRuleCandidate.evaluate, _spec(threshold="0.0005"), samples)
        self.assertEqual(result.signaled_samples, 2)
        self.assertEqual(result.hits, 2)
        self.assertEqual(result.hit_rate, Decimal("1"))

    def test_incorrect_signals_count_as_misses(self):
        samples = (
            # contrarian: positive funding -> SHORT; outcome positive -> miss
            _sample(Decimal("0.0010"), "0.02"),
            # contrarian: negative funding -> LONG; outcome negative -> miss
            _sample(Decimal("-0.0010"), "-0.02"),
        )
        result = run_validation(FundingRateThresholdRuleCandidate.evaluate, _spec(threshold="0.0005"), samples)
        self.assertEqual(result.hits, 0)
        self.assertEqual(result.hit_rate, Decimal("0"))

    def test_zero_outcome_is_signaled_but_not_a_hit(self):
        samples = (_sample(Decimal("0.0010"), "0"),)  # SHORT signal, outcome exactly 0
        result = run_validation(FundingRateThresholdRuleCandidate.evaluate, _spec(threshold="0.0005"), samples)
        self.assertEqual(result.signaled_samples, 1)
        self.assertEqual(result.hits, 0)

    def test_mean_directional_return_computed_correctly(self):
        samples = (
            _sample(Decimal("0.0010"), "-0.02"),  # SHORT, directional_return = +0.02
            _sample(Decimal("0.0010"), "-0.04"),  # SHORT, directional_return = +0.04
        )
        result = run_validation(FundingRateThresholdRuleCandidate.evaluate, _spec(threshold="0.0005"), samples)
        self.assertEqual(result.mean_directional_return, Decimal("0.03"))  # (0.02+0.04)/2

    def test_mixed_bucket_counts_partition_total(self):
        samples = (
            _sample(Decimal("0.0010"), "-0.02"),                                   # signaled, hit
            _sample(Decimal("0.0001"), "0.01"),                                    # flat
            _sample(Decimal("0"), "0.01", available=False, reason="stale"),        # unavailable
        )
        result = run_validation(FundingRateThresholdRuleCandidate.evaluate, _spec(threshold="0.0005"), samples)
        self.assertEqual(result.total_samples, 3)
        self.assertEqual(result.unavailable_samples, 1)
        self.assertEqual(result.flat_samples, 1)
        self.assertEqual(result.signaled_samples, 1)
        self.assertEqual(result.hits, 1)


class TestRunValidationCriteria(unittest.TestCase):
    def test_min_hit_rate_pass_at_boundary(self):
        samples = (
            _sample(Decimal("0.0010"), "-0.02"),  # hit
            _sample(Decimal("0.0010"), "0.02"),   # miss
        )
        spec = _spec(threshold="0.0005", acceptance_criteria={"min_hit_rate": 0.5})
        result = run_validation(FundingRateThresholdRuleCandidate.evaluate, spec, samples)
        self.assertEqual(result.hit_rate, Decimal("0.5"))
        check = result.criteria_results[0]
        self.assertEqual(check.outcome, CriterionOutcome.PASS)

    def test_min_hit_rate_fail_below_threshold(self):
        samples = (
            _sample(Decimal("0.0010"), "0.02"),  # miss
            _sample(Decimal("0.0010"), "0.02"),  # miss
        )
        spec = _spec(threshold="0.0005", acceptance_criteria={"min_hit_rate": 0.5})
        result = run_validation(FundingRateThresholdRuleCandidate.evaluate, spec, samples)
        self.assertEqual(result.criteria_results[0].outcome, CriterionOutcome.FAIL)
        self.assertFalse(result.overall_passed)

    def test_min_hit_rate_not_evaluated_when_zero_signaled(self):
        samples = (_sample(Decimal("0.0001"), "0.01"),)  # flat
        spec = _spec(threshold="0.0005", acceptance_criteria={"min_hit_rate": 0.5})
        result = run_validation(FundingRateThresholdRuleCandidate.evaluate, spec, samples)
        self.assertEqual(result.criteria_results[0].outcome, CriterionOutcome.NOT_EVALUATED)
        self.assertFalse(result.overall_passed)

    def test_min_hit_rate_malformed_value_raises(self):
        spec = _spec(threshold="0.0005", acceptance_criteria={"min_hit_rate": "not-a-number"})
        with self.assertRaises(ValidationError):
            run_validation(FundingRateThresholdRuleCandidate.evaluate, spec, (_sample(Decimal("0.0010"), "0.02"),))

    def test_min_hit_rate_out_of_range_raises(self):
        spec = _spec(threshold="0.0005", acceptance_criteria={"min_hit_rate": 1.5})
        with self.assertRaises(ValidationError):
            run_validation(FundingRateThresholdRuleCandidate.evaluate, spec, (_sample(Decimal("0.0010"), "0.02"),))

    def test_min_signaled_samples_pass_at_boundary(self):
        samples = (_sample(Decimal("0.0010"), "0.02"),)
        spec = _spec(threshold="0.0005", acceptance_criteria={"min_signaled_samples": 1})
        result = run_validation(FundingRateThresholdRuleCandidate.evaluate, spec, samples)
        self.assertEqual(result.criteria_results[0].outcome, CriterionOutcome.PASS)

    def test_min_signaled_samples_fail(self):
        samples = (_sample(Decimal("0.0001"), "0.01"),)  # flat -> 0 signaled
        spec = _spec(threshold="0.0005", acceptance_criteria={"min_signaled_samples": 1})
        result = run_validation(FundingRateThresholdRuleCandidate.evaluate, spec, samples)
        self.assertEqual(result.criteria_results[0].outcome, CriterionOutcome.FAIL)

    def test_min_signaled_samples_malformed_raises(self):
        spec = _spec(threshold="0.0005", acceptance_criteria={"min_signaled_samples": "one"})
        with self.assertRaises(ValidationError):
            run_validation(FundingRateThresholdRuleCandidate.evaluate, spec, (_sample(Decimal("0.0010"), "0.02"),))

    def test_min_signaled_samples_negative_raises(self):
        spec = _spec(threshold="0.0005", acceptance_criteria={"min_signaled_samples": -1})
        with self.assertRaises(ValidationError):
            run_validation(FundingRateThresholdRuleCandidate.evaluate, spec, (_sample(Decimal("0.0010"), "0.02"),))

    def test_unrecognized_criterion_key_is_not_evaluated_and_blocks_overall_pass(self):
        samples = (_sample(Decimal("0.0010"), "-0.02"),)  # would otherwise be a clean hit
        spec = _spec(threshold="0.0005", acceptance_criteria={"min_hit_rate": 0.5, "min_sharpe": 1.0})
        result = run_validation(FundingRateThresholdRuleCandidate.evaluate, spec, samples)
        outcomes = {c.criterion_key: c.outcome for c in result.criteria_results}
        self.assertEqual(outcomes["min_hit_rate"], CriterionOutcome.PASS)
        self.assertEqual(outcomes["min_sharpe"], CriterionOutcome.NOT_EVALUATED)
        self.assertFalse(result.overall_passed)  # NOT_EVALUATED blocks overall pass

    def test_overall_passed_true_only_when_all_criteria_pass(self):
        samples = (
            _sample(Decimal("0.0010"), "-0.02"),
            _sample(Decimal("-0.0010"), "0.02"),
        )
        spec = _spec(
            threshold="0.0005",
            acceptance_criteria={"min_hit_rate": 0.5, "min_signaled_samples": 2},
        )
        result = run_validation(FundingRateThresholdRuleCandidate.evaluate, spec, samples)
        self.assertTrue(result.overall_passed)


class TestRunValidationDeterminism(unittest.TestCase):
    def test_identical_inputs_yield_identical_result_with_fixed_clock(self):
        samples = (
            _sample(Decimal("0.0010"), "-0.02"),
            _sample(Decimal("0.0001"), "0.01"),
        )
        spec = _spec(threshold="0.0005")
        clock = lambda: "2026-05-01T00:00:00+00:00"
        r1 = run_validation(FundingRateThresholdRuleCandidate.evaluate, spec, samples, clock=clock)
        r2 = run_validation(FundingRateThresholdRuleCandidate.evaluate, spec, samples, clock=clock)
        self.assertEqual(r1, r2)


class TestEndToEndResearchLoop(unittest.TestCase):
    """The complete chain this milestone's objective names: a raw
    FundingRateReading-shaped FeatureValue computed via FundingRateFeature
    (Milestone 2.1), evaluated by the rule candidate (Milestone 3.2)
    against a specification (Milestone 3.1), scored by run_validation
    (Milestone 4.1), producing output ready to seal into a future
    Evidence Package (to_dict(), JSON-serializable)."""

    def test_full_chain_from_feature_computation_through_validation(self):
        import json
        from alpha_engine.data_sources import FundingRateReading

        # Synthetic historical readings -- NOT real market data.
        readings = [
            FundingRateReading(symbol=Symbol("BTC"), fetched_at_utc=f"2026-01-0{i}T00:00:00+00:00",
                                available=True, value=value, observed_at_utc=f"2026-01-0{i}T00:00:00+00:00")
            for i, value in enumerate(
                [Decimal("0.0012"), Decimal("-0.0015"), Decimal("0.0001"), Decimal("0.0009")], start=1
            )
        ]
        realized_outcomes = [Decimal("-0.03"), Decimal("0.04"), Decimal("0.00"), Decimal("0.01")]

        feature_values = [FundingRateFeature.compute(r) for r in readings]
        samples = tuple(
            ValidationSample(feature_value=fv, realized_outcome=outcome)
            for fv, outcome in zip(feature_values, realized_outcomes)
        )

        spec = funding_rate_candidate_specification(
            version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
            parameters={"threshold": "0.0005", "direction_convention": "contrarian"},
            acceptance_criteria={"min_hit_rate": 0.5, "min_signaled_samples": 2},
        )

        result = run_validation(FundingRateThresholdRuleCandidate.evaluate, spec, samples)

        self.assertEqual(result.total_samples, 4)
        self.assertEqual(result.candidate_name, "funding_rate_threshold_rule")
        d = result.to_dict()
        json.dumps(d)  # ready to be sealed / stored -- must not raise


if __name__ == "__main__":
    unittest.main()
