"""Degradation assessment and the freeze path (Alpha Engine R7;
Architecture v0.2 SS3.4 "Performance drift" auto-freeze trigger, built as
the honest subset available today).

THE STANDARD IS THE EXPERIMENT'S OWN PRE-REGISTERED BAR: a live
experiment is degraded exactly when a recent ValidationResult -- produced
by the same run_validation() the experiment's original evidence used,
over recent live-period samples -- fails the acceptance criteria the
hypothesis itself declared before approval. No new threshold is invented
here (no "20% drawdown" default, no invented drift band): the promise the
candidate made to get approved is the promise it is held to in
production. Richer drift detection (statistical process control, rolling
comparisons against the original evidence distribution) is real future
work, layered on once the platform accumulates live history to compare
against.

assess_degradation() is PURE (record + result + clock in, assessment
out) -- it never touches the registry. Acting on an assessment is a
separate, explicit step (freeze_degraded), so the judgment and the state
change are independently testable and auditable, and a human can always
inspect the assessment before anything moves.

Fail-safe direction: degradation FREEZES (stops new signal emission --
the bridge's load_approved_specifications drops non-approved-set states
automatically) and never force-closes positions: existing positions
continue to their natural exits under the Execution Engine's own frozen
exit machinery, which this package cannot and does not reach into.
Retirement (RETIRING -> RETIRED) remains a deliberate governance/operator
act via registry.transition() -- deliberately not automated.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional, Tuple

from ..registry import (
    ExperimentRecord,
    ExperimentRegistry,
    LifecycleState,
    LIVE_STATES,
)
from ..validation import CriterionOutcome, ValidationResult
from .errors import DegradationError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class DegradationAssessment:
    experiment_id: str
    degraded: bool
    recommendation: Optional[LifecycleState]  # FROZEN when degraded, None otherwise
    reasons: Tuple[str, ...]
    assessed_at_utc: str

    def __post_init__(self):
        if not isinstance(self.experiment_id, str) or not self.experiment_id.strip():
            raise DegradationError("DegradationAssessment.experiment_id must be a non-empty string")
        if not isinstance(self.degraded, bool):
            raise DegradationError("DegradationAssessment.degraded must be a bool")
        if self.degraded:
            if self.recommendation is not LifecycleState.FROZEN:
                raise DegradationError("a degraded assessment must recommend FROZEN")
            if len(self.reasons) == 0:
                raise DegradationError("a degraded assessment must carry at least one reason")
        else:
            if self.recommendation is not None or len(self.reasons) != 0:
                raise DegradationError("a healthy assessment carries no recommendation and no reasons")
        if not isinstance(self.reasons, tuple) or not all(
            isinstance(r, str) and r.strip() for r in self.reasons
        ):
            raise DegradationError("DegradationAssessment.reasons must be a tuple of non-empty strings")
        if not isinstance(self.assessed_at_utc, str) or not self.assessed_at_utc.strip():
            raise DegradationError("DegradationAssessment.assessed_at_utc must be a non-empty string")


def assess_degradation(
    record: ExperimentRecord,
    recent_result: ValidationResult,
    clock: Callable[[], str] = _now,
) -> DegradationAssessment:
    """Pure judgment: does `recent_result` (recent live-period validation
    of the same candidate) clear the experiment's own pre-registered
    bar? Guards (caller errors): the record must be in a LIVE state, and
    the result must belong to the record's own candidate name/version."""
    if not isinstance(record, ExperimentRecord):
        raise DegradationError(f"record must be an ExperimentRecord, got {type(record).__name__}")
    if not isinstance(recent_result, ValidationResult):
        raise DegradationError(f"recent_result must be a ValidationResult, got {type(recent_result).__name__}")
    if record.lifecycle_state not in LIVE_STATES:
        raise DegradationError(
            f"experiment {record.experiment_id!r} is in state {record.lifecycle_state.value!r}; "
            "degradation is assessed only for live (shakedown/full_production) experiments"
        )
    spec = dict(record.specification)
    if (recent_result.candidate_name != spec.get("candidate_name")
            or recent_result.candidate_version != spec.get("candidate_version")):
        raise DegradationError(
            f"recent_result is for {recent_result.candidate_name!r} "
            f"v{recent_result.candidate_version}, but experiment {record.experiment_id!r} is "
            f"{spec.get('candidate_name')!r} v{spec.get('candidate_version')} -- refusing a "
            "mismatched assessment"
        )

    if recent_result.overall_passed:
        return DegradationAssessment(
            experiment_id=record.experiment_id, degraded=False,
            recommendation=None, reasons=(), assessed_at_utc=clock(),
        )
    reasons = tuple(
        f"criterion {check.criterion_key!r}: required {check.required_value!r}, "
        f"observed {check.observed_value!r} ({check.outcome.value})"
        for check in recent_result.criteria_results
        if check.outcome is not CriterionOutcome.PASS
    )
    return DegradationAssessment(
        experiment_id=record.experiment_id, degraded=True,
        recommendation=LifecycleState.FROZEN, reasons=reasons, assessed_at_utc=clock(),
    )


def freeze_degraded(registry: ExperimentRegistry, assessment: DegradationAssessment) -> ExperimentRecord:
    """Applies a degraded assessment: transitions the experiment to
    FROZEN (durably, through the registry's own guarded transition -- an
    experiment that has moved to a state with no FROZEN edge since the
    assessment raises the registry's own error rather than being forced).
    Refuses a non-degraded assessment outright: freezing a healthy
    experiment through the degradation path would misrepresent the
    freeze's recorded cause."""
    if not isinstance(registry, ExperimentRegistry):
        raise DegradationError(f"registry must be an ExperimentRegistry, got {type(registry).__name__}")
    if not isinstance(assessment, DegradationAssessment):
        raise DegradationError(f"assessment must be a DegradationAssessment, got {type(assessment).__name__}")
    if not assessment.degraded:
        raise DegradationError(
            f"assessment for {assessment.experiment_id!r} is not degraded -- refusing to freeze a "
            "healthy experiment through the degradation path"
        )
    return registry.transition(assessment.experiment_id, LifecycleState.FROZEN)
