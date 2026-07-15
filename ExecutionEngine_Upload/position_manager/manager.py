"""Position Manager: owns the complete lifecycle of live positions after
an order has begun filling. Pure bookkeeping -- it never calculates
conviction, position sizing, or stop/T1/T2 price levels (those are
supplied at position creation by a future Portfolio Manager, exactly as
the frozen Research Engine computes them once at entry and never
recomputes them in its exit logic). It never decides that a stop, T1, or
T2 has been reached -- that judgment belongs to future Stop Management /
Take Profit Management modules; this module only records the
consequence once told, via an already-normalized Module 5 Fill.

Never touches SigningBoundary. Never holds an ExchangeAdapter reference
at all -- every input (fills, mark prices) is supplied already-normalized
by whichever caller obtained it through Module 5.
"""

import dataclasses
import threading
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional, Set, Tuple

from event_store import Event, EventStore, EventType
from exchange_adapter import Fill, OrderSide, Symbol

from . import pnl
from .errors import (
    IllegalPositionTransitionError,
    PositionNotFoundError,
    PositionStateInconsistencyError,
    ReplayIntegrityError,
)
from .ids import make_id
from .snapshot import ClosedLeg, PositionSnapshot
from .states import (
    TERMINAL_STATES,
    PositionLifecycleState,
    PositionLifecycleTrigger,
    is_legal,
    next_state,
    state_rank,
    trigger_min_target_rank,
)

_EVENT_SOURCE_TAG = "position_manager"
_MAX_PM_ID_LENGTH = 60

_EXIT_TRIGGER_REASON = {
    PositionLifecycleTrigger.T1: "t1_half",
    PositionLifecycleTrigger.T2: "t2",
}


def _is_own_event(event: Event, pm_id: str) -> bool:
    return event.payload.get("source") == _EVENT_SOURCE_TAG and event.payload.get("pm_id") == pm_id


def _dec(value: Optional[str]) -> Optional[Decimal]:
    return Decimal(value) if value is not None else None


def _event_type_for_action(action: str, to_state: Optional[PositionLifecycleState]) -> EventType:
    # Best-fit categorization onto Module 3's closed EventType enum, same
    # spirit as Modules 4 and 6: the coarse category is cosmetic, the
    # payload's own action/trigger/from_state/to_state fields are
    # authoritative for replay.
    if action == "CREATE":
        return EventType.POSITION_OPENED
    if action == "ENTRY_FILL":
        return EventType.POSITION_UPDATED
    if action == "EXIT":
        if to_state is PositionLifecycleState.STOP_TRIGGERED:
            return EventType.STOP_UPDATED
        if to_state in (PositionLifecycleState.T1_REACHED, PositionLifecycleState.T2_REACHED):
            return EventType.TAKE_PROFIT_UPDATED
        return EventType.POSITION_CLOSED
    if action == "BREAKEVEN":
        return EventType.STOP_UPDATED
    if action == "COMPLETE_CLOSE":
        return EventType.POSITION_CLOSED
    if action == "ARCHIVE":
        return EventType.POSITION_UPDATED
    if action == "FUNDING":
        return EventType.POSITION_UPDATED
    return EventType.HEALTH_ALERT


class PositionManager:
    def __init__(self, store: EventStore, pm_id: str = "default"):
        if not isinstance(store, EventStore):
            raise TypeError(f"store must be an EventStore, got {type(store).__name__}")
        if not isinstance(pm_id, str) or not pm_id.strip():
            raise ValueError("pm_id must be a non-empty string")
        if len(pm_id) > _MAX_PM_ID_LENGTH:
            raise ValueError(f"pm_id exceeds {_MAX_PM_ID_LENGTH} characters")

        self._store = store
        self._pm_id = pm_id
        self._snapshots: Dict[str, PositionSnapshot] = {}
        self._closed_legs: Dict[str, list] = {}
        self._processed_fill_ids: Dict[str, Set[str]] = {}
        self._applied_event_ids: Set[int] = set()
        self._position_locks: Dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self._id_lock = threading.Lock()
        self._next_seq = 1

        for event in store.replay():
            if not _is_own_event(event, pm_id):
                continue
            self._apply_event(event)

    # -- lock management: one lock per position lifecycle --

    def _lock_for(self, position_id: str) -> threading.Lock:
        with self._locks_guard:
            lock = self._position_locks.get(position_id)
            if lock is None:
                lock = threading.Lock()
                self._position_locks[position_id] = lock
            return lock

    # -- deterministic id generation --

    def _next_id(self, suffix: str) -> Tuple[int, str]:
        with self._id_lock:
            seq = self._next_seq
            self._next_seq += 1
            return seq, make_id(self._pm_id, seq, suffix)

    # -- persistence --

    def _persist(
        self,
        action: str,
        position_id: str,
        seq: Optional[int],
        trigger: Optional[PositionLifecycleTrigger],
        from_state: Optional[PositionLifecycleState],
        to_state: Optional[PositionLifecycleState],
        details: Dict[str, Any],
        idempotency_key: str,
    ) -> Event:
        payload = {
            "source": _EVENT_SOURCE_TAG,
            "pm_id": self._pm_id,
            "seq": seq,
            "action": action,
            "position_id": position_id,
            "trigger": trigger.value if trigger is not None else None,
            "from_state": from_state.value if from_state is not None else None,
            "to_state": to_state.value if to_state is not None else None,
            "details": details,
        }
        event_type = _event_type_for_action(action, to_state)
        namespaced_key = f"{_EVENT_SOURCE_TAG}:{self._pm_id}:{idempotency_key}"
        return self._store.append(event_type, payload, idempotency_key=namespaced_key)

    def _apply_event(self, event: Event) -> Optional[PositionSnapshot]:
        if event.event_id in self._applied_event_ids:
            position_id = event.payload.get("position_id")
            return self._snapshots.get(position_id)
        self._applied_event_ids.add(event.event_id)

        action = event.payload.get("action")
        position_id = event.payload.get("position_id")
        seq = event.payload.get("seq")
        if seq is not None:
            self._next_seq = max(self._next_seq, int(seq) + 1)

        if action == "CREATE":
            details = event.payload["details"]
            snapshot = PositionSnapshot(
                position_id=position_id,
                lifecycle_state=PositionLifecycleState.NEW,
                symbol=Symbol(details["symbol"]),
                side=OrderSide(details["side"]),
                intended_quantity=Decimal(details["intended_quantity"]),
                filled_quantity=Decimal("0"),
                remaining_quantity=Decimal("0"),
                avg_entry_price=None,
                stop_price=Decimal(details["stop_price"]),
                stop_d=Decimal(details["stop_d"]),
                t1_price=Decimal(details["t1_price"]),
                t2_price=Decimal(details["t2_price"]),
                conviction=_dec(details.get("conviction")),
                realized_pnl=Decimal("0"),
                realized_r=Decimal("0"),
                fees_paid=Decimal("0"),
                funding_paid=Decimal("0"),
                created_at_utc=event.timestamp_utc,
                updated_at_utc=event.timestamp_utc,
            )
            self._snapshots[position_id] = snapshot
            self._closed_legs.setdefault(position_id, [])
            self._processed_fill_ids.setdefault(position_id, set())
            return snapshot

        existing = self._snapshots.get(position_id)
        if existing is None:
            raise ReplayIntegrityError(f"event {event.event_id}: update for unknown position_id={position_id!r}")

        if action in ("ENTRY_FILL", "EXIT", "BREAKEVEN", "COMPLETE_CLOSE", "ARCHIVE"):
            trigger = PositionLifecycleTrigger(event.payload["trigger"])
            from_state = PositionLifecycleState(event.payload["from_state"])
            to_state = PositionLifecycleState(event.payload["to_state"])
            if from_state != existing.lifecycle_state:
                raise ReplayIntegrityError(
                    f"event {event.event_id}: from_state {from_state.value} does not match "
                    f"reconstructed state {existing.lifecycle_state.value} for {position_id}"
                )
            if not is_legal(from_state, trigger) or next_state(from_state, trigger) != to_state:
                raise ReplayIntegrityError(f"event {event.event_id}: illegal recorded transition for {position_id}")

            details = event.payload.get("details", {})

            if action == "ENTRY_FILL":
                fill_id = details["fill_id"]
                self._processed_fill_ids.setdefault(position_id, set()).add(fill_id)
                new_avg = pnl.weighted_average_price(
                    existing.avg_entry_price, existing.filled_quantity,
                    Decimal(details["fill_price"]), Decimal(details["fill_quantity"]),
                )
                new_filled = existing.filled_quantity + Decimal(details["fill_quantity"])
                updated = dataclasses.replace(
                    existing,
                    lifecycle_state=to_state,
                    avg_entry_price=new_avg,
                    filled_quantity=new_filled,
                    remaining_quantity=new_filled,
                    fees_paid=existing.fees_paid + Decimal(details.get("fee", "0")),
                    updated_at_utc=event.timestamp_utc,
                )
            elif action == "EXIT":
                fill_id = details["fill_id"]
                self._processed_fill_ids.setdefault(position_id, set()).add(fill_id)
                qty_closed = Decimal(details["fill_quantity"])
                leg = ClosedLeg(
                    position_id=position_id,
                    symbol=existing.symbol.value,
                    r=Decimal(details["r"]),
                    pct=Decimal(details["pct"]),
                    reason=details["reason"],
                    conv=existing.conviction,
                    entry_at_utc=existing.created_at_utc,
                    exit_at_utc=event.timestamp_utc,
                    entry_px=existing.avg_entry_price,
                    exit_px=Decimal(details["fill_price"]),
                    stop_d=existing.stop_d,
                    quantity=qty_closed,
                    fee=Decimal(details.get("fee", "0")),
                    realized_pnl=Decimal(details["realized_pnl"]),
                )
                self._closed_legs.setdefault(position_id, []).append(leg)
                updated = dataclasses.replace(
                    existing,
                    lifecycle_state=to_state,
                    remaining_quantity=existing.remaining_quantity - qty_closed,
                    realized_pnl=existing.realized_pnl + leg.realized_pnl,
                    realized_r=existing.realized_r + leg.r,
                    fees_paid=existing.fees_paid + leg.fee,
                    updated_at_utc=event.timestamp_utc,
                )
            else:  # BREAKEVEN, COMPLETE_CLOSE, ARCHIVE -- pure state transitions
                updated = dataclasses.replace(existing, lifecycle_state=to_state, updated_at_utc=event.timestamp_utc)

            self._snapshots[position_id] = updated
            return updated

        if action == "FUNDING":
            details = event.payload.get("details", {})
            updated = dataclasses.replace(
                existing,
                funding_paid=existing.funding_paid + Decimal(details["amount"]),
                updated_at_utc=event.timestamp_utc,
            )
            self._snapshots[position_id] = updated
            return updated

        raise ReplayIntegrityError(f"event {event.event_id}: unknown action {action!r}")

    # -- shared staleness-aware transition application --

    def _try_transition(
        self, position_id: str, trigger: PositionLifecycleTrigger, current: PositionLifecycleState
    ) -> Optional[PositionLifecycleState]:
        """Returns the target state if legal, None if this should be
        treated as a stale/duplicate/out-of-order no-op, or raises
        PositionStateInconsistencyError for a genuine contradiction."""
        if is_legal(current, trigger):
            return next_state(current, trigger)
        if current in TERMINAL_STATES or state_rank(current) >= trigger_min_target_rank(trigger):
            return None
        raise PositionStateInconsistencyError(
            f"position_id={position_id}: trigger {trigger.value} is not legal from "
            f"{current.value} and is not recognizably stale"
        )

    # -- public: create position --

    def create_position(
        self,
        symbol: Symbol,
        side: OrderSide,
        intended_quantity: Decimal,
        stop_price: Decimal,
        stop_d: Decimal,
        t1_price: Decimal,
        t2_price: Decimal,
        conviction: Optional[Decimal] = None,
    ) -> PositionSnapshot:
        if intended_quantity <= 0:
            raise ValueError("intended_quantity must be positive")
        if stop_d <= 0:
            raise ValueError("stop_d must be positive")
        seq, position_id = self._next_id("position")
        lock = self._lock_for(position_id)
        with lock:
            details = {
                "symbol": symbol.value,
                "side": side.value,
                "intended_quantity": str(intended_quantity),
                "stop_price": str(stop_price),
                "stop_d": str(stop_d),
                "t1_price": str(t1_price),
                "t2_price": str(t2_price),
                "conviction": str(conviction) if conviction is not None else None,
            }
            event = self._persist("CREATE", position_id, seq, None, None, None, details, idempotency_key=position_id)
            return self._apply_event(event)

    # -- public: entry fill --

    def record_entry_fill(self, position_id: str, fill: Fill) -> PositionSnapshot:
        if not isinstance(fill, Fill):
            raise TypeError(f"fill must be a Fill, got {type(fill).__name__}")
        lock = self._lock_for(position_id)
        with lock:
            existing = self._snapshots.get(position_id)
            if existing is None:
                raise PositionNotFoundError(f"no position tracked with position_id={position_id!r}")
            if fill.fill_id in self._processed_fill_ids.get(position_id, set()):
                return existing
            if existing.lifecycle_state not in (
                PositionLifecycleState.NEW, PositionLifecycleState.OPEN, PositionLifecycleState.PARTIALLY_FILLED,
            ):
                raise IllegalPositionTransitionError(
                    f"cannot apply entry fill to position in state {existing.lifecycle_state.value}"
                )

            current = existing.lifecycle_state
            new_filled = existing.filled_quantity + fill.quantity

            # Step 1: NEW -> OPEN, unconditionally, on the first fill.
            if current is PositionLifecycleState.NEW:
                to_open = next_state(current, PositionLifecycleTrigger.FIRST_FILL)
                open_event = self._persist(
                    "ENTRY_FILL", position_id, None, PositionLifecycleTrigger.FIRST_FILL, current, to_open,
                    {"fill_id": f"{fill.fill_id}:open", "fill_price": str(fill.price), "fill_quantity": "0", "fee": "0"},
                    idempotency_key=f"{position_id}:open:{fill.fill_id}",
                )
                self._apply_event(open_event)
                current = to_open

            # Step 2: classify as PARTIALLY_FILLED or FULLY_FILLED for this fill's contribution.
            classify_trigger = (
                PositionLifecycleTrigger.ENTRY_COMPLETE if new_filled >= existing.intended_quantity
                else PositionLifecycleTrigger.ENTRY_PARTIAL
            )
            to_state = self._try_transition(position_id, classify_trigger, current)
            if to_state is None:
                return self._snapshots[position_id]

            details = {
                "fill_id": fill.fill_id, "fill_price": str(fill.price),
                "fill_quantity": str(fill.quantity), "fee": str(fill.fee),
            }
            event = self._persist(
                "ENTRY_FILL", position_id, None, classify_trigger, current, to_state, details,
                idempotency_key=f"{position_id}:entry:{fill.fill_id}",
            )
            return self._apply_event(event)

    # -- public: exits (T1 / T2 / STOP / CLOSE) --

    def record_exit(
        self, position_id: str, fill: Fill, trigger: PositionLifecycleTrigger, reason: Optional[str] = None
    ) -> PositionSnapshot:
        if not isinstance(fill, Fill):
            raise TypeError(f"fill must be a Fill, got {type(fill).__name__}")
        if trigger not in (
            PositionLifecycleTrigger.T1, PositionLifecycleTrigger.T2,
            PositionLifecycleTrigger.STOP, PositionLifecycleTrigger.CLOSE,
        ):
            raise ValueError(f"trigger must be T1, T2, STOP, or CLOSE, got {trigger}")
        lock = self._lock_for(position_id)
        with lock:
            existing = self._snapshots.get(position_id)
            if existing is None:
                raise PositionNotFoundError(f"no position tracked with position_id={position_id!r}")

            if fill.fill_id in self._processed_fill_ids.get(position_id, set()):
                return existing
            if existing.lifecycle_state in TERMINAL_STATES:
                self._processed_fill_ids.setdefault(position_id, set()).add(fill.fill_id)
                return existing

            current = existing.lifecycle_state
            to_state = self._try_transition(position_id, trigger, current)
            if to_state is None:
                self._processed_fill_ids.setdefault(position_id, set()).add(fill.fill_id)
                return existing

            if existing.avg_entry_price is None:
                raise PositionStateInconsistencyError(f"position {position_id} has no entry price yet")

            fraction = pnl.fraction_of_original(fill.quantity, existing.intended_quantity)
            r = pnl.leg_r_multiple(existing.avg_entry_price, fill.price, existing.stop_d, fraction, fill.fee, fill.quantity)
            pct = pnl.leg_pct(existing.avg_entry_price, fill.price, fraction)
            realized_pnl = pnl.leg_realized_pnl(existing.avg_entry_price, fill.price, fill.quantity, fill.fee)

            if trigger is PositionLifecycleTrigger.STOP:
                leg_reason = "stop_after_t1" if current is PositionLifecycleState.BREAKEVEN_ACTIVE else "stop_before_t1"
            elif trigger is PositionLifecycleTrigger.CLOSE:
                leg_reason = reason or "signal_loss"
            else:
                leg_reason = _EXIT_TRIGGER_REASON[trigger]

            details = {
                "fill_id": fill.fill_id, "fill_price": str(fill.price), "fill_quantity": str(fill.quantity),
                "fee": str(fill.fee), "r": str(r), "pct": str(pct), "reason": leg_reason,
                "realized_pnl": str(realized_pnl),
            }
            event = self._persist(
                "EXIT", position_id, None, trigger, current, to_state, details,
                idempotency_key=f"{position_id}:exit:{fill.fill_id}",
            )
            return self._apply_event(event)

    # -- public: pure state transitions (no fill involved) --

    def confirm_breakeven(self, position_id: str) -> PositionSnapshot:
        return self._pure_transition(position_id, PositionLifecycleTrigger.BREAKEVEN, "BREAKEVEN", "breakeven")

    def complete_close(self, position_id: str) -> PositionSnapshot:
        return self._pure_transition(position_id, PositionLifecycleTrigger.COMPLETE_CLOSE, "COMPLETE_CLOSE", "complete_close")

    def archive_position(self, position_id: str) -> PositionSnapshot:
        return self._pure_transition(position_id, PositionLifecycleTrigger.ARCHIVE, "ARCHIVE", "archive")

    def _pure_transition(
        self, position_id: str, trigger: PositionLifecycleTrigger, action: str, tag: str
    ) -> PositionSnapshot:
        lock = self._lock_for(position_id)
        with lock:
            existing = self._snapshots.get(position_id)
            if existing is None:
                raise PositionNotFoundError(f"no position tracked with position_id={position_id!r}")
            current = existing.lifecycle_state
            to_state = self._try_transition(position_id, trigger, current)
            if to_state is None:
                return existing
            event = self._persist(
                action, position_id, None, trigger, current, to_state, {},
                idempotency_key=f"{position_id}:{tag}",
            )
            return self._apply_event(event)

    # -- public: funding --

    def record_funding_payment(
        self, position_id: str, amount: Decimal, timestamp_utc: str, funding_id: str
    ) -> PositionSnapshot:
        lock = self._lock_for(position_id)
        with lock:
            existing = self._snapshots.get(position_id)
            if existing is None:
                raise PositionNotFoundError(f"no position tracked with position_id={position_id!r}")
            event = self._persist(
                "FUNDING", position_id, None, None, None, None,
                {"amount": str(amount), "timestamp_utc": timestamp_utc, "funding_id": funding_id},
                idempotency_key=f"{position_id}:funding:{funding_id}",
            )
            return self._apply_event(event)

    # -- public: queries --

    def get_position(self, position_id: str) -> PositionSnapshot:
        snapshot = self._snapshots.get(position_id)
        if snapshot is None:
            raise PositionNotFoundError(f"no position tracked with position_id={position_id!r}")
        return snapshot

    def get_closed_legs(self, position_id: str) -> Tuple[ClosedLeg, ...]:
        if position_id not in self._snapshots:
            raise PositionNotFoundError(f"no position tracked with position_id={position_id!r}")
        return tuple(self._closed_legs.get(position_id, []))

    def unrealized_pnl(self, position_id: str, mark_price: Decimal) -> Decimal:
        snapshot = self.get_position(position_id)
        if snapshot.avg_entry_price is None or snapshot.remaining_quantity <= 0:
            return Decimal("0")
        return pnl.unrealized_pnl(snapshot.avg_entry_price, mark_price, snapshot.remaining_quantity)

    def __repr__(self) -> str:
        return f"PositionManager(pm_id={self._pm_id!r}, tracked_positions={len(self._snapshots)})"

    __str__ = __repr__
