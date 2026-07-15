"""Execution State Machine: the single source of truth for execution
lifecycle state.

Explicit, finite, event-driven, deterministic. Every legal transition is
declared once in transitions.py; nothing here infers, guesses, or falls
back to a default. This module contains no business logic: it does not
decide WHEN a signal should be rejected, WHEN a kill switch should fire,
or what a fill means for capital -- it only enforces WHETHER a requested
state change is structurally legal from the current state, and durably
records it via the Event Store (Module 3) if so. No timers, no threads,
no exchange calls: it only reacts, synchronously, to explicit calls made
by other modules.

Integration note on EventType usage: see the module docstring in
transitions.py. In short -- Module 3's EventType enum is a coarse,
domain-level filing category, not an FSM-transition identifier, and this
module may not modify Module 3 to add one. Replay and recovery below
never interpret the coarse EventType; they reconstruct exact history
purely from each event's own payload fields.
"""

import threading
from typing import Any, Dict, FrozenSet, Optional

from event_store import Event, EventStore, EventType

from .errors import IllegalTransitionError, ReplayIntegrityError, UnknownTriggerError
from .states import State, Trigger, TransitionResult
from .transitions import LEGAL_TRIGGERS_BY_STATE, TRIGGER_EVENT_TYPE, is_legal, next_state

_EVENT_SOURCE_TAG = "execution_state_machine"
_MAX_MACHINE_ID_LENGTH = 60
_MAX_REQUEST_ID_LENGTH = 60


def _namespaced_key(machine_id: str, request_id: str) -> str:
    """Combine machine_id and request_id into a single idempotency key
    with no ambiguity between different (machine_id, request_id) pairs.

    Naive "tag:machine_id:request_id" concatenation would let
    machine_id="A:B" + request_id="C" collide with machine_id="A" +
    request_id="B:C" -- the same field-boundary-confusion class Module 2's
    domain separation exists to prevent. Length-prefixing each variable
    component removes the ambiguity regardless of what characters either
    string contains.
    """
    return f"{_EVENT_SOURCE_TAG}:{len(machine_id)}:{machine_id}:{len(request_id)}:{request_id}"


def _is_own_event(event: Event, machine_id: str) -> bool:
    return event.payload.get("source") == _EVENT_SOURCE_TAG and event.payload.get("machine_id") == machine_id


def _parse_state(raw: Any, event_id: int, field: str) -> State:
    try:
        return State(raw)
    except ValueError as exc:
        raise ReplayIntegrityError(f"event {event_id}: payload.{field} = {raw!r} is not a known State") from exc


def _parse_trigger(raw: Any, event_id: int) -> Trigger:
    try:
        return Trigger(raw)
    except ValueError as exc:
        raise ReplayIntegrityError(f"event {event_id}: payload.trigger = {raw!r} is not a known Trigger") from exc


class ExecutionStateMachine:
    """Single source of truth for one execution lifecycle.

    State can only ever change through transition() -- there is no other
    public mutator, and `current_state` is a read-only property.

    `machine_id` partitions the shared Event Store between independent
    state-machine instances (e.g. one per symbol, or one engine-wide).
    Instances that are meant to be independent MUST use distinct
    machine_id values, or their histories and idempotency keys will
    collide by design.
    """

    def __init__(self, store: EventStore, machine_id: str = "default"):
        if not isinstance(machine_id, str) or not machine_id.strip():
            raise ValueError("machine_id must be a non-empty string")
        if len(machine_id) > _MAX_MACHINE_ID_LENGTH:
            raise ValueError(f"machine_id exceeds {_MAX_MACHINE_ID_LENGTH} characters")

        self._store = store
        self._machine_id = machine_id
        self._current_state = State.INITIALIZING
        self._lock = threading.Lock()

        for event in store.replay():
            if not _is_own_event(event, machine_id):
                continue

            trigger = _parse_trigger(event.payload.get("trigger"), event.event_id)
            from_state = _parse_state(event.payload.get("from_state"), event.event_id, "from_state")
            to_state = _parse_state(event.payload.get("to_state"), event.event_id, "to_state")

            if from_state != self._current_state:
                raise ReplayIntegrityError(
                    f"event {event.event_id}: recorded from_state {from_state.value} does not match "
                    f"reconstructed current state {self._current_state.value} for machine_id={machine_id!r}"
                )
            if not is_legal(from_state, trigger) or next_state(from_state, trigger) != to_state:
                raise ReplayIntegrityError(
                    f"event {event.event_id}: transition {from_state.value} --{trigger.value}--> "
                    f"{to_state.value} is not a legal edge in the current transition table"
                )
            self._current_state = to_state

    @property
    def current_state(self) -> State:
        return self._current_state

    @property
    def machine_id(self) -> str:
        return self._machine_id

    def legal_triggers(self) -> FrozenSet[Trigger]:
        """The set of triggers that would currently succeed. Pure
        introspection -- does not validate, reserve, or record anything."""
        return LEGAL_TRIGGERS_BY_STATE[self._current_state]

    def transition(
        self,
        trigger: Trigger,
        request_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> TransitionResult:
        """Attempt a state transition.

        Idempotent: if `request_id` has already been processed by this
        machine instance, the original outcome is returned unchanged --
        no re-validation against the current state, no new event, no
        mutation. This makes it safe for a caller to retry the same
        request after a crash without risking a duplicate or an
        inconsistent re-evaluation of something that already happened.

        Otherwise, (current_state, trigger) is validated against the
        frozen transition table BEFORE any mutation. An illegal pair
        raises IllegalTransitionError with nothing recorded and nothing
        changed. A legal pair is durably recorded via the Event Store
        first; only after that succeeds is in-memory state updated -- so
        a failure while recording (e.g. Module 3 rejecting a malformed
        `context`) also leaves nothing changed.
        """
        if not isinstance(trigger, Trigger):
            raise UnknownTriggerError(f"trigger must be a Trigger member, got {type(trigger).__name__}")
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must be a non-empty string")
        if len(request_id) > _MAX_REQUEST_ID_LENGTH:
            raise ValueError(f"request_id exceeds {_MAX_REQUEST_ID_LENGTH} characters")
        if context is not None and not isinstance(context, dict):
            raise TypeError(f"context must be a dict or None, got {type(context).__name__}")
        context = context or {}

        # Namespaced so this machine's request_ids only need to be unique
        # to itself, never across other modules or other machine_id
        # partitions sharing the same underlying Event Store.
        namespaced_key = _namespaced_key(self._machine_id, request_id)

        # The whole read-check-validate-append-mutate sequence is one
        # critical section. Without this, two concurrent callers with
        # different request_ids but the same legal trigger could both
        # pass validation against the same current_state before either
        # persists, producing two events that both (correctly, at the
        # time) claim the same from_state -- which would then fail replay
        # with ReplayIntegrityError on the next restart, even though
        # neither call was individually illegal.
        with self._lock:
            existing = self._store.get_by_idempotency_key(namespaced_key)
            if existing is not None:
                if not _is_own_event(existing, self._machine_id):
                    raise ValueError(
                        f"request_id {request_id!r} collides with a non-FSM event under the same "
                        "namespaced idempotency key -- this should be structurally impossible"
                    )
                return self._result_from_event(existing, request_id, replayed=True)

            from_state = self._current_state
            if not is_legal(from_state, trigger):
                raise IllegalTransitionError(f"trigger {trigger.value} is not legal from state {from_state.value}")
            to_state = next_state(from_state, trigger)

            payload = {
                "source": _EVENT_SOURCE_TAG,
                "machine_id": self._machine_id,
                "trigger": trigger.value,
                "from_state": from_state.value,
                "to_state": to_state.value,
                "context": context,
            }
            event = self._store.append(TRIGGER_EVENT_TYPE[trigger], payload, idempotency_key=namespaced_key)

            # Mutation happens only after the event is durably recorded,
            # and only while still holding the lock.
            self._current_state = to_state
            return self._result_from_event(event, request_id, replayed=False)

    def _result_from_event(self, event: Event, request_id: str, replayed: bool) -> TransitionResult:
        trigger = _parse_trigger(event.payload.get("trigger"), event.event_id)
        from_state = _parse_state(event.payload.get("from_state"), event.event_id, "from_state")
        to_state = _parse_state(event.payload.get("to_state"), event.event_id, "to_state")
        return TransitionResult(
            event_id=event.event_id,
            trigger=trigger,
            from_state=from_state,
            to_state=to_state,
            timestamp_utc=event.timestamp_utc,
            request_id=request_id,
            context=event.payload.get("context", {}),
            replayed=replayed,
        )

    def __repr__(self) -> str:
        return f"ExecutionStateMachine(machine_id={self._machine_id!r}, current_state={self._current_state.value})"

    __str__ = __repr__
