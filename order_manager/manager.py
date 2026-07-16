"""Order Manager: owns the lifecycle of orders after a strategy has
already decided to trade. No exchange-specific code, no position sizing,
no trading decisions -- it only executes exactly what it is told (via
place_order/amend_order/cancel_order/cancel_all) and keeps a durable,
replayable record of what happened to each order.

Communicates with the exchange ONLY through Module 5's typed
ExchangeAdapter interface -- never with SigningBoundary, never with any
exchange-native shape. All mutations persist through Module 3's Event
Store before any exchange call is made, and successful order-lifecycle
milestones drive Module 4's ExecutionStateMachine using its existing
triggers (ORDER_PLACED, ORDER_REJECTED, ORDER_CANCELLED,
PARTIAL_FILL_RECEIVED, FULLY_FILLED, REMAINDER_FILLED).

Integration note: Module 4's transition table has no edge for "a cancel
confirms after the order was already partially filled" (there is no
PARTIALLY_FILLED -> READY-equivalent edge). This Order Manager's own
order-lifecycle tracking remains fully correct and durable in that case
regardless; it simply does not attempt to advance Module 4 for it. See
_drive_execution_sm.
"""

import dataclasses
import hashlib
import threading
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional, Set, Tuple, Union

from event_store import Event, EventStore, EventType
from execution_state_machine import ExecutionStateMachine
from execution_state_machine import IllegalTransitionError as ExecutionIllegalTransitionError
from execution_state_machine import Trigger as ExecutionTrigger
from exchange_adapter import (
    AmendRequest,
    CancelAllRequest,
    CancelRequest,
    ExchangeAdapter,
    ExchangeAdapterError,
    Fill,
    Order,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Symbol,
    TimeInForce,
)

from .errors import (
    IllegalOrderTransitionError,
    OrderManagerError,
    OrderNotFoundError,
    OrderStateInconsistencyError,
    ReplayIntegrityError,
)
from .ids import make_id
from .snapshot import OrderSnapshot
from .states import (
    TERMINAL_STATES,
    OrderLifecycleState,
    OrderLifecycleTrigger,
    is_legal,
    next_state,
    state_rank,
    trigger_min_target_rank,
)

_EVENT_SOURCE_TAG = "order_manager"
_MAX_OM_ID_LENGTH = 60

_STATUS_TO_TRIGGER = {
    OrderStatus.ACKNOWLEDGED: OrderLifecycleTrigger.ACKNOWLEDGED,
    OrderStatus.CANCELLED: OrderLifecycleTrigger.CANCEL_CONFIRMED,
    OrderStatus.REJECTED: OrderLifecycleTrigger.REJECTED,
}


def _is_own_event(event: Event, om_id: str) -> bool:
    return event.payload.get("source") == _EVENT_SOURCE_TAG and event.payload.get("om_id") == om_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dec(value: Optional[str]) -> Optional[Decimal]:
    return Decimal(value) if value is not None else None


def _event_type_for_action(action: str, to_state: Optional[OrderLifecycleState]) -> EventType:
    # Best-fit categorization onto Module 3's closed EventType enum, same
    # spirit as Module 4: the coarse category is cosmetic, the payload's
    # own action/trigger/from_state/to_state fields are authoritative for
    # replay -- see _apply_event.
    if action == "SUBMIT":
        return EventType.ORDER_SUBMITTED
    if action == "FILL":
        return EventType.ORDER_FILLED
    if action in ("AMEND_REQUESTED", "AMEND"):
        return EventType.POSITION_UPDATED
    if action in ("CANCEL_ALL_REQUESTED",):
        return EventType.ORDER_CANCELLED
    if action == "STATUS_UPDATE":
        if to_state is OrderLifecycleState.ACKNOWLEDGED:
            return EventType.ORDER_ACKNOWLEDGED
        if to_state in (
            OrderLifecycleState.CANCELLED,
            OrderLifecycleState.REJECTED,
            OrderLifecycleState.EXPIRED,
            OrderLifecycleState.FAILED,
        ):
            return EventType.ORDER_CANCELLED
        return EventType.ORDER_ACKNOWLEDGED
    return EventType.HEALTH_ALERT


class OrderManager:
    def __init__(
        self,
        adapter: ExchangeAdapter,
        store: EventStore,
        execution_state_machine: ExecutionStateMachine,
        om_id: str = "default",
    ):
        if not isinstance(adapter, ExchangeAdapter):
            raise TypeError(f"adapter must be an ExchangeAdapter, got {type(adapter).__name__}")
        if not isinstance(store, EventStore):
            raise TypeError(f"store must be an EventStore, got {type(store).__name__}")
        if not isinstance(execution_state_machine, ExecutionStateMachine):
            raise TypeError(
                f"execution_state_machine must be an ExecutionStateMachine, got "
                f"{type(execution_state_machine).__name__}"
            )
        if not isinstance(om_id, str) or not om_id.strip():
            raise ValueError("om_id must be a non-empty string")
        if len(om_id) > _MAX_OM_ID_LENGTH:
            raise ValueError(f"om_id exceeds {_MAX_OM_ID_LENGTH} characters")

        self._adapter = adapter
        self._store = store
        self._execution_sm = execution_state_machine
        self._om_id = om_id

        self._snapshots: Dict[str, OrderSnapshot] = {}
        self._processed_fill_ids: Dict[str, Set[str]] = {}
        self._applied_event_ids: Set[int] = set()
        self._order_locks: Dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self._id_lock = threading.Lock()
        self._next_seq = 1

        for event in store.replay():
            if not _is_own_event(event, om_id):
                continue
            self._apply_event(event)

    # -- lock management: one lock per order lifecycle --

    def _lock_for(self, client_order_id: str) -> threading.Lock:
        with self._locks_guard:
            lock = self._order_locks.get(client_order_id)
            if lock is None:
                lock = threading.Lock()
                self._order_locks[client_order_id] = lock
            return lock

    # -- deterministic id generation --

    def _next_id(self, suffix: str) -> Tuple[int, str]:
        with self._id_lock:
            seq = self._next_seq
            self._next_seq += 1
            return seq, make_id(self._om_id, seq, suffix)

    # -- persistence --

    def _persist(
        self,
        action: str,
        client_order_id: str,
        seq: Optional[int],
        trigger: Optional[OrderLifecycleTrigger],
        from_state: Optional[OrderLifecycleState],
        to_state: Optional[OrderLifecycleState],
        details: Dict[str, Any],
        idempotency_key: str,
    ) -> Event:
        payload = {
            "source": _EVENT_SOURCE_TAG,
            "om_id": self._om_id,
            "seq": seq,
            "action": action,
            "client_order_id": client_order_id,
            "trigger": trigger.value if trigger is not None else None,
            "from_state": from_state.value if from_state is not None else None,
            "to_state": to_state.value if to_state is not None else None,
            "details": details,
        }
        event_type = _event_type_for_action(action, to_state)
        namespaced_key = f"{_EVENT_SOURCE_TAG}:{self._om_id}:{idempotency_key}"
        return self._store.append(event_type, payload, idempotency_key=namespaced_key)

    def _apply_event(self, event: Event) -> Optional[OrderSnapshot]:
        """Idempotent-safe application of one persisted event to in-memory
        state. Used identically for replay AND for the live path (called
        right after a successful _persist), so a duplicate append that
        hits Module 3's idempotency cache and returns an ALREADY-APPLIED
        event is never double-applied here."""
        if event.event_id in self._applied_event_ids:
            client_order_id = event.payload.get("client_order_id")
            return self._snapshots.get(client_order_id)
        self._applied_event_ids.add(event.event_id)

        action = event.payload.get("action")
        client_order_id = event.payload.get("client_order_id")
        seq = event.payload.get("seq")
        if seq is not None:
            self._next_seq = max(self._next_seq, int(seq) + 1)

        if action == "SUBMIT":
            details = event.payload.get("details", {})
            snapshot = OrderSnapshot(
                client_order_id=client_order_id,
                lifecycle_state=OrderLifecycleState.SUBMITTED,
                exchange_order_id=None,
                symbol=Symbol(details["symbol"]),
                side=OrderSide(details["side"]),
                order_type=OrderType(details["order_type"]),
                quantity=Decimal(details["quantity"]),
                filled_quantity=Decimal("0"),
                limit_price=_dec(details.get("limit_price")),
                time_in_force=TimeInForce(details["time_in_force"]),
                reduce_only=details["reduce_only"],
                created_at_utc=event.timestamp_utc,
                updated_at_utc=event.timestamp_utc,
            )
            self._snapshots[client_order_id] = snapshot
            self._processed_fill_ids.setdefault(client_order_id, set())
            return snapshot

        if action == "CANCEL_ALL_REQUESTED" or action == "AMEND_REQUESTED":
            # Pure intent record: durably consumes the id sequence before
            # any adapter call, but does not itself change any snapshot.
            return self._snapshots.get(client_order_id)

        existing = self._snapshots.get(client_order_id)
        if existing is None:
            raise ReplayIntegrityError(
                f"event {event.event_id}: update for unknown client_order_id={client_order_id!r}"
            )

        if action in ("STATUS_UPDATE", "FILL"):
            trigger = OrderLifecycleTrigger(event.payload["trigger"])
            from_state = OrderLifecycleState(event.payload["from_state"])
            to_state = OrderLifecycleState(event.payload["to_state"])
            if from_state != existing.lifecycle_state:
                raise ReplayIntegrityError(
                    f"event {event.event_id}: from_state {from_state.value} does not match "
                    f"reconstructed state {existing.lifecycle_state.value} for {client_order_id}"
                )
            if not is_legal(from_state, trigger) or next_state(from_state, trigger) != to_state:
                raise ReplayIntegrityError(
                    f"event {event.event_id}: illegal recorded transition for {client_order_id}"
                )
            details = event.payload.get("details", {})
            if action == "FILL":
                fill_id = details["fill_id"]
                self._processed_fill_ids.setdefault(client_order_id, set()).add(fill_id)
                new_filled = existing.filled_quantity + Decimal(details["fill_quantity"])
                updated = dataclasses.replace(
                    existing,
                    lifecycle_state=to_state,
                    filled_quantity=new_filled,
                    updated_at_utc=event.timestamp_utc,
                )
            else:
                updated = dataclasses.replace(
                    existing,
                    lifecycle_state=to_state,
                    exchange_order_id=details.get("exchange_order_id") or existing.exchange_order_id,
                    reject_reason=details.get("reject_reason") or existing.reject_reason,
                    updated_at_utc=event.timestamp_utc,
                )
            self._snapshots[client_order_id] = updated
            return updated

        if action == "AMEND":
            details = event.payload.get("details", {})
            updated = dataclasses.replace(
                existing,
                quantity=_dec(details.get("new_quantity")) or existing.quantity,
                limit_price=_dec(details.get("new_limit_price")) if "new_limit_price" in details else existing.limit_price,
                updated_at_utc=event.timestamp_utc,
            )
            self._snapshots[client_order_id] = updated
            return updated

        raise ReplayIntegrityError(f"event {event.event_id}: unknown action {action!r}")

    # -- Execution State Machine integration --

    def _drive_execution_sm(
        self,
        client_order_id: str,
        trigger: Union[str, OrderLifecycleTrigger],
        from_state: Optional[OrderLifecycleState],
        snapshot: OrderSnapshot,
    ) -> None:
        exec_trigger: Optional[ExecutionTrigger] = None
        if trigger == "SUBMIT":
            exec_trigger = ExecutionTrigger.ORDER_PLACED
        elif trigger is OrderLifecycleTrigger.REJECTED:
            exec_trigger = ExecutionTrigger.ORDER_REJECTED
        elif trigger is OrderLifecycleTrigger.PARTIAL_FILL:
            exec_trigger = ExecutionTrigger.PARTIAL_FILL_RECEIVED
        elif trigger is OrderLifecycleTrigger.FULL_FILL:
            exec_trigger = (
                ExecutionTrigger.REMAINDER_FILLED
                if from_state is OrderLifecycleState.PARTIALLY_FILLED
                else ExecutionTrigger.FULLY_FILLED
            )
        elif (
            trigger is OrderLifecycleTrigger.CANCEL_CONFIRMED
            and from_state is OrderLifecycleState.CANCEL_PENDING
            and snapshot.filled_quantity == 0
        ):
            exec_trigger = ExecutionTrigger.ORDER_CANCELLED
        # SUBMIT_FAILED, CANCEL_FAILED, EXPIRED, and CANCEL_CONFIRMED after
        # a partial fill are deliberately not driven -- either the outcome
        # is genuinely ambiguous (never guess forward on capital-relevant
        # state), or Module 4's frozen table has no matching edge.

        if exec_trigger is None:
            return
        # Module 4 caps request_id at 60 chars; client_order_id + trigger
        # name can exceed that, so hash to a fixed-length, still fully
        # deterministic id (same inputs always produce the same digest).
        digest = hashlib.sha256(f"{client_order_id}:{exec_trigger.value}".encode("utf-8")).hexdigest()[:40]
        try:
            self._execution_sm.transition(
                exec_trigger,
                request_id=digest,
                context={"client_order_id": client_order_id},
            )
        except ExecutionIllegalTransitionError:
            pass

    # -- shared status-ingestion path (submit ack/reject, cancel confirm, resync) --

    def _ingest_status(
        self, client_order_id: str, status: OrderStatus, exchange_order_id: Optional[str], reason: Optional[str] = None
    ) -> OrderSnapshot:
        trigger = _STATUS_TO_TRIGGER.get(status)
        if trigger is None:
            return self._snapshots[client_order_id]  # PARTIALLY_FILLED/UNKNOWN/NEW arrive via report_fill or are inert

        existing = self._snapshots[client_order_id]
        current = existing.lifecycle_state
        if is_legal(current, trigger):
            to_state = next_state(current, trigger)
        elif current in TERMINAL_STATES or state_rank(current) >= trigger_min_target_rank(trigger):
            return existing  # stale/duplicate/out-of-order -- ignored
        else:
            raise OrderStateInconsistencyError(
                f"client_order_id={client_order_id}: status {status.value} is not legal from "
                f"{current.value} and is not recognizably stale"
            )

        details = {"exchange_order_id": exchange_order_id, "reject_reason": reason}
        event = self._persist(
            "STATUS_UPDATE", client_order_id, None, trigger, current, to_state, details,
            idempotency_key=f"{client_order_id}:status:{trigger.value}:{current.value}",
        )
        snapshot = self._apply_event(event)
        self._drive_execution_sm(client_order_id, trigger, current, snapshot)
        return snapshot

    # -- public: place order --

    def place_order(
        self,
        symbol: Symbol,
        side: OrderSide,
        order_type: OrderType,
        quantity: Decimal,
        limit_price: Optional[Decimal] = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
        reduce_only: bool = False,
    ) -> OrderSnapshot:
        seq, client_order_id = self._next_id("place")
        lock = self._lock_for(client_order_id)
        with lock:
            details = {
                "symbol": symbol.value,
                "side": side.value,
                "order_type": order_type.value,
                "quantity": str(quantity),
                "limit_price": str(limit_price) if limit_price is not None else None,
                "time_in_force": time_in_force.value,
                "reduce_only": reduce_only,
            }
            event = self._persist("SUBMIT", client_order_id, seq, None, None, None, details, idempotency_key=client_order_id)
            snapshot = self._apply_event(event)
            self._drive_execution_sm(client_order_id, "SUBMIT", OrderLifecycleState.NEW, snapshot)

            request = OrderRequest(
                client_order_id=client_order_id, symbol=symbol, side=side, order_type=order_type,
                quantity=quantity, limit_price=limit_price, time_in_force=time_in_force, reduce_only=reduce_only,
            )
            try:
                order = self._adapter.place_order(request)
            except ExchangeAdapterError as exc:
                current = self._snapshots[client_order_id].lifecycle_state
                trigger = OrderLifecycleTrigger.SUBMIT_FAILED
                if is_legal(current, trigger):
                    to_state = next_state(current, trigger)
                    fail_event = self._persist(
                        "STATUS_UPDATE", client_order_id, None, trigger, current, to_state, {"error": str(exc)},
                        idempotency_key=f"{client_order_id}:submit_failed",
                    )
                    self._apply_event(fail_event)  # deliberately not driving execution_sm: ambiguous outcome
                raise

            if order.status is OrderStatus.REJECTED:
                return self._ingest_status(client_order_id, OrderStatus.REJECTED, order.exchange_order_id)
            return self._ingest_status(client_order_id, OrderStatus.ACKNOWLEDGED, order.exchange_order_id)

    # -- public: amend order --

    def amend_order(
        self, client_order_id: str, new_quantity: Optional[Decimal] = None, new_limit_price: Optional[Decimal] = None
    ) -> OrderSnapshot:
        if new_quantity is None and new_limit_price is None:
            raise ValueError("amend must change at least one of new_quantity or new_limit_price")
        lock = self._lock_for(client_order_id)
        with lock:
            existing = self._snapshots.get(client_order_id)
            if existing is None:
                raise OrderNotFoundError(f"no order tracked with client_order_id={client_order_id!r}")
            if existing.lifecycle_state not in (OrderLifecycleState.ACKNOWLEDGED, OrderLifecycleState.PARTIALLY_FILLED):
                raise IllegalOrderTransitionError(f"cannot amend order in state {existing.lifecycle_state.value}")
            if existing.exchange_order_id is None:
                raise OrderStateInconsistencyError(f"order {client_order_id} has no exchange_order_id yet")

            seq, request_id = self._next_id("amend")
            intent_details = {
                "request_id": request_id,
                "new_quantity": str(new_quantity) if new_quantity is not None else None,
                "new_limit_price": str(new_limit_price) if new_limit_price is not None else None,
            }
            intent_event = self._persist(
                "AMEND_REQUESTED", client_order_id, seq, None, None, None, intent_details,
                idempotency_key=f"{client_order_id}:amend_req:{request_id}",
            )
            self._apply_event(intent_event)

            request = AmendRequest(
                request_id=request_id, exchange_order_id=existing.exchange_order_id,
                new_quantity=new_quantity, new_limit_price=new_limit_price,
            )
            order = self._adapter.amend_order(request)

            applied_details = {
                "new_quantity": str(order.quantity),
                "new_limit_price": str(order.limit_price) if order.limit_price is not None else None,
            }
            applied_event = self._persist(
                "AMEND", client_order_id, None, None, None, None, applied_details,
                idempotency_key=f"{client_order_id}:amend_applied:{request_id}",
            )
            return self._apply_event(applied_event)

    # -- public: cancel order --

    def cancel_order(self, client_order_id: str) -> OrderSnapshot:
        lock = self._lock_for(client_order_id)
        with lock:
            existing = self._snapshots.get(client_order_id)
            if existing is None:
                raise OrderNotFoundError(f"no order tracked with client_order_id={client_order_id!r}")
            current = existing.lifecycle_state
            if current is OrderLifecycleState.CANCEL_PENDING:
                return existing  # already in flight -- idempotent no-op, no new exchange action
            trigger = OrderLifecycleTrigger.CANCEL_REQUESTED
            if not is_legal(current, trigger):
                raise IllegalOrderTransitionError(f"cannot cancel order in state {current.value}")
            if existing.exchange_order_id is None:
                raise OrderStateInconsistencyError(f"order {client_order_id} has no exchange_order_id yet")

            to_state = next_state(current, trigger)
            seq, request_id = self._next_id("cancel")
            event = self._persist(
                "STATUS_UPDATE", client_order_id, seq, trigger, current, to_state, {"request_id": request_id},
                idempotency_key=f"{client_order_id}:cancel:{request_id}",
            )
            self._apply_event(event)

            request = CancelRequest(request_id=request_id, exchange_order_id=existing.exchange_order_id)
            try:
                order = self._adapter.cancel_order(request)
            except ExchangeAdapterError as exc:
                pending = self._snapshots[client_order_id].lifecycle_state
                fail_trigger = OrderLifecycleTrigger.CANCEL_FAILED
                if is_legal(pending, fail_trigger):
                    fail_state = next_state(pending, fail_trigger)
                    fail_event = self._persist(
                        "STATUS_UPDATE", client_order_id, None, fail_trigger, pending, fail_state, {"error": str(exc)},
                        idempotency_key=f"{client_order_id}:cancel_failed:{request_id}",
                    )
                    self._apply_event(fail_event)  # ambiguous outcome -- not driving execution_sm
                raise
            return self._ingest_status(client_order_id, order.status, order.exchange_order_id)

    # -- public: cancel all --

    def cancel_all(self, symbol: Optional[Symbol] = None) -> Tuple[OrderSnapshot, ...]:
        seq, request_id = self._next_id("cancel_all")
        intent_event = self._persist(
            "CANCEL_ALL_REQUESTED", "*", seq, None, None, None,
            {"request_id": request_id, "symbol": symbol.value if symbol else None},
            idempotency_key=f"cancel_all:{request_id}",
        )
        self._apply_event(intent_event)

        request = CancelAllRequest(request_id=request_id, symbol=symbol)
        orders = self._adapter.cancel_all(request)

        results = []
        for order in orders:
            cid = order.client_order_id
            if cid not in self._snapshots:
                continue
            lock = self._lock_for(cid)
            with lock:
                current = self._snapshots[cid].lifecycle_state
                if current in (OrderLifecycleState.ACKNOWLEDGED, OrderLifecycleState.PARTIALLY_FILLED):
                    pend_trigger = OrderLifecycleTrigger.CANCEL_REQUESTED
                    pend_state = next_state(current, pend_trigger)
                    ev1 = self._persist(
                        "STATUS_UPDATE", cid, None, pend_trigger, current, pend_state, {"request_id": request_id},
                        idempotency_key=f"{cid}:cancel_all_pending:{request_id}",
                    )
                    self._apply_event(ev1)
                    current = pend_state
                if current is OrderLifecycleState.CANCEL_PENDING:
                    conf_trigger = OrderLifecycleTrigger.CANCEL_CONFIRMED
                    conf_state = next_state(current, conf_trigger)
                    ev2 = self._persist(
                        "STATUS_UPDATE", cid, None, conf_trigger, current, conf_state,
                        {"exchange_order_id": order.exchange_order_id},
                        idempotency_key=f"{cid}:cancel_all_confirm:{request_id}",
                    )
                    snapshot = self._apply_event(ev2)
                    self._drive_execution_sm(cid, conf_trigger, OrderLifecycleState.CANCEL_PENDING, snapshot)
                    results.append(snapshot)
        return tuple(results)

    # -- public: fill ingestion --

    def report_fill(self, client_order_id: str, fill: Fill) -> OrderSnapshot:
        if not isinstance(fill, Fill):
            raise TypeError(f"fill must be a Fill, got {type(fill).__name__}")
        lock = self._lock_for(client_order_id)
        with lock:
            existing = self._snapshots.get(client_order_id)
            if existing is None:
                raise OrderNotFoundError(f"no order tracked with client_order_id={client_order_id!r}")

            if fill.fill_id in self._processed_fill_ids.get(client_order_id, set()):
                return existing  # duplicate fill -- ignored

            if existing.lifecycle_state in TERMINAL_STATES:
                # Late fill after the order already resolved. Recorded as
                # processed (dedup-safe) but does not reopen a closed
                # snapshot -- reconciling P&L for this case is a future
                # Position Manager concern, not this module's.
                self._processed_fill_ids.setdefault(client_order_id, set()).add(fill.fill_id)
                return existing

            new_filled = existing.filled_quantity + fill.quantity
            trigger = OrderLifecycleTrigger.FULL_FILL if new_filled >= existing.quantity else OrderLifecycleTrigger.PARTIAL_FILL
            current = existing.lifecycle_state
            if not is_legal(current, trigger):
                raise OrderStateInconsistencyError(
                    f"fill for {client_order_id} not legal from {current.value}"
                )
            to_state = next_state(current, trigger)
            details = {"fill_id": fill.fill_id, "fill_quantity": str(fill.quantity), "fill_price": str(fill.price)}
            event = self._persist(
                "FILL", client_order_id, None, trigger, current, to_state, details,
                idempotency_key=f"{client_order_id}:fill:{fill.fill_id}",
            )
            snapshot = self._apply_event(event)
            self._drive_execution_sm(client_order_id, trigger, current, snapshot)
            return snapshot

    # -- public: general async status ingestion (e.g. a later websocket push) --

    def report_order_update(self, client_order_id: str, order: Order) -> OrderSnapshot:
        if not isinstance(order, Order):
            raise TypeError(f"order must be an Order, got {type(order).__name__}")
        lock = self._lock_for(client_order_id)
        with lock:
            if client_order_id not in self._snapshots:
                raise OrderNotFoundError(f"no order tracked with client_order_id={client_order_id!r}")
            return self._ingest_status(client_order_id, order.status, order.exchange_order_id)

    # -- public: queries --

    def get_order_status(self, client_order_id: str) -> OrderSnapshot:
        snapshot = self._snapshots.get(client_order_id)
        if snapshot is None:
            raise OrderNotFoundError(f"no order tracked with client_order_id={client_order_id!r}")
        return snapshot

    def get_fills(self, client_order_id: Optional[str] = None) -> Tuple[Fill, ...]:
        # Delegates entirely to the adapter -- OM implements no fill
        # storage of its own beyond the dedup set needed for report_fill.
        fills = self._adapter.get_fills()
        if client_order_id is not None:
            fills = tuple(f for f in fills if f.client_order_id == client_order_id)
        return tuple(fills)

    # -- public: recovery support (reconciliation only through ExchangeAdapter) --

    @property
    def in_doubt_client_order_ids(self) -> Tuple[str, ...]:
        return tuple(
            cid for cid, snap in self._snapshots.items()
            if snap.lifecycle_state in (OrderLifecycleState.SUBMITTED, OrderLifecycleState.CANCEL_PENDING)
        )

    def resync_order(self, client_order_id: str) -> OrderSnapshot:
        lock = self._lock_for(client_order_id)
        with lock:
            existing = self._snapshots.get(client_order_id)
            if existing is None:
                raise OrderNotFoundError(f"no order tracked with client_order_id={client_order_id!r}")
            if existing.exchange_order_id is None:
                request = OrderRequest(
                    client_order_id=existing.client_order_id, symbol=existing.symbol, side=existing.side,
                    order_type=existing.order_type, quantity=existing.quantity, limit_price=existing.limit_price,
                    time_in_force=existing.time_in_force, reduce_only=existing.reduce_only,
                )
                match = self._adapter.find_order(request)
                if match is None:
                    return existing  # still unresolved; caller decides next step
                return self._ingest_status(client_order_id, match.status, match.exchange_order_id)
            order = self._adapter.get_order_status(existing.exchange_order_id)
            return self._ingest_status(client_order_id, order.status, order.exchange_order_id)

    def __repr__(self) -> str:
        return f"OrderManager(om_id={self._om_id!r}, tracked_orders={len(self._snapshots)})"

    __str__ = __repr__
