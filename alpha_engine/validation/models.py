"""Value types for the validation harness (Architecture v0.2 SS6; Alpha
Engine Milestone 4.1).

Scope, deliberate: this milestone builds the SINGLE-PASS validation
mechanics needed to evaluate the one existing candidate
(FundingRateThresholdRuleCandidate, Milestone 3.2) against a
caller-supplied historical sample sequence -- not walk-forward folds,
not purge/embargo, not Monte Carlo/bootstrap/attribution/calibration.
Those are real, named future work (per project direction, "layered on
incrementally without changing the overall architecture"), not omissions
papered over: alpha_engine has no historical data ingestion pipeline yet
(alpha_engine.features has no windowing -- Milestone 2.1's own documented
boundary), so ValidationSample accepts historical (feature, outcome)
pairs as plain input rather than this module fabricating or fetching
them itself. Where that historical data eventually comes from is future
work; how to score a candidate against ANY such sequence, once available,
is what this milestone actually builds.

Why this is NOT yet the Evidence Package (Architecture v0.2 SS2.1):
ValidationResult is a single run's output, in-memory, not yet sealed,
not yet stored in the Experiment Registry, not yet reviewed by
governance. It IS, deliberately, shaped so that sealing is a small,
later step rather than a redesign: to_dict() already produces the exact
JSON-native shape an Evidence Package would archive -- pre-registered
criteria (from CandidateSpecification.acceptance_criteria, Milestone
3.1), and a mapping from each declared criterion to its measured
disposition (CriterionCheck), exactly the shape Architecture v0.2 SS2.1
specifies: "a mapping from each declared threshold to the observed
value, with an explicit pass/fail." No criterion is silently skipped: an
acceptance-criteria key this harness does not know how to check is
reported as NOT_EVALUATED, never ignored and never assumed to pass.
"""

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from .._time import canonical_utc
from ..features import FeatureValue
from .errors import ValidationError


def fingerprint_samples(samples: Tuple["ValidationSample", ...]) -> str:
    """Content fingerprint of a sample sequence (audit finding B1):
    SHA-256 over the canonical JSON of every sample, in order. Binds a
    validation result to the exact dataset that produced it -- without
    this, evidence could not be tied to its inputs, re-runs on different
    (cherry-picked) data were undetectable, and cross-experiment
    comparison had no data-identity check even in principle. Timestamps
    are canonicalized (B5) so equal instants fingerprint equally
    regardless of the producer's formatting. Raises ValidationError for
    a non-sample sequence or an unparseable timestamp (configuration
    error, fail-loud)."""
    if not isinstance(samples, tuple) or len(samples) == 0:
        raise ValidationError("samples must be a non-empty tuple of ValidationSample")
    if not all(isinstance(s, ValidationSample) for s in samples):
        raise ValidationError("samples must contain only ValidationSample instances")
    rows = []
    for index, sample in enumerate(samples):
        fv = sample.feature_value
        try:
            computed_at = canonical_utc(fv.computed_at_utc)
            observed_at = (
                canonical_utc(sample.outcome_observed_at_utc)
                if sample.outcome_observed_at_utc is not None else None
            )
        except ValueError as exc:
            raise ValidationError(f"sample {index}: unparseable timestamp: {exc}") from exc
        rows.append({
            "feature_name": fv.feature_name,
            "feature_version": fv.feature_version,
            "symbol": fv.symbol.value,
            "computed_at_utc": computed_at,
            "available": fv.available,
            "value": str(fv.value) if fv.value is not None else None,
            "reason": fv.reason,
            "realized_outcome": str(sample.realized_outcome),
            "outcome_observed_at_utc": observed_at,
            "regime_label": sample.regime_label,
        })
    canonical = json.dumps(rows, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ValidationSample:
    """One historical (feature, outcome) pair. realized_outcome is the
    symbol's signed realized return over whatever fixed horizon the
    caller defines (positive = price rose, negative = price fell) --
    the minimum information needed to check whether a signal's direction
    was correct. Not a full triple-barrier label (Research repo style);
    that refinement is future work, layered on once justified.

    outcome_observed_at_utc (Milestone 4.3, additive -- optional, default
    None, existing samples built without it remain valid): when the
    realized outcome was actually measured. Enables causality_audit.
    run_causality_audit() to check the one concrete, checkable form
    "no look-ahead" takes in this architecture -- the outcome must be
    observed strictly after the feature was computed. Omitting it does
    not make a sample invalid; it makes that sample's ordering
    unverifiable to the causality audit (reported, never silently
    assumed sound -- see causality_audit.py).

    regime_label (Milestone 4.6, additive -- optional, default None,
    existing samples built without it remain valid): a caller-supplied
    market-regime tag (e.g. "risk_on"/"risk_off", any taxonomy the
    caller chooses -- this type does not interpret its meaning, only
    groups samples that share one). Enables
    regime_stratification.run_regime_stratified_validation() to check
    whether performance is concentrated in one regime rather than robust
    across several. A sample without one is not invalid; it is simply
    unstratifiable (reported, never silently grouped or ignored -- see
    regime_stratification.py)."""

    feature_value: FeatureValue
    realized_outcome: Decimal
    outcome_observed_at_utc: Optional[str] = None
    regime_label: Optional[str] = None

    def __post_init__(self):
        if not isinstance(self.feature_value, FeatureValue):
            raise ValidationError(
                f"ValidationSample.feature_value must be a FeatureValue, got {type(self.feature_value).__name__}"
            )
        if not isinstance(self.realized_outcome, Decimal):
            raise ValidationError(
                f"ValidationSample.realized_outcome must be a Decimal, got {type(self.realized_outcome).__name__}"
            )
        if self.outcome_observed_at_utc is not None and (
            not isinstance(self.outcome_observed_at_utc, str) or not self.outcome_observed_at_utc.strip()
        ):
            raise ValidationError("ValidationSample.outcome_observed_at_utc must be a non-empty string or None")
        if self.regime_label is not None and (
            not isinstance(self.regime_label, str) or not self.regime_label.strip()
        ):
            raise ValidationError("ValidationSample.regime_label must be a non-empty string or None")


class CriterionOutcome(Enum):
    """The disposition of one pre-registered acceptance criterion against
    a validation run's measured metrics."""

    PASS = "pass"
    FAIL = "fail"
    NOT_EVALUATED = "not_evaluated"


@dataclass(frozen=True)
class CriterionCheck:
    """One declared acceptance-criteria key's measurement. required_value
    is copied verbatim from CandidateSpecification.acceptance_criteria;
    observed_value is None exactly when outcome is NOT_EVALUATED (this
    harness does not recognize the key, or the metric it would compare
    against could not be computed from the given samples)."""

    criterion_key: str
    required_value: Any
    observed_value: Optional[Any]
    outcome: CriterionOutcome

    def __post_init__(self):
        if not isinstance(self.criterion_key, str) or not self.criterion_key.strip():
            raise ValidationError("CriterionCheck.criterion_key must be a non-empty string")
        if not isinstance(self.outcome, CriterionOutcome):
            raise ValidationError("CriterionCheck.outcome must be a CriterionOutcome")
        if self.outcome is CriterionOutcome.NOT_EVALUATED and self.observed_value is not None:
            raise ValidationError("CriterionCheck.observed_value must be None when outcome is NOT_EVALUATED")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "criterion_key": self.criterion_key,
            "required_value": self.required_value,
            "observed_value": self.observed_value,
            "outcome": self.outcome.value,
        }


@dataclass(frozen=True)
class ValidationResult:
    """One run_validation() call's outcome (Milestone 4.1) -- see module
    docstring on why this is the pre-Evidence-Package shape, not the
    Evidence Package itself. Immutable; a re-run (different samples, a
    refined specification) produces a new ValidationResult, never a
    mutation of this one."""

    candidate_name: str
    candidate_version: str
    validated_at_utc: str
    total_samples: int
    unavailable_samples: int
    flat_samples: int
    signaled_samples: int
    hits: int
    hit_rate: Optional[Decimal]
    mean_directional_return: Optional[Decimal]
    criteria_results: Tuple[CriterionCheck, ...]
    overall_passed: bool
    # B1 (additive): fingerprint of the exact sample set scored. Optional
    # with default None for backward compatibility of direct
    # construction; run_validation() always populates it.
    sample_set_fingerprint: Optional[str] = None

    # ---- Payoff decomposition (additive, 2026-08-07) ----------------
    # WHY THESE EXIST. hit_rate alone cannot decide whether a strategy is
    # tradeable. Indian VDA tax is levied on GROSS gains with no loss
    # set-off, so viability turns on the gross profit factor, not on how
    # often the direction was right. A campaign could clear
    # min_hit_rate and still be untradeable; without these fields that
    # was not even checkable after the fact.
    #
    # Same additive contract as sample_set_fingerprint above: Optional,
    # defaulted, appended last, so every existing construction site,
    # sealed evidence package and stored campaign keeps working
    # unchanged. A None here means "not computed by the code that
    # produced this result", never "zero".
    mean_win: Optional[Decimal] = None
    mean_loss: Optional[Decimal] = None          # positive magnitude
    gross_profit_factor: Optional[Decimal] = None

    @property
    def payoff_ratio(self) -> Optional[Decimal]:
        """mean_win / mean_loss -- the win/loss ratio a payoff-shape gate needs.

        None when either leg is absent, because a ratio with no
        denominator is undefined, not infinite.
        """
        if self.mean_win is None or self.mean_loss is None or self.mean_loss == 0:
            return None
        return self.mean_win / self.mean_loss

    @property
    def expectancy(self) -> Optional[Decimal]:
        """Mean profit per signaled sample.

        Deliberately an alias of mean_directional_return rather than a
        second stored field: they are the same quantity, and storing it
        twice would create two things to keep consistent.
        """
        return self.mean_directional_return

    def __post_init__(self):
        if not isinstance(self.candidate_name, str) or not self.candidate_name.strip():
            raise ValidationError("ValidationResult.candidate_name must be a non-empty string")
        if not isinstance(self.candidate_version, str) or not self.candidate_version.strip():
            raise ValidationError("ValidationResult.candidate_version must be a non-empty string")
        if not isinstance(self.validated_at_utc, str) or not self.validated_at_utc.strip():
            raise ValidationError("ValidationResult.validated_at_utc must be a non-empty string")
        for field_name in ("total_samples", "unavailable_samples", "flat_samples", "signaled_samples", "hits"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValidationError(f"ValidationResult.{field_name} must be a non-negative int")
        # Internal consistency: the four counted buckets must exactly
        # partition total_samples, and hits can never exceed the pool of
        # signaled (directional) samples they were drawn from.
        if self.unavailable_samples + self.flat_samples + self.signaled_samples != self.total_samples:
            raise ValidationError(
                "ValidationResult: unavailable_samples + flat_samples + signaled_samples "
                f"must equal total_samples ({self.unavailable_samples}+{self.flat_samples}+"
                f"{self.signaled_samples} != {self.total_samples})"
            )
        if self.hits > self.signaled_samples:
            raise ValidationError("ValidationResult.hits cannot exceed signaled_samples")
        if self.signaled_samples == 0:
            if self.hit_rate is not None or self.mean_directional_return is not None:
                raise ValidationError(
                    "ValidationResult.hit_rate/mean_directional_return must be None when "
                    "signaled_samples is 0 -- never fabricate a rate from zero signals"
                )
        else:
            if not isinstance(self.hit_rate, Decimal):
                raise ValidationError("ValidationResult.hit_rate must be a Decimal when signaled_samples > 0")
            if not isinstance(self.mean_directional_return, Decimal):
                raise ValidationError(
                    "ValidationResult.mean_directional_return must be a Decimal when signaled_samples > 0"
                )
        if not isinstance(self.criteria_results, tuple) or len(self.criteria_results) == 0:
            raise ValidationError("ValidationResult.criteria_results must be a non-empty tuple")
        if not all(isinstance(c, CriterionCheck) for c in self.criteria_results):
            raise ValidationError("ValidationResult.criteria_results must contain only CriterionCheck instances")
        if not isinstance(self.overall_passed, bool):
            raise ValidationError("ValidationResult.overall_passed must be a bool")
        # overall_passed is derived, but re-checked here defensively -- see
        # runner.run_validation for the authoritative derivation.
        expected_overall = all(c.outcome is CriterionOutcome.PASS for c in self.criteria_results)
        if self.overall_passed != expected_overall:
            raise ValidationError(
                "ValidationResult.overall_passed is inconsistent with criteria_results -- "
                "must be True iff every criterion's outcome is PASS"
            )
        if self.sample_set_fingerprint is not None and (
            not isinstance(self.sample_set_fingerprint, str) or not self.sample_set_fingerprint.strip()
        ):
            raise ValidationError("ValidationResult.sample_set_fingerprint must be a non-empty string or None")

        # Payoff decomposition: type, sign, and the one consistency rule
        # that matters -- nothing may be reported when nothing signaled.
        for field_name in ("mean_win", "mean_loss", "gross_profit_factor"):
            value = getattr(self, field_name)
            if value is None:
                continue
            if not isinstance(value, Decimal):
                raise ValidationError(f"ValidationResult.{field_name} must be a Decimal or None")
            if value < 0:
                raise ValidationError(
                    f"ValidationResult.{field_name} must be non-negative -- mean_loss is a "
                    f"MAGNITUDE, not a signed return"
                )
        if self.signaled_samples == 0 and any(
            getattr(self, f) is not None for f in ("mean_win", "mean_loss", "gross_profit_factor")
        ):
            raise ValidationError(
                "ValidationResult payoff fields must be None when signaled_samples is 0 -- "
                "never fabricate a payoff from zero signals"
            )

    def to_dict(self) -> Dict[str, Any]:
        """The JSON-native Mapping a future Evidence Package would seal
        verbatim. Pure function of this object's own fields."""
        return {
            "candidate_name": self.candidate_name,
            "candidate_version": self.candidate_version,
            "validated_at_utc": self.validated_at_utc,
            "total_samples": self.total_samples,
            "unavailable_samples": self.unavailable_samples,
            "flat_samples": self.flat_samples,
            "signaled_samples": self.signaled_samples,
            "hits": self.hits,
            "hit_rate": str(self.hit_rate) if self.hit_rate is not None else None,
            "mean_directional_return": (
                str(self.mean_directional_return) if self.mean_directional_return is not None else None
            ),
            "criteria_results": [c.to_dict() for c in self.criteria_results],
            "overall_passed": self.overall_passed,
            "sample_set_fingerprint": self.sample_set_fingerprint,
            # Payoff decomposition. Emitted as strings (or null) for the
            # same reason every other Decimal here is: canonical JSON
            # must not go through binary float. `payoff_ratio` is derived
            # and emitted for the reader's convenience; it is never
            # stored, so it cannot disagree with its two inputs.
            "mean_win": str(self.mean_win) if self.mean_win is not None else None,
            "mean_loss": str(self.mean_loss) if self.mean_loss is not None else None,
            "gross_profit_factor": (
                str(self.gross_profit_factor) if self.gross_profit_factor is not None else None
            ),
            "payoff_ratio": str(self.payoff_ratio) if self.payoff_ratio is not None else None,
        }
