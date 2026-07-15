"""The frozen, explicit transition table for the Execution State Machine.

Every legal (from_state, trigger) -> to_state edge is declared here, once,
as an explicit tuple. There is no pattern-matching, wildcard, or implicit
fallback: a pair not listed here is illegal, full stop. Built once at
import time and wrapped in MappingProxyType so nothing -- including this
module's own code -- can mutate it at runtime.

Design notes on the graph itself (structural, not business logic):
  - Kill-switch triggers (SOFT_KILL_TRIGGERED / HARD_KILL_TRIGGERED /
    EMERGENCY_KILL_TRIGGERED) are legal from every "live" state, matching
    the frozen architecture's requirement that a kill switch must be able
    to fire regardless of what the engine is currently doing.
  - Recovery from SOFT_KILL or HARD_KILL always routes back through
    RECONCILING (via RESUME), never directly to READY -- this mirrors the
    architecture's mandatory "reconcile before resuming trading" gate.
  - EMERGENCY_KILL has exactly one legal exit: SHUTDOWN -> STOPPED. This
    matches Module 2's SigningBoundary.revoke() being one-way: an
    emergency kill is a one-way trip requiring a fresh process, not a
    resumable state.
  - SHUTDOWN is only legal from states where nothing is at risk in
    flight (INITIALIZING, RECONCILING, READY, FLAT, and the three kill
    states) -- it is deliberately NOT legal from SIGNAL_PENDING,
    ORDER_PENDING, PARTIALLY_FILLED, POSITION_OPEN, or POSITION_CLOSING,
    so nothing can shut down out from under an order or an open position
    without going through a kill tier first.
  - STOPPED is terminal: no outgoing edges, by omission from the table.
"""

from types import MappingProxyType
from typing import Dict, FrozenSet, Mapping, Tuple

from event_store import EventType

from .states import State, Trigger

_S = State
_T = Trigger

# (from_state, trigger, to_state)
_EDGES: Tuple[Tuple[State, Trigger, State], ...] = (
    (_S.INITIALIZING, _T.STARTED, _S.RECONCILING),
    (_S.INITIALIZING, _T.EMERGENCY_KILL_TRIGGERED, _S.EMERGENCY_KILL),
    (_S.INITIALIZING, _T.SHUTDOWN, _S.STOPPED),

    (_S.RECONCILING, _T.RECONCILED, _S.READY),
    (_S.RECONCILING, _T.RECONCILIATION_FAILED, _S.SOFT_KILL),
    (_S.RECONCILING, _T.SOFT_KILL_TRIGGERED, _S.SOFT_KILL),
    (_S.RECONCILING, _T.HARD_KILL_TRIGGERED, _S.HARD_KILL),
    (_S.RECONCILING, _T.EMERGENCY_KILL_TRIGGERED, _S.EMERGENCY_KILL),
    (_S.RECONCILING, _T.SHUTDOWN, _S.STOPPED),

    (_S.READY, _T.SIGNAL_RECEIVED, _S.SIGNAL_PENDING),
    (_S.READY, _T.SOFT_KILL_TRIGGERED, _S.SOFT_KILL),
    (_S.READY, _T.HARD_KILL_TRIGGERED, _S.HARD_KILL),
    (_S.READY, _T.EMERGENCY_KILL_TRIGGERED, _S.EMERGENCY_KILL),
    (_S.READY, _T.SHUTDOWN, _S.STOPPED),

    (_S.SIGNAL_PENDING, _T.ORDER_PLACED, _S.ORDER_PENDING),
    (_S.SIGNAL_PENDING, _T.SIGNAL_REJECTED, _S.READY),
    (_S.SIGNAL_PENDING, _T.SOFT_KILL_TRIGGERED, _S.SOFT_KILL),
    (_S.SIGNAL_PENDING, _T.HARD_KILL_TRIGGERED, _S.HARD_KILL),
    (_S.SIGNAL_PENDING, _T.EMERGENCY_KILL_TRIGGERED, _S.EMERGENCY_KILL),

    (_S.ORDER_PENDING, _T.PARTIAL_FILL_RECEIVED, _S.PARTIALLY_FILLED),
    (_S.ORDER_PENDING, _T.FULLY_FILLED, _S.POSITION_OPEN),
    (_S.ORDER_PENDING, _T.ORDER_REJECTED, _S.READY),
    (_S.ORDER_PENDING, _T.ORDER_CANCELLED, _S.READY),
    (_S.ORDER_PENDING, _T.SOFT_KILL_TRIGGERED, _S.SOFT_KILL),
    (_S.ORDER_PENDING, _T.HARD_KILL_TRIGGERED, _S.HARD_KILL),
    (_S.ORDER_PENDING, _T.EMERGENCY_KILL_TRIGGERED, _S.EMERGENCY_KILL),

    (_S.PARTIALLY_FILLED, _T.PARTIAL_FILL_RECEIVED, _S.PARTIALLY_FILLED),
    (_S.PARTIALLY_FILLED, _T.REMAINDER_FILLED, _S.POSITION_OPEN),
    (_S.PARTIALLY_FILLED, _T.SOFT_KILL_TRIGGERED, _S.SOFT_KILL),
    (_S.PARTIALLY_FILLED, _T.HARD_KILL_TRIGGERED, _S.HARD_KILL),
    (_S.PARTIALLY_FILLED, _T.EMERGENCY_KILL_TRIGGERED, _S.EMERGENCY_KILL),

    (_S.POSITION_OPEN, _T.STOP_ADJUSTED, _S.POSITION_OPEN),
    (_S.POSITION_OPEN, _T.PARTIAL_TAKE_PROFIT_FILLED, _S.POSITION_OPEN),
    (_S.POSITION_OPEN, _T.CLOSE_INITIATED, _S.POSITION_CLOSING),
    (_S.POSITION_OPEN, _T.SOFT_KILL_TRIGGERED, _S.SOFT_KILL),
    (_S.POSITION_OPEN, _T.HARD_KILL_TRIGGERED, _S.HARD_KILL),
    (_S.POSITION_OPEN, _T.EMERGENCY_KILL_TRIGGERED, _S.EMERGENCY_KILL),

    (_S.POSITION_CLOSING, _T.PARTIAL_CLOSE_FILLED, _S.POSITION_CLOSING),
    (_S.POSITION_CLOSING, _T.CLOSE_COMPLETED, _S.FLAT),
    (_S.POSITION_CLOSING, _T.SOFT_KILL_TRIGGERED, _S.SOFT_KILL),
    (_S.POSITION_CLOSING, _T.HARD_KILL_TRIGGERED, _S.HARD_KILL),
    (_S.POSITION_CLOSING, _T.EMERGENCY_KILL_TRIGGERED, _S.EMERGENCY_KILL),

    (_S.FLAT, _T.READY_FOR_NEXT, _S.READY),
    (_S.FLAT, _T.SOFT_KILL_TRIGGERED, _S.SOFT_KILL),
    (_S.FLAT, _T.HARD_KILL_TRIGGERED, _S.HARD_KILL),
    (_S.FLAT, _T.EMERGENCY_KILL_TRIGGERED, _S.EMERGENCY_KILL),
    (_S.FLAT, _T.SHUTDOWN, _S.STOPPED),

    (_S.SOFT_KILL, _T.RESUME, _S.RECONCILING),
    (_S.SOFT_KILL, _T.HARD_KILL_TRIGGERED, _S.HARD_KILL),
    (_S.SOFT_KILL, _T.EMERGENCY_KILL_TRIGGERED, _S.EMERGENCY_KILL),
    (_S.SOFT_KILL, _T.SHUTDOWN, _S.STOPPED),

    (_S.HARD_KILL, _T.FLATTEN_FILL_RECEIVED, _S.HARD_KILL),
    (_S.HARD_KILL, _T.RESUME, _S.RECONCILING),
    (_S.HARD_KILL, _T.EMERGENCY_KILL_TRIGGERED, _S.EMERGENCY_KILL),
    (_S.HARD_KILL, _T.SHUTDOWN, _S.STOPPED),

    (_S.EMERGENCY_KILL, _T.SHUTDOWN, _S.STOPPED),

    # STOPPED: terminal, no outgoing edges.
)

TRANSITION_TABLE: Mapping = MappingProxyType({(frm, trig): to for frm, trig, to in _EDGES})

_legal_by_state: Dict[State, FrozenSet[Trigger]] = {s: frozenset() for s in State}
for _frm, _trig, _to in _EDGES:
    _legal_by_state[_frm] = _legal_by_state[_frm] | {_trig}
LEGAL_TRIGGERS_BY_STATE: Mapping = MappingProxyType({k: frozenset(v) for k, v in _legal_by_state.items()})


def is_legal(from_state: State, trigger: Trigger) -> bool:
    return (from_state, trigger) in TRANSITION_TABLE


def next_state(from_state: State, trigger: Trigger) -> State:
    return TRANSITION_TABLE[(from_state, trigger)]


# Each trigger is filed under the single closest-fitting EventType from
# Module 3's closed, frozen enum, which was not designed with per-trigger
# FSM granularity in mind and may not be modified to add one. This mapping
# is a coarse filing category ONLY -- machine.py's replay and recovery
# logic never relies on it; they reconstruct exact history purely from
# each event's own payload (source, trigger, from_state, to_state), which
# is what makes replay correctness independent of this categorization.
TRIGGER_EVENT_TYPE: Mapping = MappingProxyType({
    _T.STARTED: EventType.SYSTEM_STARTED,
    _T.RECONCILED: EventType.POSITION_UPDATED,
    _T.RECONCILIATION_FAILED: EventType.HEALTH_ALERT,
    _T.SIGNAL_RECEIVED: EventType.ORDER_SUBMITTED,
    _T.SIGNAL_REJECTED: EventType.ORDER_CANCELLED,
    _T.ORDER_PLACED: EventType.ORDER_SUBMITTED,
    _T.ORDER_REJECTED: EventType.ORDER_CANCELLED,
    _T.ORDER_CANCELLED: EventType.ORDER_CANCELLED,
    _T.PARTIAL_FILL_RECEIVED: EventType.ORDER_FILLED,
    _T.FULLY_FILLED: EventType.POSITION_OPENED,
    _T.REMAINDER_FILLED: EventType.POSITION_OPENED,
    _T.STOP_ADJUSTED: EventType.STOP_UPDATED,
    _T.PARTIAL_TAKE_PROFIT_FILLED: EventType.TAKE_PROFIT_UPDATED,
    _T.CLOSE_INITIATED: EventType.POSITION_UPDATED,
    _T.PARTIAL_CLOSE_FILLED: EventType.ORDER_FILLED,
    _T.CLOSE_COMPLETED: EventType.POSITION_CLOSED,
    _T.READY_FOR_NEXT: EventType.POSITION_UPDATED,
    _T.SOFT_KILL_TRIGGERED: EventType.KILL_SWITCH_TRIGGERED,
    _T.HARD_KILL_TRIGGERED: EventType.KILL_SWITCH_TRIGGERED,
    _T.EMERGENCY_KILL_TRIGGERED: EventType.KILL_SWITCH_TRIGGERED,
    _T.FLATTEN_FILL_RECEIVED: EventType.ORDER_FILLED,
    _T.RESUME: EventType.POSITION_UPDATED,
    _T.SHUTDOWN: EventType.SYSTEM_STOPPED,
})

assert set(TRIGGER_EVENT_TYPE.keys()) == set(Trigger), "every Trigger must have an EventType mapping"
