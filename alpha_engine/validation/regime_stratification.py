"""Regime stratification stage (Alpha Engine Milestone 4.6; Architecture
v0.2 SS6.9 "Regime Testing").

Contributes ONE MORE named stage to an EvidencePackage (Milestone 4.2)
via EvidencePackage.with_stage_result() -- zero changes to EvidencePackage
were needed, the fourth stage in a row to confirm this. Consumes the
candidate's evaluate_fn, its CandidateSpecification, and a sample
sequence directly -- exactly like every other stage
(run_validation, run_causality_audit, run_walk_forward_validation,
run_bootstrap_resampling) -- and depends on none of their outputs.
Validation stages remain independent contributors to the Evidence
Package by construction, not by convention: nothing in this module's
signature could even accept another stage's result.

WHY MONTE CARLO AND RISK-OF-RUIN ARE NOT BUILT IN THIS MILESTONE (the
roadmap groups "Monte Carlo, risk-of-ruin, regime stratification"
together): both require a PORTFOLIO EQUITY CURVE -- compounding capital
across trades, position sizing, drawdown tracking -- to mean anything.
Research's run_monte_carlo_robustness resamples the trade set and
recomputes portfolio metrics (CAGR, Sharpe, max drawdown, minimum equity
fraction reached); compute_risk_of_ruin then reads the fraction of those
resampled equity paths that ever breach a ruin_threshold. Nothing in the
Alpha Engine performs capital compounding or sizing yet -- Portfolio
Construction (Architecture v0.2 SS4, "signal-agnostic assembly of
approved candidates' outputs into capital allocations") is explicit,
later, unbuilt work (Milestone 6.2 in the approved roadmap). Building a
stand-in equity-curve model now, ahead of that milestone's real design,
would almost certainly need to be redesigned once Portfolio Construction
actually exists -- exactly the outcome "extend the Evidence Package
without redesigning it" is meant to prevent. Regime stratification needs
no such machinery: it groups already-scored samples by an externally
supplied label and re-applies the same per-sample metric this whole
package already trusts. Monte Carlo and risk-of-ruin remain real, named
future work for once Portfolio Construction exists.

WHY REGIME LABELS ARE A PLAIN, OPAQUE, CALLER-SUPPLIED STRING: this
system has no regime-detection mechanism of its own (no historical
windowing anywhere in alpha_engine.features, unchanged since Milestone
2.1). Rather than fabricate one (e.g. guessing a BTC-trend proxy from a
single point-in-time reading), ValidationSample.regime_label (Milestone
4.6, additive) accepts whatever taxonomy a caller has independently
derived -- this module does not know or care what "risk_on" or "regime_3"
means, only that samples sharing a label belong to the same regime.
Exactly the same "this layer stays ignorant of the next layer's
semantics" discipline used for CandidateSpecification.parameters and the
registry's own opaque specification.

A sample with no regime_label is not silently dropped or silently
assumed representative of some regime -- it is counted as
unstratified_sample_count and, like every other "could not be verified"
condition in this package (an unrecognized acceptance-criteria key in
run_validation, a missing outcome_observed_at_utc in run_causality_audit),
blocks a clean overall_passed. Supplying real regime labels is the only
way to earn a passing regime-stratification result, not an optional
nicety silently assumed fine.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Callable, Dict, List, Mapping, Tuple

from ..candidates import CandidateSpecification
from .errors import ValidationError
from .models import ValidationResult, ValidationSample
from .runner import EvaluateFn, run_validation


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class RegimeStratificationResult:
    """One run_regime_stratified_validation() call's outcome. to_dict()
    nests each regime's own ValidationResult.to_dict() verbatim, keyed
    by regime label, sorted for a canonical/deterministic
    representation -- no information is summarized away."""

    candidate_name: str
    candidate_version: str
    regime_results: Mapping[str, ValidationResult]
    n_regimes_observed: int
    unstratified_sample_count: int
    validated_at_utc: str
    overall_passed: bool

    def __post_init__(self):
        if not isinstance(self.candidate_name, str) or not self.candidate_name.strip():
            raise ValidationError("RegimeStratificationResult.candidate_name must be a non-empty string")
        if not isinstance(self.candidate_version, str) or not self.candidate_version.strip():
            raise ValidationError("RegimeStratificationResult.candidate_version must be a non-empty string")
        if not isinstance(self.regime_results, Mapping):
            raise ValidationError("RegimeStratificationResult.regime_results must be a Mapping")
        for label, result in self.regime_results.items():
            if not isinstance(label, str) or not label.strip():
                raise ValidationError("RegimeStratificationResult.regime_results keys must be non-empty strings")
            if not isinstance(result, ValidationResult):
                raise ValidationError(
                    "RegimeStratificationResult.regime_results values must be ValidationResult instances"
                )
        if not isinstance(self.n_regimes_observed, int) or isinstance(self.n_regimes_observed, bool) \
                or self.n_regimes_observed < 0:
            raise ValidationError("RegimeStratificationResult.n_regimes_observed must be a non-negative int")
        if self.n_regimes_observed != len(self.regime_results):
            raise ValidationError(
                "RegimeStratificationResult.n_regimes_observed must equal len(regime_results)"
            )
        if not isinstance(self.unstratified_sample_count, int) or isinstance(self.unstratified_sample_count, bool) \
                or self.unstratified_sample_count < 0:
            raise ValidationError("RegimeStratificationResult.unstratified_sample_count must be a non-negative int")
        if not isinstance(self.validated_at_utc, str) or not self.validated_at_utc.strip():
            raise ValidationError("RegimeStratificationResult.validated_at_utc must be a non-empty string")
        if not isinstance(self.overall_passed, bool):
            raise ValidationError("RegimeStratificationResult.overall_passed must be a bool")
        expected_overall = (
            self.unstratified_sample_count == 0
            and self.n_regimes_observed >= 1
            and all(r.overall_passed for r in self.regime_results.values())
        )
        if self.overall_passed != expected_overall:
            raise ValidationError(
                "RegimeStratificationResult.overall_passed must be True iff there are zero unstratified "
                "samples, at least one regime was observed, and every regime's own ValidationResult passed"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_name": self.candidate_name,
            "candidate_version": self.candidate_version,
            "regime_results": {
                label: self.regime_results[label].to_dict() for label in sorted(self.regime_results)
            },
            "n_regimes_observed": self.n_regimes_observed,
            "unstratified_sample_count": self.unstratified_sample_count,
            "validated_at_utc": self.validated_at_utc,
            "overall_passed": self.overall_passed,
        }


def run_regime_stratified_validation(
    evaluate_fn: EvaluateFn,
    specification: CandidateSpecification,
    samples: Tuple[ValidationSample, ...],
    clock: Callable[[], str] = _now,
) -> RegimeStratificationResult:
    """Groups samples by ValidationSample.regime_label and scores each
    group with the same run_validation() every other stage uses.
    overall_passed is True only if every sample carries a regime_label
    (zero unstratified_sample_count), at least one regime was observed,
    and every regime's own ValidationResult.overall_passed is True -- the
    candidate must hold up in every observed regime, not merely on
    average, and "we could not tell" is never silently treated as
    success.

    Raises ValidationError only for a caller error (bad argument shape).
    Never raises merely because a regime failed its own criteria, or
    because samples lack regime labels -- both are normal, evidence-
    bearing outcomes reflected in the result.
    """
    if not callable(evaluate_fn):
        raise ValidationError(f"evaluate_fn must be callable, got {type(evaluate_fn).__name__}")
    if not isinstance(specification, CandidateSpecification):
        raise ValidationError(
            f"specification must be a CandidateSpecification, got {type(specification).__name__}"
        )
    if not isinstance(samples, tuple) or len(samples) == 0:
        raise ValidationError("samples must be a non-empty tuple of ValidationSample")
    if not all(isinstance(s, ValidationSample) for s in samples):
        raise ValidationError("samples must contain only ValidationSample instances")

    grouped: Dict[str, List[ValidationSample]] = {}
    unstratified = 0
    for sample in samples:
        if sample.regime_label is None:
            unstratified += 1
            continue
        grouped.setdefault(sample.regime_label, []).append(sample)

    regime_results = {
        label: run_validation(evaluate_fn, specification, tuple(group_samples), clock=clock)
        for label, group_samples in grouped.items()
    }

    overall_passed = (
        unstratified == 0
        and len(regime_results) >= 1
        and all(r.overall_passed for r in regime_results.values())
    )

    return RegimeStratificationResult(
        candidate_name=specification.name,
        candidate_version=specification.version,
        regime_results=MappingProxyType(regime_results),
        n_regimes_observed=len(regime_results),
        unstratified_sample_count=unstratified,
        validated_at_utc=clock(),
        overall_passed=overall_passed,
    )
