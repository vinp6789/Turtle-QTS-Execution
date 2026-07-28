"""Leakage & causality audit stage (Alpha Engine Milestone 4.3;
Architecture v0.2 SS6.2 "Leakage & causality audits").

Contributes ONE MORE named stage to an EvidencePackage (Milestone 4.2)
via EvidencePackage.with_stage_result() -- this module does not redesign
EvidencePackage, ValidationSample, or run_validation; it is a second,
independent scoring pass over the same sample sequence run_validation()
already consumes. Zero changes to EvidencePackage were needed to add
this: with_stage_result() already existed for exactly this purpose.

WHAT THIS AUDITS, and why it is scoped this way: the Research
repository's verify_causality methodology (checking that a feature's
value at index i is unaffected by altering data at index >i) requires a
time-indexed historical series this system does not have
(alpha_engine.features has no historical windowing -- Milestone 2.1's
own documented boundary, unchanged since). Rather than fake that
methodology against data that does not exist, this audit checks the two
concrete leakage/integrity properties that DO apply to any
ValidationSample batch, regardless of whether historical windowing ever
exists:

  1. Duplicate detection: no two samples share the same (symbol,
     feature.computed_at_utc). A duplicated data point silently inflates
     apparent evidence (double-counting a hit or a miss) -- a real
     threat to evidence quality even without any temporal-ordering
     concern.
  2. Outcome-after-feature ordering: when a sample declares
     outcome_observed_at_utc (Milestone 4.3's additive, optional
     ValidationSample field -- existing samples without it remain valid,
     reported as NOT VERIFIABLE rather than assumed causally sound),
     this audit requires it to be STRICTLY LATER than the feature's own
     computed_at_utc. A realized outcome measured at or before the
     moment the feature was computed cannot have been genuinely
     predicted by it -- that is the concrete, checkable form "no
     look-ahead" takes in this architecture today.

A sample missing outcome_observed_at_utc is NOT treated as passing -- it
is reported NOT VERIFIABLE, and blocks an overall PASS, exactly the same
"never assume a criterion was cleared when it was not evaluated"
discipline run_validation() already applies to unrecognized acceptance-
criteria keys (Milestone 4.1). This is deliberate: it means supplying
real observation timestamps is the only way to earn a clean audit, not
an optional nicety that is silently assumed fine.

Deliberately NOT built here: walk-forward folds, purge/embargo,
bootstrap, attribution, Monte Carlo, calibration -- unrelated validation
techniques, each its own future stage, each attaching the same way.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Tuple

from .._time import parse_utc
from .errors import ValidationError
from .models import ValidationSample

_logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class CausalityAuditResult:
    """One run_causality_audit() call's outcome. to_dict() produces the
    JSON-native shape EvidencePackage.with_stage_result() expects --
    matching every other stage result in this package (ValidationResult
    included)."""

    total_samples: int
    unique_sample_keys: int
    duplicate_samples: int
    ordering_verified: int
    ordering_violated: int
    ordering_not_verifiable: int
    violation_details: Tuple[str, ...]
    audited_at_utc: str
    passed: bool

    def __post_init__(self):
        for field_name in (
            "total_samples", "unique_sample_keys", "duplicate_samples",
            "ordering_verified", "ordering_violated", "ordering_not_verifiable",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValidationError(f"CausalityAuditResult.{field_name} must be a non-negative int")
        if self.unique_sample_keys + self.duplicate_samples != self.total_samples:
            raise ValidationError(
                "CausalityAuditResult: unique_sample_keys + duplicate_samples must equal total_samples "
                f"({self.unique_sample_keys}+{self.duplicate_samples} != {self.total_samples})"
            )
        if self.ordering_verified + self.ordering_violated + self.ordering_not_verifiable != self.total_samples:
            raise ValidationError(
                "CausalityAuditResult: ordering_verified + ordering_violated + ordering_not_verifiable "
                f"must equal total_samples ({self.ordering_verified}+{self.ordering_violated}+"
                f"{self.ordering_not_verifiable} != {self.total_samples})"
            )
        if not isinstance(self.violation_details, tuple) or not all(
            isinstance(v, str) and v.strip() for v in self.violation_details
        ):
            raise ValidationError("CausalityAuditResult.violation_details must be a tuple of non-empty strings")
        if not isinstance(self.audited_at_utc, str) or not self.audited_at_utc.strip():
            raise ValidationError("CausalityAuditResult.audited_at_utc must be a non-empty string")
        if not isinstance(self.passed, bool):
            raise ValidationError("CausalityAuditResult.passed must be a bool")
        expected_passed = (
            self.duplicate_samples == 0
            and self.ordering_violated == 0
            and self.ordering_not_verifiable == 0
        )
        if self.passed != expected_passed:
            raise ValidationError(
                "CausalityAuditResult.passed is inconsistent -- must be True iff there are zero "
                "duplicates, zero ordering violations, and zero not-verifiable samples"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_samples": self.total_samples,
            "unique_sample_keys": self.unique_sample_keys,
            "duplicate_samples": self.duplicate_samples,
            "ordering_verified": self.ordering_verified,
            "ordering_violated": self.ordering_violated,
            "ordering_not_verifiable": self.ordering_not_verifiable,
            "violation_details": list(self.violation_details),
            "audited_at_utc": self.audited_at_utc,
            "passed": self.passed,
        }


def run_causality_audit(
    samples: Tuple[ValidationSample, ...],
    clock: Callable[[], str] = _now,
) -> CausalityAuditResult:
    """Scores a ValidationSample batch for duplicate data points and
    outcome-after-feature ordering violations. Never raises for a data
    condition (a duplicate, a violation, or an unverifiable sample are
    all normal, counted outcomes) -- only for a caller error (bad
    argument shape, or a supplied outcome_observed_at_utc that is not a
    parseable timestamp, which is a configuration error in the sample
    data itself, not a leakage finding)."""
    if not isinstance(samples, tuple) or len(samples) == 0:
        raise ValidationError("samples must be a non-empty tuple of ValidationSample")
    if not all(isinstance(s, ValidationSample) for s in samples):
        raise ValidationError("samples must contain only ValidationSample instances")

    seen_keys = set()
    duplicate_count = 0
    ordering_verified = 0
    ordering_violated = 0
    ordering_not_verifiable = 0
    violation_details = []

    for index, sample in enumerate(samples):
        key = (sample.feature_value.symbol.value, sample.feature_value.computed_at_utc)
        if key in seen_keys:
            duplicate_count += 1
            violation_details.append(
                f"sample {index}: duplicate data point for {key[0]} @ {key[1]} "
                "(already present earlier in this batch)"
            )
        else:
            seen_keys.add(key)

        if sample.outcome_observed_at_utc is None:
            ordering_not_verifiable += 1
            continue
        try:
            feature_time = parse_utc(sample.feature_value.computed_at_utc)
            outcome_time = parse_utc(sample.outcome_observed_at_utc)
        except ValueError as exc:
            raise ValidationError(f"sample {index}: unparseable timestamp: {exc}") from exc

        if outcome_time > feature_time:
            ordering_verified += 1
        else:
            ordering_violated += 1
            violation_details.append(
                f"sample {index}: outcome_observed_at_utc ({sample.outcome_observed_at_utc}) does not "
                f"strictly follow feature computed_at_utc ({sample.feature_value.computed_at_utc}) -- a "
                "realized outcome cannot be measured at or before the feature that supposedly predicted it"
            )

    total = len(samples)
    passed = duplicate_count == 0 and ordering_violated == 0 and ordering_not_verifiable == 0

    if not passed:
        # B4: an audit that finds duplicate data points or causality
        # violations is exactly the "hidden bias" / "incorrect research
        # conclusions" risk the audit charter named -- this must not be
        # silently discoverable only by a caller who happens to inspect
        # CausalityAuditResult.passed.
        _logger.warning(
            "causality audit failed: total_samples=%d duplicate_samples=%d "
            "ordering_violated=%d ordering_not_verifiable=%d",
            total, duplicate_count, ordering_violated, ordering_not_verifiable,
        )

    return CausalityAuditResult(
        total_samples=total,
        unique_sample_keys=len(seen_keys),
        duplicate_samples=duplicate_count,
        ordering_verified=ordering_verified,
        ordering_violated=ordering_violated,
        ordering_not_verifiable=ordering_not_verifiable,
        violation_details=tuple(violation_details),
        audited_at_utc=clock(),
        passed=passed,
    )
