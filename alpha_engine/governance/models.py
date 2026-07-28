"""GovernanceDecision: the typed decision artifact (Alpha Engine R3;
Architecture v0.2 SS2.3).

A decision is data, not judgment logic: nothing here scores evidence or
automates approval. It records WHO decided WHAT about WHICH evidence,
with structural reviewer separation (Architecture v0.2 SS2.2:
"Governance is separate from research... the registry records both roles
per decision and enforces the separation"). Identity is a plain string
today -- there is no identity/authentication layer in this repository;
the separation check (proposed_by != reviewed_by) is the honest subset
of SS2.2 buildable now, and is documented as such rather than
oversold.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict

from ..registry import LifecycleState
from .errors import GovernanceError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GovernanceDecisionType(Enum):
    APPROVE = "approve"
    REJECT = "reject"
    DEFER = "defer"


_RESULTING_STATE = {
    GovernanceDecisionType.APPROVE: LifecycleState.APPROVED,
    GovernanceDecisionType.REJECT: LifecycleState.REJECTED,
    GovernanceDecisionType.DEFER: LifecycleState.DEFERRED,
}


@dataclass(frozen=True)
class GovernanceDecision:
    """Immutable. decided_at_utc is caller/clock-supplied like every
    timestamped type in this codebase."""

    experiment_id: str
    decision: GovernanceDecisionType
    evidence_fingerprint: str
    proposed_by: str
    reviewed_by: str
    rationale: str
    decided_at_utc: str

    def __post_init__(self):
        for field_name in ("experiment_id", "evidence_fingerprint", "proposed_by",
                           "reviewed_by", "rationale", "decided_at_utc"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise GovernanceError(f"GovernanceDecision.{field_name} must be a non-empty string")
        if not isinstance(self.decision, GovernanceDecisionType):
            raise GovernanceError("GovernanceDecision.decision must be a GovernanceDecisionType")
        if self.proposed_by.strip() == self.reviewed_by.strip():
            raise GovernanceError(
                "GovernanceDecision.reviewed_by must differ from proposed_by -- the researcher "
                "may not review their own hypothesis (Architecture v0.2 SS2.2)"
            )

    @property
    def resulting_state(self) -> LifecycleState:
        return _RESULTING_STATE[self.decision]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "decision": self.decision.value,
            "evidence_fingerprint": self.evidence_fingerprint,
            "proposed_by": self.proposed_by,
            "reviewed_by": self.reviewed_by,
            "rationale": self.rationale,
            "decided_at_utc": self.decided_at_utc,
        }
