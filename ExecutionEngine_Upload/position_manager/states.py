"""PositionLifecycleState / PositionLifecycleTrigger and the frozen
transition table for position-level lifecycle tracking.

The graph is built to make every exit path the frozen Research Engine's
own code actually produces representable as an explicit edge -- verified
against turtle_backtest.py's exit-reason vocabulary: "stop" (before T1),
"stop_after_t1", "t1_half", "t2", "signal_loss". None of those paths are
computed here; this module only records that they occurred.

NEW -> OPEN is always the first transition regardless of whether the
first fill completes the intended entry size, so OPEN is never skipped;
a second, immediate transition then classifies it as PARTIALLY_FILLED or
FULLY_FILLED. T1_REACHED -> BREAKEVEN_ACTIVE is a distinct step (the T1
fill itself, then separate confirmation that the stop has actually moved
to breakeven), mirroring the two-fact structure of "half exited" and
"stop now at entry" being different pieces of information in practice.
"""

from enum import Enum
from types import MappingProxyType
from typing import Dict, FrozenSet, Mapping, Tuple


class PositionLifecycleState(Enum):
    NEW = "NEW"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FULLY_FILLED = "FULLY_FILLED"
    T1_REACHED = "T1_REACHED"
    BREAKEVEN_ACTIVE = "BREAKEVEN_ACTIVE"
    T2_REACHED = "T2_REACHED"
    STOP_TRIGGERED = "STOP_TRIGGERED"
    CLOSED = "CLOSED"
    ARCHIVED = "ARCHIVED"


class PositionLifecycleTrigger(Enum):
    FIRST_FILL = "FIRST_FILL"
    ENTRY_PARTIAL = "ENTRY_PARTIAL"
    ENTRY_COMPLETE = "ENTRY_COMPLETE"
    T1 = "T1"
    BREAKEVEN = "BREAKEVEN"
    T2 = "T2"
    STOP = "STOP"
    CLOSE = "CLOSE"
    COMPLETE_CLOSE = "COMPLETE_CLOSE"
    ARCHIVE = "ARCHIVE"


_S = PositionLifecycleState
_T = PositionLifecycleTrigger

_EDGES: Tuple[Tuple[PositionLifecycleState, PositionLifecycleTrigger, PositionLifecycleState], ...] = (
    (_S.NEW, _T.FIRST_FILL, _S.OPEN),

    (_S.OPEN, _T.ENTRY_PARTIAL, _S.PARTIALLY_FILLED),
    (_S.OPEN, _T.ENTRY_COMPLETE, _S.FULLY_FILLED),

    (_S.PARTIALLY_FILLED, _T.ENTRY_PARTIAL, _S.PARTIALLY_FILLED),
    (_S.PARTIALLY_FILLED, _T.ENTRY_COMPLETE, _S.FULLY_FILLED),
    (_S.PARTIALLY_FILLED, _T.CLOSE, _S.CLOSED),
    (_S.PARTIALLY_FILLED, _T.STOP, _S.STOP_TRIGGERED),

    (_S.FULLY_FILLED, _T.T1, _S.T1_REACHED),
    (_S.FULLY_FILLED, _T.STOP, _S.STOP_TRIGGERED),
    (_S.FULLY_FILLED, _T.CLOSE, _S.CLOSED),

    (_S.T1_REACHED, _T.BREAKEVEN, _S.BREAKEVEN_ACTIVE),

    (_S.BREAKEVEN_ACTIVE, _T.T2, _S.T2_REACHED),
    (_S.BREAKEVEN_ACTIVE, _T.STOP, _S.STOP_TRIGGERED),
    (_S.BREAKEVEN_ACTIVE, _T.CLOSE, _S.CLOSED),

    (_S.T2_REACHED, _T.COMPLETE_CLOSE, _S.CLOSED),
    (_S.STOP_TRIGGERED, _T.COMPLETE_CLOSE, _S.CLOSED),

    (_S.CLOSED, _T.ARCHIVE, _S.ARCHIVED),

    # ARCHIVED: terminal, no outgoing edges.
)

TRANSITION_TABLE: Mapping = MappingProxyType({(frm, trig): to for frm, trig, to in _EDGES})

_legal_by_state: Dict[PositionLifecycleState, FrozenSet[PositionLifecycleTrigger]] = {
    s: frozenset() for s in PositionLifecycleState
}
for _frm, _trig, _to in _EDGES:
    _legal_by_state[_frm] = _legal_by_state[_frm] | {_trig}
LEGAL_TRIGGERS_BY_STATE: Mapping = MappingProxyType({k: frozenset(v) for k, v in _legal_by_state.items()})

TERMINAL_STATES: FrozenSet[PositionLifecycleState] = frozenset(
    s for s in PositionLifecycleState if len(LEGAL_TRIGGERS_BY_STATE[s]) == 0
)


def is_legal(from_state: PositionLifecycleState, trigger: PositionLifecycleTrigger) -> bool:
    return (from_state, trigger) in TRANSITION_TABLE


def next_state(from_state: PositionLifecycleState, trigger: PositionLifecycleTrigger) -> PositionLifecycleState:
    return TRANSITION_TABLE[(from_state, trigger)]


_STATE_RANK: Mapping[PositionLifecycleState, int] = MappingProxyType({
    _S.NEW: 0,
    _S.OPEN: 1,
    _S.PARTIALLY_FILLED: 2,
    _S.FULLY_FILLED: 3,
    _S.T1_REACHED: 4,
    _S.BREAKEVEN_ACTIVE: 5,
    _S.T2_REACHED: 6,
    _S.STOP_TRIGGERED: 6,
    _S.CLOSED: 7,
    _S.ARCHIVED: 8,
})


def state_rank(state: PositionLifecycleState) -> int:
    return _STATE_RANK[state]


def trigger_min_target_rank(trigger: PositionLifecycleTrigger) -> int:
    targets = [to for (_frm, trig), to in TRANSITION_TABLE.items() if trig is trigger]
    return min(state_rank(t) for t in targets)
