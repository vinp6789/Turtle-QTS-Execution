"""Walk-forward validation stage (Alpha Engine Milestone 4.4;
Architecture v0.2 SS6.3 "Walk-Forward Validation").

Contributes ONE MORE named stage to an EvidencePackage (Milestone 4.2)
via EvidencePackage.with_stage_result() -- zero changes to EvidencePackage
were needed, exactly as Milestone 4.3's causality audit already
demonstrated.

WHY WALK-FORWARD MEANS SOMETHING DIFFERENT HERE THAN IN THE RESEARCH
REPOSITORY: the Research repo's walk-forward folds exist to guard
against OVERFITTING -- each fold trains a NEW model on a growing window
and tests it on unseen data, so a result cannot be an artifact of
fitting to the whole sample. FundingRateThresholdRuleCandidate
(Milestone 3.2) has no fitting step at all: its threshold and
direction_convention are fixed, pre-registered parameters
(CandidateSpecification.parameters, Milestone 3.1), not coefficients
estimated from data. There is nothing to overfit.

What walk-forward is HONESTLY still good for here is the OTHER stated
purpose Research's own documentation gives it: "a single backtest window
can produce a result that is a lucky (or unlucky) property of that
specific period." That risk is identical for a fixed-rule candidate.
This stage therefore: sorts samples chronologically, splits them into
n_folds contiguous, non-overlapping periods, and re-applies the SAME
run_validation() (Milestone 4.1) to each fold independently -- checking
whether the candidate clears its OWN pre-registered acceptance_criteria
in EVERY period, not just in aggregate. No new metric-computation logic
is duplicated; each fold's ValidationResult comes from the exact same
scoring function every other stage already trusts.

WHY PURGE/EMBARGO IS NOT IMPLEMENTED HERE: purge (removing training
samples whose label window overlaps a test fold) and embargo (a gap
after each test period before training resumes) exist specifically to
stop information leaking from a TRAINING set into a TEST set that is
adjacent to it in time. There is no training set here -- folds are
independently scored against the same fixed rule, not used to fit
anything -- so there is no leakage vector for purge/embargo to close.
This becomes meaningful again the moment a FITTED (statistical,
optimization, or ensemble) candidate type exists; implementing it now,
against a rule with nothing to fit, would be exactly the kind of
premature abstraction this project has consistently avoided introducing
ahead of a real need.

fold-count and consistency reporting: hit_rate_range (the spread between
the best- and worst-performing fold's hit rate) is reported as
INFORMATION, not gated against an invented pass/fail threshold -- there
is no principled default for "how much fold-to-fold variation is too
much" without real historical calibration data this system does not yet
have, and manufacturing one now would itself be a fabricated criterion.
Judging that number is left to governance review (Milestone 5.x), where
a human looks at fold_results directly; overall_passed here reflects
only what IS honestly checkable: did every fold clear its own
pre-registered bar.

Long-term architectural constraints this design keeps open (not
implemented now, per project direction): evaluate_fn stays a plain,
candidate-agnostic callable (Milestone 3.2's shape) so any future
strategy -- not just this one -- validates through this same fold
mechanism; nothing here assumes a single hard-coded candidate, a single
symbol, or scans anything beyond the samples it is given.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple

from .._time import parse_utc
from ..candidates import CandidateSpecification
from .errors import ValidationError
from .models import ValidationResult, ValidationSample, fingerprint_samples
from .runner import EvaluateFn, run_validation

_logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fold_boundaries(n_samples: int, n_folds: int) -> List[Tuple[int, int]]:
    """Contiguous, near-equal, non-overlapping index ranges. The first
    (n_samples % n_folds) folds get one extra sample so every fold's size
    differs by at most one -- deterministic given n_samples/n_folds
    alone."""
    base_size, remainder = divmod(n_samples, n_folds)
    boundaries = []
    start = 0
    for i in range(n_folds):
        size = base_size + (1 if i < remainder else 0)
        boundaries.append((start, start + size))
        start += size
    return boundaries


@dataclass(frozen=True)
class WalkForwardResult:
    """One run_walk_forward_validation() call's outcome. to_dict()
    produces the JSON-native shape EvidencePackage.with_stage_result()
    expects, nesting each fold's own ValidationResult.to_dict()
    verbatim -- no information is summarized away."""

    candidate_name: str
    candidate_version: str
    n_folds: int
    fold_results: Tuple[ValidationResult, ...]
    hit_rate_range: Optional[Decimal]
    validated_at_utc: str
    overall_passed: bool
    sample_set_fingerprint: Optional[str] = None  # B1 (additive)

    def __post_init__(self):
        if not isinstance(self.candidate_name, str) or not self.candidate_name.strip():
            raise ValidationError("WalkForwardResult.candidate_name must be a non-empty string")
        if not isinstance(self.candidate_version, str) or not self.candidate_version.strip():
            raise ValidationError("WalkForwardResult.candidate_version must be a non-empty string")
        if not isinstance(self.n_folds, int) or isinstance(self.n_folds, bool) or self.n_folds <= 0:
            raise ValidationError("WalkForwardResult.n_folds must be a positive int")
        if not isinstance(self.fold_results, tuple) or len(self.fold_results) != self.n_folds:
            raise ValidationError("WalkForwardResult.fold_results must be a tuple of length n_folds")
        if not all(isinstance(f, ValidationResult) for f in self.fold_results):
            raise ValidationError("WalkForwardResult.fold_results must contain only ValidationResult instances")
        if self.hit_rate_range is not None and not isinstance(self.hit_rate_range, Decimal):
            raise ValidationError("WalkForwardResult.hit_rate_range must be a Decimal or None")
        if not isinstance(self.validated_at_utc, str) or not self.validated_at_utc.strip():
            raise ValidationError("WalkForwardResult.validated_at_utc must be a non-empty string")
        if not isinstance(self.overall_passed, bool):
            raise ValidationError("WalkForwardResult.overall_passed must be a bool")
        expected_overall = all(f.overall_passed for f in self.fold_results)
        if self.overall_passed != expected_overall:
            raise ValidationError(
                "WalkForwardResult.overall_passed must equal all(fold.overall_passed for fold in fold_results)"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_name": self.candidate_name,
            "candidate_version": self.candidate_version,
            "n_folds": self.n_folds,
            "fold_results": [f.to_dict() for f in self.fold_results],
            "hit_rate_range": str(self.hit_rate_range) if self.hit_rate_range is not None else None,
            "validated_at_utc": self.validated_at_utc,
            "overall_passed": self.overall_passed,
            "sample_set_fingerprint": self.sample_set_fingerprint,
        }


def run_walk_forward_validation(
    evaluate_fn: EvaluateFn,
    specification: CandidateSpecification,
    samples: Tuple[ValidationSample, ...],
    n_folds: int,
    clock: Callable[[], str] = _now,
) -> WalkForwardResult:
    """Sorts samples by feature_value.computed_at_utc (stable, ascending
    -- callers need not pre-sort), splits them into n_folds contiguous
    periods, and scores each fold with the same run_validation() every
    other stage uses. overall_passed is True only if every fold's own
    ValidationResult.overall_passed is True -- the candidate must clear
    its pre-registered bar in every period, not merely on average.

    Raises ValidationError for a caller error (bad argument shape,
    non-positive n_folds, or n_folds exceeding the number of samples --
    every fold must contain at least one sample). Never raises merely
    because a fold's own validation failed to clear its criteria; that
    is a normal, evidence-bearing outcome, reflected in fold_results and
    in overall_passed being False.
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
    if not isinstance(n_folds, int) or isinstance(n_folds, bool) or n_folds <= 0:
        raise ValidationError("n_folds must be a positive int")
    if n_folds > len(samples):
        raise ValidationError(
            f"n_folds ({n_folds}) cannot exceed the number of samples ({len(samples)}) -- "
            "every fold must contain at least one sample"
        )

    # B5: chronological sort by PARSED timestamp, never by raw string --
    # string order diverges from temporal order across mixed offsets,
    # Z-suffixes, or precision. Unparseable timestamps fail loudly.
    try:
        sorted_samples = sorted(samples, key=lambda s: parse_utc(s.feature_value.computed_at_utc))
    except ValueError as exc:
        raise ValidationError(f"unparseable sample timestamp: {exc}") from exc
    boundaries = _fold_boundaries(len(sorted_samples), n_folds)
    fold_results = tuple(
        run_validation(evaluate_fn, specification, tuple(sorted_samples[start:end]), clock=clock)
        for start, end in boundaries
    )

    fold_hit_rates = [f.hit_rate for f in fold_results if f.hit_rate is not None]
    hit_rate_range = (max(fold_hit_rates) - min(fold_hit_rates)) if len(fold_hit_rates) >= 2 else None

    overall_passed = all(f.overall_passed for f in fold_results)
    if not overall_passed:
        failing_folds = [i for i, f in enumerate(fold_results) if not f.overall_passed]
        _logger.warning(
            "walk-forward validation failed: candidate=%s/%s n_folds=%d failing_folds=%s",
            specification.name, specification.version, n_folds, failing_folds,
        )

    return WalkForwardResult(
        candidate_name=specification.name,
        candidate_version=specification.version,
        n_folds=n_folds,
        fold_results=fold_results,
        hit_rate_range=hit_rate_range,
        validated_at_utc=clock(),
        overall_passed=overall_passed,
        sample_set_fingerprint=fingerprint_samples(samples),
    )
