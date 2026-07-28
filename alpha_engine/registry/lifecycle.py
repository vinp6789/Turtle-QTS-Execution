"""Experiment lifecycle states and the allowed-transition table (Alpha
Engine R2; Architecture v0.2 SS3).

Lives in the REGISTRY package deliberately: Architecture v0.2 SS1 makes
the Experiment Registry the single source of truth for an experiment's
"outcome timeline. From proposal through retirement, every state
transition" -- so the state definitions and the durable state bookkeeping
belong here. The (still separate) alpha_engine.lifecycle package hosts
POLICIES that decide when to request a transition (degradation
assessment, shakedown criteria -- R7+); this module is pure data plus the
legality table.

Differences from Architecture v0.2 SS3's diagram, deliberate and small:
  - IDEA is not a state -- an idea is by definition not yet registered.
  - CANDIDATE and VALIDATING are merged into VALIDATING: the SS3
    Proposed->Candidate acknowledgement gate presumed a governance
    identity layer that does not exist yet; a separate no-op state would
    be bookkeeping without meaning today. When governance acknowledgement
    becomes real, adding CANDIDATE between PROPOSED and VALIDATING is a
    table edit, not a redesign.
  - DEFERRED is terminal for THIS experiment: per SS3 itself, a deferral
    "returns to Candidate under amended pre-registration = a NEW
    experiment" (parent-linked), never a resumption of this one.
  - FROZEN -> re-approval is not modeled (SS3: "requires re-review with a
    fresh governance decision"); a frozen experiment can only proceed to
    RETIRING today. Re-approval, when built, is a new edge -- documented
    deferral, not an accident.

Governance-gated targets: APPROVED / REJECTED / DEFERRED may never be
reached through ExperimentRegistry.transition() directly -- only through
a recorded governance decision (R3's apply_governance_decision). This is
structural (transition() raises GovernanceRequiredError), not a naming
convention.
"""

from enum import Enum
from types import MappingProxyType
from typing import FrozenSet, Mapping


class LifecycleState(Enum):
    PROPOSED = "proposed"
    VALIDATING = "validating"
    EVIDENCE_SEALED = "evidence_sealed"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    SHAKEDOWN = "shakedown"
    FULL_PRODUCTION = "full_production"
    FROZEN = "frozen"
    RETIRING = "retiring"
    RETIRED = "retired"
    WITHDRAWN = "withdrawn"


INITIAL_STATE = LifecycleState.PROPOSED

# States only a recorded governance decision may enter (R3).
GOVERNANCE_DECISION_STATES: FrozenSet[LifecycleState] = frozenset({
    LifecycleState.APPROVED, LifecycleState.REJECTED, LifecycleState.DEFERRED,
})

# States representing "live in production" for promotion/selection purposes.
LIVE_STATES: FrozenSet[LifecycleState] = frozenset({
    LifecycleState.SHAKEDOWN, LifecycleState.FULL_PRODUCTION,
})

TERMINAL_STATES: FrozenSet[LifecycleState] = frozenset({
    LifecycleState.RETIRED, LifecycleState.REJECTED,
    LifecycleState.DEFERRED, LifecycleState.WITHDRAWN,
})

ALLOWED_TRANSITIONS: Mapping[LifecycleState, FrozenSet[LifecycleState]] = MappingProxyType({
    LifecycleState.PROPOSED: frozenset({LifecycleState.VALIDATING, LifecycleState.WITHDRAWN}),
    LifecycleState.VALIDATING: frozenset({LifecycleState.EVIDENCE_SEALED, LifecycleState.WITHDRAWN}),
    LifecycleState.EVIDENCE_SEALED: frozenset({LifecycleState.IN_REVIEW}),
    LifecycleState.IN_REVIEW: frozenset(GOVERNANCE_DECISION_STATES),
    LifecycleState.APPROVED: frozenset({LifecycleState.SHAKEDOWN}),
    LifecycleState.SHAKEDOWN: frozenset({
        LifecycleState.FULL_PRODUCTION, LifecycleState.FROZEN, LifecycleState.RETIRING,
    }),
    LifecycleState.FULL_PRODUCTION: frozenset({LifecycleState.FROZEN, LifecycleState.RETIRING}),
    LifecycleState.FROZEN: frozenset({LifecycleState.RETIRING}),
    LifecycleState.RETIRING: frozenset({LifecycleState.RETIRED}),
    LifecycleState.RETIRED: frozenset(),
    LifecycleState.REJECTED: frozenset(),
    LifecycleState.DEFERRED: frozenset(),
    LifecycleState.WITHDRAWN: frozenset(),
})


def is_legal_transition(from_state: LifecycleState, to_state: LifecycleState) -> bool:
    return to_state in ALLOWED_TRANSITIONS[from_state]
