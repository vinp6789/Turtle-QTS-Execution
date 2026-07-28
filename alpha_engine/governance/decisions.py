"""record_governance_decision(): the typed entry point that moves an
experiment through IN_REVIEW (Alpha Engine R3).

Cross-checks the decision against the registry's own record before
applying it:
  - the experiment must be IN_REVIEW (the registry re-enforces this too);
  - the decision's evidence_fingerprint must equal the experiment's
    attached evidence fingerprint -- a decision must reference the exact
    evidence that was reviewed, never a stale or foreign bundle.

The registry's apply_governance_decision() is the single durable path
into APPROVED/REJECTED/DEFERRED; this module is its only intended
caller.
"""

from typing import Tuple

from .._time import parse_utc
from ..registry import ExperimentRecord, ExperimentRegistry, LifecycleState
from .errors import GovernanceError
from .models import GovernanceDecision


def record_governance_decision(
    registry: ExperimentRegistry,
    decision: GovernanceDecision,
) -> ExperimentRecord:
    """Validates and durably records `decision`, returning the updated
    record (now APPROVED, REJECTED, or DEFERRED)."""
    if not isinstance(registry, ExperimentRegistry):
        raise GovernanceError(f"registry must be an ExperimentRegistry, got {type(registry).__name__}")
    if not isinstance(decision, GovernanceDecision):
        raise GovernanceError(f"decision must be a GovernanceDecision, got {type(decision).__name__}")

    record = registry.get(decision.experiment_id)
    if record.lifecycle_state is not LifecycleState.IN_REVIEW:
        raise GovernanceError(
            f"experiment {decision.experiment_id!r} is in state "
            f"{record.lifecycle_state.value!r}, not {LifecycleState.IN_REVIEW.value!r} -- "
            "a decision may only be recorded for an experiment under review"
        )
    if record.evidence_fingerprint != decision.evidence_fingerprint:
        raise GovernanceError(
            f"decision references evidence fingerprint {decision.evidence_fingerprint!r} but "
            f"experiment {decision.experiment_id!r} carries "
            f"{record.evidence_fingerprint!r} -- a decision must reference the exact evidence "
            "reviewed"
        )
    return registry.apply_governance_decision(
        decision.experiment_id, decision.to_dict(), decision.resulting_state,
    )


def approved_experiments(registry: ExperimentRegistry) -> Tuple[ExperimentRecord, ...]:
    """Every experiment currently holding governance approval and not yet
    frozen/retiring: APPROVED plus the live production states
    (SHAKEDOWN, FULL_PRODUCTION). Deterministically ordered (the
    registry's own created_at/id ordering)."""
    if not isinstance(registry, ExperimentRegistry):
        raise GovernanceError(f"registry must be an ExperimentRegistry, got {type(registry).__name__}")
    approved = []
    for state in (LifecycleState.APPROVED, LifecycleState.SHAKEDOWN, LifecycleState.FULL_PRODUCTION):
        approved.extend(registry.list_experiments(state=state))
    # B5: rank by PARSED timestamp, not raw string -- see alpha_engine._time.
    try:
        return tuple(sorted(approved, key=lambda r: (parse_utc(r.created_at_utc), r.experiment_id)))
    except ValueError as exc:
        raise GovernanceError(f"unparseable created_at_utc in registry record: {exc}") from exc
