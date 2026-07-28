"""Verification tests for the research cycle orchestrator (Alpha Engine
R5). Synthetic fixture data throughout."""

import unittest
from decimal import Decimal

from exchange_adapter import Symbol

from alpha_engine.candidates import funding_rate_candidate_specification, open_interest_candidate_specification
from alpha_engine.features import FeatureValue
from alpha_engine.governance import GovernanceDecision, GovernanceDecisionType, record_governance_decision
from alpha_engine.registry import ExperimentRegistry, LifecycleState, RegistryStorage
from alpha_engine.research import (
    STAGE_BOOTSTRAP,
    STAGE_CAUSALITY,
    STAGE_REGIME,
    STAGE_SINGLE_PASS,
    STAGE_WALK_FORWARD,
    ResearchError,
    compare_experiments,
    run_research_cycle,
)
from alpha_engine.validation import ValidationSample
from alpha_engine.watchlist import Watchlist


class _InMemoryStorage(RegistryStorage):
    def __init__(self):
        self._entries = []

    def append(self, entry):
        self._entries.append(dict(entry))

    def read_all(self):
        return list(self._entries)


_CLOCK = lambda: "2026-07-01T00:00:00+00:00"


def _funding_spec(threshold="0.0005", version="v1"):
    return funding_rate_candidate_specification(
        version=version, universe=(Symbol("BTC"),), cadence_seconds=60,
        parameters={"threshold": threshold}, acceptance_criteria={"min_hit_rate": 0.5},
    )


def _funding_samples(outcomes=("-0.02", "0.02", "-0.03", "-0.01")):
    """Four beyond-threshold (SHORT under contrarian) readings with the
    given outcomes; negative outcome = hit for a SHORT signal."""
    samples = []
    for i, outcome in enumerate(outcomes, start=1):
        samples.append(ValidationSample(
            feature_value=FeatureValue(
                feature_name="funding_rate_raw", feature_version="v1", symbol=Symbol("BTC"),
                computed_at_utc=f"2026-01-{i:02d}T00:00:00+00:00", available=True,
                value=Decimal("0.0010"),
            ),
            realized_outcome=Decimal(outcome),
            outcome_observed_at_utc=f"2026-01-{i + 1:02d}T00:00:00+00:00",
            regime_label="test_regime",
        ))
    return tuple(samples)


def _run(registry, eid="exp-1", spec=None, samples=None, name="funding_rate_threshold_rule"):
    return run_research_cycle(
        registry, name, eid, spec or _funding_spec(), samples or _funding_samples(),
        n_folds=2, n_resamples=10, seed=7, clock=_CLOCK,
        known_limitations=("synthetic fixture data",),
    )


class TestRunResearchCycle(unittest.TestCase):
    def setUp(self):
        self.registry = ExperimentRegistry(_InMemoryStorage())

    def test_full_cycle_lands_in_evidence_sealed_with_all_stages(self):
        result = _run(self.registry)
        self.assertEqual(result.record.lifecycle_state, LifecycleState.EVIDENCE_SEALED)
        self.assertTrue(result.record.sealed)
        self.assertEqual(result.record.evidence_fingerprint, result.package.fingerprint)
        self.assertEqual(
            set(result.package.validation_results.keys()),
            {STAGE_SINGLE_PASS, STAGE_CAUSALITY, STAGE_WALK_FORWARD, STAGE_BOOTSTRAP, STAGE_REGIME},
        )

    def test_stage_passed_summary(self):
        result = _run(self.registry)
        self.assertIsNone(result.stage_passed[STAGE_BOOTSTRAP])  # diagnostic, never gating
        self.assertTrue(result.stage_passed[STAGE_CAUSALITY])
        self.assertIsInstance(result.stage_passed[STAGE_SINGLE_PASS], bool)

    def test_deterministic_fingerprint_across_independent_registries(self):
        r1 = _run(ExperimentRegistry(_InMemoryStorage()))
        r2 = _run(ExperimentRegistry(_InMemoryStorage()))
        self.assertEqual(r1.package.fingerprint, r2.package.fingerprint)
        self.assertEqual(r1.package, r2.package)

    def test_mismatched_catalog_entry_and_specification_refused(self):
        oi_spec = open_interest_candidate_specification(
            version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
            parameters={"threshold": "10000"}, acceptance_criteria={"min_hit_rate": 0.5},
        )
        with self.assertRaises(ResearchError):
            _run(self.registry, spec=oi_spec)  # funding catalog name, OI spec
        # Nothing was registered.
        self.assertEqual(len(self.registry), 0)

    def test_wrong_types_raise(self):
        with self.assertRaises(ResearchError):
            run_research_cycle("not-a-registry", "funding_rate_threshold_rule", "exp-1",
                               _funding_spec(), _funding_samples(), n_folds=2, n_resamples=5, seed=1)
        with self.assertRaises(ResearchError):
            run_research_cycle(self.registry, "funding_rate_threshold_rule", "exp-1",
                               "not-a-spec", _funding_samples(), n_folds=2, n_resamples=5, seed=1)

    def test_no_watchlist_keeps_prior_unconstrained_behavior(self):
        # Backward compatibility: watchlist=None (the default) never
        # enforces anything -- exactly the pre-C4 behavior.
        result = _run(self.registry)
        self.assertEqual(result.record.lifecycle_state, LifecycleState.EVIDENCE_SEALED)

    def test_specification_outside_watchlist_refused(self):
        watchlist = Watchlist(name="core-perps", symbols=(Symbol("ETH"),))
        with self.assertRaises(ResearchError):
            run_research_cycle(
                self.registry, "funding_rate_threshold_rule", "exp-1",
                _funding_spec(), _funding_samples(),  # universe is (Symbol("BTC"),)
                n_folds=2, n_resamples=10, seed=7, clock=_CLOCK, watchlist=watchlist,
            )
        self.assertEqual(len(self.registry), 0)  # nothing registered before the refusal

    def test_specification_inside_watchlist_proceeds(self):
        watchlist = Watchlist(name="core-perps", symbols=(Symbol("BTC"), Symbol("ETH")))
        result = run_research_cycle(
            self.registry, "funding_rate_threshold_rule", "exp-1",
            _funding_spec(), _funding_samples(),
            n_folds=2, n_resamples=10, seed=7, clock=_CLOCK, watchlist=watchlist,
        )
        self.assertEqual(result.record.lifecycle_state, LifecycleState.EVIDENCE_SEALED)

    def test_invalid_watchlist_type_refused(self):
        with self.assertRaises(ResearchError):
            run_research_cycle(
                self.registry, "funding_rate_threshold_rule", "exp-1",
                _funding_spec(), _funding_samples(),
                n_folds=2, n_resamples=10, seed=7, clock=_CLOCK, watchlist="not-a-watchlist",
            )

    def test_open_interest_family_runs_through_the_same_orchestrator(self):
        oi_spec = open_interest_candidate_specification(
            version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
            parameters={"threshold": "10000"}, acceptance_criteria={"min_hit_rate": 0.5},
        )
        samples = tuple(
            ValidationSample(
                feature_value=FeatureValue(
                    feature_name="open_interest_raw", feature_version="v1", symbol=Symbol("BTC"),
                    computed_at_utc=f"2026-02-{i:02d}T00:00:00+00:00", available=True,
                    value=Decimal("50000"),
                ),
                realized_outcome=Decimal(outcome),
                outcome_observed_at_utc=f"2026-02-{i + 1:02d}T00:00:00+00:00",
                regime_label="test_regime",
            )
            for i, outcome in enumerate(("-0.02", "-0.01"), start=1)
        )
        result = run_research_cycle(
            self.registry, "open_interest_threshold_rule", "exp-oi", oi_spec, samples,
            n_folds=2, n_resamples=5, seed=3, clock=_CLOCK,
        )
        self.assertEqual(result.record.lifecycle_state, LifecycleState.EVIDENCE_SEALED)

    def test_cycle_feeds_governance_end_to_end(self):
        result = _run(self.registry)
        self.registry.transition("exp-1", LifecycleState.IN_REVIEW)
        record = record_governance_decision(self.registry, GovernanceDecision(
            experiment_id="exp-1", decision=GovernanceDecisionType.APPROVE,
            evidence_fingerprint=result.package.fingerprint,
            proposed_by="researcher", reviewed_by="reviewer",
            rationale="pre-registered criteria met on synthetic data",
            decided_at_utc=_CLOCK(),
        ))
        self.assertEqual(record.lifecycle_state, LifecycleState.APPROVED)


class TestCompareExperiments(unittest.TestCase):
    def setUp(self):
        self.registry = ExperimentRegistry(_InMemoryStorage())

    def test_passing_experiment_ranks_above_failing_one(self):
        _run(self.registry, eid="exp-pass", samples=_funding_samples(("-0.02", "-0.01", "-0.03", "-0.02")))
        _run(self.registry, eid="exp-fail", spec=_funding_spec(version="v2"),
             samples=_funding_samples(("0.02", "0.01", "0.03", "0.02")))  # all misses
        rows = compare_experiments(self.registry, ("exp-fail", "exp-pass"))
        self.assertEqual(rows[0]["experiment_id"], "exp-pass")
        self.assertEqual(rows[0]["rank"], 1)
        self.assertEqual(rows[1]["experiment_id"], "exp-fail")

    def test_experiment_without_evidence_ranks_last(self):
        _run(self.registry, eid="exp-evidenced")
        self.registry.create("exp-bare", {"a": 1})
        rows = compare_experiments(self.registry, ("exp-bare", "exp-evidenced"))
        self.assertEqual(rows[-1]["experiment_id"], "exp-bare")
        self.assertFalse(rows[-1]["has_evidence"])

    def test_unknown_experiment_raises(self):
        from alpha_engine.registry import ExperimentNotFoundError
        with self.assertRaises(ExperimentNotFoundError):
            compare_experiments(self.registry, ("ghost",))

    def test_empty_ids_raise(self):
        with self.assertRaises(ResearchError):
            compare_experiments(self.registry, ())

    def test_deterministic_output(self):
        _run(self.registry, eid="exp-a")
        _run(self.registry, eid="exp-b", spec=_funding_spec(version="v2"))
        rows_1 = compare_experiments(self.registry, ("exp-a", "exp-b"))
        rows_2 = compare_experiments(self.registry, ("exp-b", "exp-a"))
        self.assertEqual(rows_1, rows_2)


if __name__ == "__main__":
    unittest.main()
