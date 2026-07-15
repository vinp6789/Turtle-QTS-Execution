"""OrderLifecycleState / OrderLifecycleTrigger and the frozen transition
table for order-level lifecycle tracking within the Order Manager.

This is a SEPARATE state machine from Module 4's ExecutionStateMachine.
Module 4 tracks engine/position-level lifecycle -- one instance per
position. This tracks ONE ORDER's lifecycle, and a single OrderManager
multiplexes many of these simultaneously, one per client_order_id.

The cancel/fill race is modeled as explicit, legal edges (not errors):
a cancel in flight can be overtaken by a fill (CANCEL_PENDING -> FILLED /
PARTIALLY_FILLED), and a cancel already in flight when a fill lands can
still go on to confirm afterward (PARTIALLY_FILLED -> CANCELLED).
"""

from enum import Enum
from types import MappingProxyType
from typing import Dict, FrozenSet, Mapping, Tuple


class OrderLifecycleState(Enum):
    NEW = "NEW"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class OrderLifecycleTrigger(Enum):
    SUBMIT = "SUBMIT"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    REJECTED = "REJECTED"
    SUBMIT_FAILED = "SUBMIT_FAILED"
    PARTIAL_FILL = "PARTIAL_FILL"
    FULL_FILL = "FULL_FILL"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCEL_RETRY_ACKNOWLEDGED = "CANCEL_RETRY_ACKNOWLEDGED"
    CANCEL_CONFIRMED = "CANCEL_CONFIRMED"
    CANCEL_FAILED = "CANCEL_FAILED"
    EXPIRED = "EXPIRED"


_S = OrderLifecycleState
_T = OrderLifecycleTrigger

_EDGES: Tuple[Tuple[OrderLifecycleState, OrderLifecycleTrigger, OrderLifecycleState], ...] = (
    (_S.NEW, _T.SUBMIT, _S.SUBMITTED),

    (_S.SUBMITTED, _T.ACKNOWLEDGED, _S.ACKNOWLEDGED),
    (_S.SUBMITTED, _T.REJECTED, _S.REJECTED),
    (_S.SUBMITTED, _T.SUBMIT_FAILED, _S.FAILED),

    (_S.ACKNOWLEDGED, _T.PARTIAL_FILL, _S.PARTIALLY_FILLED),
    (_S.ACKNOWLEDGED, _T.FULL_FILL, _S.FILLED),
    (_S.ACKNOWLEDGED, _T.CANCEL_REQUESTED, _S.CANCEL_PENDING),
    (_S.ACKNOWLEDGED, _T.EXPIRED, _S.EXPIRED),

    (_S.PARTIALLY_FILLED, _T.PARTIAL_FILL, _S.PARTIALLY_FILLED),
    (_S.PARTIALLY_FILLED, _T.FULL_FILL, _S.FILLED),
    (_S.PARTIALLY_FILLED, _T.CANCEL_REQUESTED, _S.CANCEL_PENDING),
    (_S.PARTIALLY_FILLED, _T.EXPIRED, _S.EXPIRED),
    (_S.PARTIALLY_FILLED, _T.CANCEL_CONFIRMED, _S.CANCELLED),  # a cancel racing a fill finally confirms

    (_S.CANCEL_PENDING, _T.CANCEL_CONFIRMED, _S.CANCELLED),
    (_S.CANCEL_PENDING, _T.PARTIAL_FILL, _S.PARTIALLY_FILLED),  # fill lands while cancel in flight
    (_S.CANCEL_PENDING, _T.FULL_FILL, _S.FILLED),  # fully filled before cancel took effect
    (_S.CANCEL_PENDING, _T.CANCEL_RETRY_ACKNOWLEDGED, _S.CANCEL_PENDING),
    (_S.CANCEL_PENDING, _T.CANCEL_FAILED, _S.FAILED),

    # FILLED, CANCELLED, REJECTED, EXPIRED, FAILED: terminal, no outgoing edges.
)

TRANSITION_TABLE: Mapping = MappingProxyType({(frm, trig): to for frm, trig, to in _EDGES})

_legal_by_state: Dict[OrderLifecycleState, FrozenSet[OrderLifecycleTrigger]] = {
    s: frozenset() for s in OrderLifecycleState
}
for _frm, _trig, _to in _EDGES:
    _legal_by_state[_frm] = _legal_by_state[_frm] | {_trig}
LEGAL_TRIGGERS_BY_STATE: Mapping = MappingProxyType({k: frozenset(v) for k, v in _legal_by_state.items()})

TERMINAL_STATES: FrozenSet[OrderLifecycleState] = frozenset(
    s for s in OrderLifecycleState if len(LEGAL_TRIGGERS_BY_STATE[s]) == 0
)


def is_legal(from_state: OrderLifecycleState, trigger: OrderLifecycleTrigger) -> bool:
    return (from_state, trigger) in TRANSITION_TABLE


def next_state(from_state: OrderLifecycleState, trigger: OrderLifecycleTrigger) -> OrderLifecycleState:
    return TRANSITION_TABLE[(from_state, trigger)]


# Rank used to classify an illegal (current_state, trigger) pair as a
# stale/duplicate/out-of-order notification (safe to ignore) rather than a
# genuine inconsistency (must be surfaced). Terminal states are handled
# separately by the caller, since rank alone can't order CANCEL_PENDING
# against PARTIALLY_FILLED (they are branches, not a strict sequence).
_STATE_RANK: Mapping[OrderLifecycleState, int] = MappingProxyType({
    _S.NEW: 0,
    _S.SUBMITTED: 1,
    _S.ACKNOWLEDGED: 2,
    _S.PARTIALLY_FILLED: 3,
    _S.CANCEL_PENDING: 3,
    _S.FILLED: 4,
    _S.CANCELLED: 4,
    _S.REJECTED: 4,
    _S.EXPIRED: 4,
    _S.FAILED: 4,
})


def state_rank(state: OrderLifecycleState) -> int:
    return _STATE_RANK[state]


def trigger_min_target_rank(trigger: OrderLifecycleTrigger) -> int:
    targets = [to for (_frm, trig), to in TRANSITION_TABLE.items() if trig is trigger]
    return min(state_rank(t) for t in targets)
