"""Governance Layer (Architecture v0.2 SS2; Alpha Engine R3).

Public API:
    GovernanceDecision        -- immutable decision artifact with
                                 structural reviewer separation
    GovernanceDecisionType    -- APPROVE / REJECT / DEFER
    record_governance_decision -- validates a decision against the
                                 registry record (state + evidence
                                 fingerprint) and durably applies it;
                                 the only path into APPROVED/REJECTED/
                                 DEFERRED
    approved_experiments      -- the current approved set (APPROVED +
                                 live production states)
    GovernanceError           -- this sub-package's error base

Deliberately NOT built: automated judgment (no code scores evidence or
decides approval -- a human records the decision), quorum/multi-reviewer
flows, and a real identity layer (proposed_by/reviewed_by are plain
strings; separation is enforced on the strings, documented honestly in
models.py).
"""

from .decisions import approved_experiments, record_governance_decision
from .errors import GovernanceError
from .models import GovernanceDecision, GovernanceDecisionType

__all__ = [
    "GovernanceDecision",
    "GovernanceDecisionType",
    "record_governance_decision",
    "approved_experiments",
    "GovernanceError",
]
