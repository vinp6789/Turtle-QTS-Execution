"""Verification tests for degradation assessment and the freeze/retire
path (Alpha Engine R7). Synthetic fixture data throughout."""

import unittest
from decimal import Decimal

from exchange_adapter import Symbol

from alpha_engine.candidates import FundingRateThresholdRuleCandidate, funding_rate_candidate_specification
from alpha_engine.execution_bridge import load_approved_specifications
from alpha_engine.features import FeatureValue
from alpha_engine.governance import GovernanceDecision, GovernanceDecisionType, record_governance_decision
from alpha_engine.lifecycle import (
    DegradationAssessment,
    DegradationError,
    assess_degradation,
    freeze_degraded,
)
from alpha_engine.registry import (
    ExperimentRegistry,
    IllegalLifecycleTransitionError,
    LifecycleState,
    RegistryStorage,
)
from alpha_engine.validation import ValidationSample, run_validation

_CLOCK = lambda: "2026-08-01T00:00:00+00:00"


class _InMemoryStorage(RegistryStorage):
    def __init__(self):
        self._entries = []

    def append(self, entry):
        self._entries.append(dict(entry))

    def read_all(self):
        return list(self._entries)


def _spec(stop_fraction="0.02"):
    return funding_rate_candidate_specification(
        version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
        parameters={"threshold": "0.0005", "stop_fraction": stop_fraction},
        acceptance_criteria={"min_hit_rate": 0.5},
    )


def _result(spec, outcomes):
    """Beyond-threshold SHORT signals; negative outcome = hit."""
    samples = tuple(
        ValidationSample(
            feature_value=FeatureValue(
                feature_name="funding_rate_raw", feature_version="v1", symbol=Symbol("BTC"),
                computed_at_utc=f"2026-07-{i:02d}T00:00:00+00:00", available=True,
                value=Decimal("0.0010"),
            ),
            realized_outcome=Decimal(outcome),
        )
        for i, outcome in enumerate(outcomes, start=1)
    )
    return run_validation(FundingRateThresholdRuleCandidate.evaluate, spec, samples, clock=_CLOCK)


def _live_registry(spec, eid="exp-1", state=LifecycleState.SHAKEDOWN):
    registry = ExperimentRegistry(_InMemoryStorage())
    registry.create(eid, spec.to_specification_dict())
    registry.seal(eid)
    registry.attach_evidence(eid, {"stage": {"x": 1}}, "fp-1")
    registry.transition(eid, LifecycleState.VALIDATING)
    registry.transition(eid, LifecycleState.EVIDENCE_SEALED)
    registry.transition(eid, LifecycleState.IN_REVIEW)
    record_governance_decision(registry, GovernanceDecision(
        experiment_id=eid, decision=GovernanceDecisionType.APPROVE,
        evidence_fingerprint="fp-1", proposed_by="researcher", reviewed_by="reviewer",
        rationale="ok", decided_at_utc=_CLOCK(),
    ))
    registry.transition(eid, LifecycleState.SHAKEDOWN)
    if state is LifecycleState.FULL_PRODUCTION:
        registry.transition(eid, LifecycleState.FULL_PRODUCTION)
    return registry


class TestAssessDegradation(unittest.TestCase):
    def test_healthy_when_recent_result_passes_its_own_bar(self):
        spec = _spec()
        registry = _live_registry(spec)
        assessment = assess_degradation(registry.get("exp-1"), _result(spec, ("-0.02", "-0.01")), clock=_CLOCK)
        self.assertFalse(assessment.degraded)
        self.assertIsNone(assessment.recommendation)
        self.assertEqual(assessment.reasons, ())

    def test_degraded_when_recent_result_fails_with_reasons(self):
        spec = _spec()
        registry = _live_registry(spec)
        assessment = assess_degradation(registry.get("exp-1"), _result(spec, ("0.02", "0.01")), clock=_CLOCK)
        self.assertTrue(assessment.degraded)
        self.assertEqual(assessment.recommendation, LifecycleState.FROZEN)
        self.assertTrue(any("min_hit_rate" in r for r in assessment.reasons))

    def test_pure_and_deterministic(self):
        spec = _spec()
        registry = _live_registry(spec)
        record = registry.get("exp-1")
        result = _result(spec, ("0.02",))
        self.assertEqual(
            assess_degradation(record, result, clock=_CLOCK),
            assess_degradation(record, result, clock=_CLOCK),
        )

    def test_non_live_state_raises(self):
        spec = _spec()
        registry = ExperimentRegistry(_InMemoryStorage())
        registry.create("exp-1", spec.to_specification_dict())
        with self.assertRaises(DegradationError):
            assess_degradation(registry.get("exp-1"), _result(spec, ("0.02",)))

    def test_mismatched_candidate_raises(self):
        spec = _spec()
        registry = _live_registry(spec)
        other_spec = funding_rate_candidate_specification(
            version="v2", universe=(Symbol("BTC"),), cadence_seconds=60,
            parameters={"threshold": "0.0005"}, acceptance_criteria={"min_hit_rate": 0.5},
        )
        with self.assertRaises(DegradationError):
            assess_degradation(registry.get("exp-1"), _result(other_spec, ("0.02",)))

    def test_works_in_full_production_too(self):
        spec = _spec()
        registry = _live_registry(spec, state=LifecycleState.FULL_PRODUCTION)
        assessment = assess_degradation(registry.get("exp-1"), _result(spec, ("0.02",)), clock=_CLOCK)
        self.assertTrue(assessment.degraded)


class TestFreezeDegraded(unittest.TestCase):
    def test_freeze_applies_the_recommendation_durably(self):
        spec = _spec()
        registry = _live_registry(spec)
        assessment = assess_degradation(registry.get("exp-1"), _result(spec, ("0.02",)), clock=_CLOCK)
        record = freeze_degraded(registry, assessment)
        self.assertEqual(record.lifecycle_state, LifecycleState.FROZEN)

    def test_refuses_a_healthy_assessment(self):
        spec = _spec()
        registry = _live_registry(spec)
        healthy = assess_degradation(registry.get("exp-1"), _result(spec, ("-0.02",)), clock=_CLOCK)
        with self.assertRaises(DegradationError):
            freeze_degraded(registry, healthy)

    def test_stale_assessment_hits_registry_guard(self):
        spec = _spec()
        registry = _live_registry(spec)
        assessment = assess_degradation(registry.get("exp-1"), _result(spec, ("0.02",)), clock=_CLOCK)
        registry.transition("exp-1", LifecycleState.RETIRING)
        registry.transition("exp-1", LifecycleState.RETIRED)
        with self.assertRaises(IllegalLifecycleTransitionError):
            freeze_degraded(registry, assessment)

    def test_frozen_experiment_leaves_the_approved_set_and_can_retire(self):
        spec = _spec()
        registry = _live_registry(spec)
        self.assertEqual(len(load_approved_specifications(registry)), 1)

        assessment = assess_degradation(registry.get("exp-1"), _result(spec, ("0.02",)), clock=_CLOCK)
        freeze_degraded(registry, assessment)
        self.assertEqual(load_approved_specifications(registry), ())  # bridge no longer serves it

        registry.transition("exp-1", LifecycleState.RETIRING)
        record = registry.transition("exp-1", LifecycleState.RETIRED)
        self.assertEqual(record.lifecycle_state, LifecycleState.RETIRED)


class TestAssessmentValidation(unittest.TestCase):
    def test_degraded_must_recommend_frozen_with_reasons(self):
        with self.assertRaises(DegradationError):
            DegradationAssessment(experiment_id="x", degraded=True, recommendation=None,
                                  reasons=("r",), assessed_at_utc="t")
        with self.assertRaises(DegradationError):
            DegradationAssessment(experiment_id="x", degraded=True,
                                  recommendation=LifecycleState.FROZEN, reasons=(),
                                  assessed_at_utc="t")

    def test_healthy_must_carry_nothing(self):
        with self.assertRaises(DegradationError):
            DegradationAssessment(experiment_id="x", degraded=False,
                                  recommendation=LifecycleState.FROZEN, reasons=(),
                                  assessed_at_utc="t")


if __name__ == "__main__":
    unittest.main()
