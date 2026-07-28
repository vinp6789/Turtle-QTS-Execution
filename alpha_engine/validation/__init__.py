"""Research Validation (Architecture v0.2 SS6, SS2.1; Alpha Engine
Milestone 4.1: the first, single-pass validation loop; Milestone 4.2: the
immutable Evidence Package that captures its output; Milestone 4.3: the
leakage & causality audit, the first additional stage; Milestone 4.4:
walk-forward validation, the second; Milestone 4.5: bootstrap resampling,
the third; Milestone 4.6: regime stratification, the fourth).

Every stage (run_causality_audit, run_walk_forward_validation,
run_bootstrap_resampling, run_regime_stratified_validation) shares the
same signature shape -- (evaluate_fn, specification, samples, ...) -- and
consumes ONLY the candidate and the sample sequence, never another
stage's output. Validation stages are independent contributors to an
EvidencePackage by construction: nothing in any stage's signature could
even accept another stage's result as input.

Public API:
    run_validation      -- evaluates a candidate's evaluate_fn against a
                           historical sample sequence, checks the result
                           against the specification's own
                           acceptance_criteria, criterion by criterion
    EvaluateFn          -- the plain callable type run_validation()
                           accepts: (FeatureValue, CandidateSpecification)
                           -> CandidateSignal -- not an ABC, not a
                           registry (see runner.py's docstring)
    ValidationSample    -- one historical (feature, realized outcome,
                           optional outcome_observed_at_utc) tuple
    ValidationResult    -- one run_validation() call's outcome;
                           to_dict() produces the JSON-native shape
                           EvidencePackage captures verbatim
    CriterionCheck      -- one declared acceptance-criteria key's
                           measured disposition
    CriterionOutcome    -- PASS / FAIL / NOT_EVALUATED
    EvidencePackage     -- the immutable destination artifact validation
                           outputs accumulate into, one named stage at a
                           time (with_stage_result()) -- the single
                           artifact future validation techniques extend
                           rather than redesign
    evidence_package_from_validation_result -- builds the first
                           EvidencePackage from a CandidateSpecification
                           and today's ValidationResult
    run_causality_audit -- scores a sample batch for duplicate data
                           points and outcome-after-feature ordering
                           violations
    CausalityAuditResult -- one run_causality_audit() call's outcome
    run_walk_forward_validation -- re-scores the same candidate across
                           n_folds chronologically independent periods
                           (see walk_forward.py's docstring on why this
                           means something different for a fixed-
                           parameter rule candidate than for a fitted
                           model)
    WalkForwardResult   -- one run_walk_forward_validation() call's
                           outcome
    run_bootstrap_resampling -- seeded, deterministic resampling of the
                           sample set, reporting the resulting hit-rate
                           distribution (see bootstrap.py's docstring on
                           why attribution and calibration -- the other
                           two techniques the roadmap groups with
                           bootstrap -- do not yet apply to this
                           candidate)
    BootstrapResult     -- one run_bootstrap_resampling() call's outcome;
                           diagnostic, not gating -- no overall_passed
    run_regime_stratified_validation -- groups samples by an externally
                           supplied ValidationSample.regime_label and
                           scores each regime independently (see
                           regime_stratification.py's docstring on why
                           Monte Carlo and risk-of-ruin -- the other two
                           techniques the roadmap groups with regime
                           stratification -- need portfolio/equity-curve
                           machinery this project has not built yet)
    RegimeStratificationResult -- one run_regime_stratified_validation()
                           call's outcome
    ValidationError     -- this sub-package's error base (also covers
                           EvidencePackage, causality-audit, walk-forward,
                           bootstrap, and regime-stratification
                           construction failures)

Every result type's to_dict() attaches to an EvidencePackage via the
existing with_stage_result() -- no EvidencePackage change has been
needed for any stage added so far, and none is expected for the next.

Deliberately NOT built yet (see models.py's, runner.py's, evidence.py's,
causality_audit.py's, walk_forward.py's, bootstrap.py's, and
regime_stratification.py's docstrings): purge/embargo (not meaningful
without a fitted candidate type), attribution (needs a second, ablatable
feature), calibration (needs a continuous probability output), Monte
Carlo and risk-of-ruin (need portfolio/equity-curve machinery -- Milestone
6.2, unbuilt), and any governance/promotion/Registry-sealing logic for an
EvidencePackage. Each is real, named future work layered on once
justified -- not an oversight.
"""

from .bootstrap import BootstrapResult, run_bootstrap_resampling
from .causality_audit import CausalityAuditResult, run_causality_audit
from .errors import ValidationError
from .evidence import EvidencePackage, evidence_package_from_validation_result
from .models import CriterionCheck, CriterionOutcome, ValidationResult, ValidationSample
from .regime_stratification import RegimeStratificationResult, run_regime_stratified_validation
from .registry_link import attach_evidence_package
from .runner import EvaluateFn, run_validation
from .walk_forward import WalkForwardResult, run_walk_forward_validation

__all__ = [
    "run_validation",
    "EvaluateFn",
    "ValidationSample",
    "ValidationResult",
    "CriterionCheck",
    "CriterionOutcome",
    "EvidencePackage",
    "evidence_package_from_validation_result",
    "run_causality_audit",
    "CausalityAuditResult",
    "run_walk_forward_validation",
    "WalkForwardResult",
    "run_bootstrap_resampling",
    "BootstrapResult",
    "run_regime_stratified_validation",
    "RegimeStratificationResult",
    "attach_evidence_package",
    "ValidationError",
]
