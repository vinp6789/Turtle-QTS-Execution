"""Bootstrap resampling stage (Alpha Engine Milestone 4.5; Architecture
v0.2 SS6.5 "Bootstrap", SS6.7 "Monte Carlo").

Contributes ONE MORE named stage to an EvidencePackage (Milestone 4.2)
via EvidencePackage.with_stage_result() -- zero changes to EvidencePackage
were needed, the third stage in a row to confirm this.

WHY THIS IS BOOTSTRAP RESAMPLING, NOT "ATTRIBUTION, BOOTSTRAP, AND
CALIBRATION" AS ONE MILESTONE: the roadmap groups these three together
because the Research repository's methodology treats them as a set --
but two of the three do not honestly apply to today's one candidate:

  - Attribution (Architecture v0.2 SS6.6) decomposes a MULTI-COMPONENT
    conviction score by ablating each component (ON vs. forced-OFF) to
    measure its independent contribution. FundingRateThresholdRuleCandidate
    (Milestone 3.2) has exactly ONE feature (funding_rate_raw, Milestone
    2.1) and ONE decision parameter (threshold) -- there is nothing to
    ablate against. This becomes meaningful once a second, orthogonal
    feature/data source exists and a candidate combines more than one
    signal -- the long-term direction this project has already named
    (Open Interest, on-chain, macro, ...), not before.
  - Calibration (ROC/PR AUC, Brier score, a calibration curve) requires
    a CONTINUOUS PREDICTED PROBABILITY to compare against realized
    outcomes. CandidateSignal.direction (Milestone 3.2) is a discrete
    choice -- LONG, SHORT, or FLAT -- never a probability. This becomes
    meaningful once a probabilistic/statistical candidate type exists,
    not for a fixed threshold rule.

Building either now, against data that cannot support them, would be
exactly the kind of premature abstraction this project has consistently
avoided. Bootstrap resampling is the one technique of the three that
transplants honestly without any of that: it resamples the SAMPLE SET
itself (not a fitted model's coefficients -- there are none here) and
asks a question that applies to any candidate, fitted or not: "is the
observed hit rate a robust finding, or an artifact of one small, fixed
ordering of a limited sample set?" -- precisely the Research repository's
own stated rationale for its Monte Carlo bootstrap
(run_monte_carlo_robustness): reuses compute_portfolio_metrics()
unmodified, "does not change any trade or metric-computation logic, only
the ordering/composition of the resampled trade set." This module keeps
that same discipline: every resample is scored by the exact same
run_validation() (Milestone 4.1) every other stage already trusts; no
metric is recomputed differently here.

DETERMINISM (non-negotiable per project direction): resampling is
pseudo-random by nature, so this module requires an explicit seed --
there is no default. A caller must consciously choose and record one,
exactly like n_folds is an explicit walk-forward parameter (Milestone
4.4) rather than a silently-chosen default. Given the same seed, the
same samples, and the same n_resamples, the resampled index sequence
(via a LOCAL random.Random(seed) instance, never the global random
module -- no hidden shared state) is byte-for-byte reproducible, and so
is the resulting BootstrapResult.

NO INVENTED PASS/FAIL THRESHOLD: this stage reports a distribution
(mean/min/max observed hit rate across resamples), matching Research's
own framing of its Monte Carlo report as diagnostic, not gating
("print_monte_carlo_report displays baseline vs. Monte Carlo mean,
5th/95th percentile... for each metric" -- a report). The one number
that IS checked against a fixed bar, fraction_meeting_min_hit_rate,
reuses the candidate's OWN pre-registered min_hit_rate acceptance
criterion (Milestone 3.1) -- never a threshold invented by this module.
If min_hit_rate is not declared, that fraction is simply not computed
(None), rather than compared against a fabricated default.
"""

import random
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..candidates import CandidateSpecification
from .errors import ValidationError
from .models import ValidationSample
from .runner import EvaluateFn, run_validation

_MIN_HIT_RATE_KEY = "min_hit_rate"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class BootstrapResult:
    """One run_bootstrap_resampling() call's outcome. Diagnostic, not
    gating (see module docstring) -- there is deliberately no
    overall_passed field here; EvidencePackage.with_stage_result() does
    not require one (it validates only that a stage result is a
    non-empty, JSON-native Mapping), and fabricating a pass/fail verdict
    for a distributional report would misrepresent what this stage
    actually establishes."""

    candidate_name: str
    candidate_version: str
    n_resamples: int
    resample_size: int
    seed: int
    resamples_with_hit_rate: int
    mean_hit_rate: Optional[Decimal]
    min_hit_rate_observed: Optional[Decimal]
    max_hit_rate_observed: Optional[Decimal]
    fraction_meeting_min_hit_rate: Optional[Decimal]
    validated_at_utc: str

    def __post_init__(self):
        if not isinstance(self.candidate_name, str) or not self.candidate_name.strip():
            raise ValidationError("BootstrapResult.candidate_name must be a non-empty string")
        if not isinstance(self.candidate_version, str) or not self.candidate_version.strip():
            raise ValidationError("BootstrapResult.candidate_version must be a non-empty string")
        for field_name in ("n_resamples", "resample_size", "resamples_with_hit_rate"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValidationError(f"BootstrapResult.{field_name} must be a non-negative int")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise ValidationError("BootstrapResult.seed must be an int")
        if self.resamples_with_hit_rate > self.n_resamples:
            raise ValidationError("BootstrapResult.resamples_with_hit_rate cannot exceed n_resamples")

        hit_rate_fields = (self.mean_hit_rate, self.min_hit_rate_observed, self.max_hit_rate_observed)
        if self.resamples_with_hit_rate == 0:
            if any(f is not None for f in hit_rate_fields):
                raise ValidationError(
                    "BootstrapResult.mean/min/max_hit_rate_observed must all be None when "
                    "resamples_with_hit_rate is 0 -- never fabricate a distribution from zero observations"
                )
        else:
            if not all(isinstance(f, Decimal) for f in hit_rate_fields):
                raise ValidationError(
                    "BootstrapResult.mean/min/max_hit_rate_observed must all be Decimals when "
                    "resamples_with_hit_rate > 0"
                )
            if not (self.min_hit_rate_observed <= self.mean_hit_rate <= self.max_hit_rate_observed):
                raise ValidationError(
                    "BootstrapResult: min_hit_rate_observed <= mean_hit_rate <= max_hit_rate_observed must hold"
                )
        if self.fraction_meeting_min_hit_rate is not None:
            if not isinstance(self.fraction_meeting_min_hit_rate, Decimal):
                raise ValidationError("BootstrapResult.fraction_meeting_min_hit_rate must be a Decimal or None")
            if not (Decimal("0") <= self.fraction_meeting_min_hit_rate <= Decimal("1")):
                raise ValidationError("BootstrapResult.fraction_meeting_min_hit_rate must be in [0, 1]")
        if not isinstance(self.validated_at_utc, str) or not self.validated_at_utc.strip():
            raise ValidationError("BootstrapResult.validated_at_utc must be a non-empty string")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_name": self.candidate_name,
            "candidate_version": self.candidate_version,
            "n_resamples": self.n_resamples,
            "resample_size": self.resample_size,
            "seed": self.seed,
            "resamples_with_hit_rate": self.resamples_with_hit_rate,
            "mean_hit_rate": str(self.mean_hit_rate) if self.mean_hit_rate is not None else None,
            "min_hit_rate_observed": (
                str(self.min_hit_rate_observed) if self.min_hit_rate_observed is not None else None
            ),
            "max_hit_rate_observed": (
                str(self.max_hit_rate_observed) if self.max_hit_rate_observed is not None else None
            ),
            "fraction_meeting_min_hit_rate": (
                str(self.fraction_meeting_min_hit_rate)
                if self.fraction_meeting_min_hit_rate is not None else None
            ),
            "validated_at_utc": self.validated_at_utc,
        }


def run_bootstrap_resampling(
    evaluate_fn: EvaluateFn,
    specification: CandidateSpecification,
    samples: Tuple[ValidationSample, ...],
    n_resamples: int,
    seed: int,
    clock: Callable[[], str] = _now,
) -> BootstrapResult:
    """Resamples `samples` (with replacement, same size each draw) exactly
    n_resamples times using a local, seeded random.Random(seed) instance
    -- never the global random module -- and scores each resample with
    run_validation(). Reports the resulting hit-rate distribution, plus
    the fraction of resamples meeting the specification's own
    min_hit_rate criterion when one is declared (None otherwise).

    Raises ValidationError for a caller error (bad argument shape,
    non-positive n_resamples, non-int seed, or a malformed min_hit_rate
    value under specification.acceptance_criteria). Never raises merely
    because a resample happened to draw zero signaled samples; that
    resample simply does not contribute a hit rate to the distribution.
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
    if not isinstance(n_resamples, int) or isinstance(n_resamples, bool) or n_resamples <= 0:
        raise ValidationError("n_resamples must be a positive int")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValidationError("seed must be an int")

    required_min_hit_rate = specification.acceptance_criteria.get(_MIN_HIT_RATE_KEY)
    required_decimal: Optional[Decimal] = None
    if required_min_hit_rate is not None:
        try:
            required_decimal = Decimal(str(required_min_hit_rate))
        except InvalidOperation as exc:
            raise ValidationError(
                f"acceptance_criteria[{_MIN_HIT_RATE_KEY!r}] must be numeric, got {required_min_hit_rate!r}"
            ) from exc

    rng = random.Random(seed)
    n = len(samples)
    hit_rates: List[Decimal] = []
    meeting_count = 0

    for _ in range(n_resamples):
        resampled = tuple(samples[rng.randrange(n)] for _ in range(n))
        result = run_validation(evaluate_fn, specification, resampled, clock=clock)
        if result.hit_rate is not None:
            hit_rates.append(result.hit_rate)
            if required_decimal is not None and result.hit_rate >= required_decimal:
                meeting_count += 1

    resamples_with_hit_rate = len(hit_rates)
    mean_hit_rate = (sum(hit_rates) / Decimal(resamples_with_hit_rate)) if hit_rates else None
    min_observed = min(hit_rates) if hit_rates else None
    max_observed = max(hit_rates) if hit_rates else None
    fraction_meeting = (
        Decimal(meeting_count) / Decimal(n_resamples) if required_decimal is not None else None
    )

    return BootstrapResult(
        candidate_name=specification.name,
        candidate_version=specification.version,
        n_resamples=n_resamples,
        resample_size=n,
        seed=seed,
        resamples_with_hit_rate=resamples_with_hit_rate,
        mean_hit_rate=mean_hit_rate,
        min_hit_rate_observed=min_observed,
        max_hit_rate_observed=max_observed,
        fraction_meeting_min_hit_rate=fraction_meeting,
        validated_at_utc=clock(),
    )
