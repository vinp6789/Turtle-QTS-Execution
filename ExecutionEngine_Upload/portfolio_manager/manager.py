"""Portfolio Manager: owns portfolio-level state only. A ledger, not a
lifecycle -- there is no per-entity state machine here, just one
portfolio-wide lock serializing every mutation against every other.

Consumes only normalized facts from Position Manager (realized PnL legs,
funding payments, fee amounts, unrealized PnL/exposure/heat aggregates)
and caller-supplied deposit/withdrawal amounts. Never touches
SigningBoundary or ExchangeAdapter, never generates signals, never
computes conviction or indicators, never submits an exchange request.

Every mutating method acquires the single portfolio lock, checks
Module 3's idempotency ledger for a duplicate request before validating
or applying anything, and asserts Assets == Equity before returning --
so a bug that breaks the invariant is caught immediately, not discovered
later during a reconciliation.
"""

import threading
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional, Set

from event_store import Event, EventStore, EventType

from .errors import (
    AccountingInvariantError,
    InsufficientFundsError,
    InsufficientMarginError,
    PortfolioManagerError,
    ReplayIntegrityError,
)
from .snapshot import PortfolioSnapshot

_EVENT_SOURCE_TAG = "portfolio_manager"
_MAX_PM_ID_LENGTH = 60


def _is_own_event(event: Event, pm_id: str) -> bool:
    return event.payload.get("source") == _EVENT_SOURCE_TAG and event.payload.get("pm_id") == pm_id


def _event_type_for_action(action: str) -> EventType:
    # Best-fit categorization onto Module 3's closed EventType enum, same
    # spirit as every prior module: the coarse category is cosmetic, the
    # payload's own action/details fields are authoritative for replay.
    return EventType.POSITION_UPDATED


class PortfolioManager:
    def __init__(self, store: EventStore, pm_id: str = "default"):
        if not isinstance(store, EventStore):
            raise TypeError(f"store must be an EventStore, got {type(store).__name__}")
        if not isinstance(pm_id, str) or not pm_id.strip():
            raise ValueError("pm_id must be a non-empty string")
        if len(pm_id) > _MAX_PM_ID_LENGTH:
            raise ValueError(f"pm_id exceeds {_MAX_PM_ID_LENGTH} characters")

        self._store = store
        self._pm_id = pm_id
        self._lock = threading.Lock()

        self._available_cash = Decimal("0")
        self._reserved_margin = Decimal("0")
        self._used_margin = Decimal("0")
        self._unrealized_pnl = Decimal("0")
        self._realized_pnl_cumulative = Decimal("0")
        self._funding_cumulative = Decimal("0")
        self._fees_cumulative = Decimal("0")
        self._deposits_cumulative = Decimal("0")
        self._withdrawals_cumulative = Decimal("0")
        self._exposure = Decimal("0")
        self._heat = Decimal("0")
        self._open_position_ids: Set[str] = set()
        self._reserved_by_position: Dict[str, Decimal] = {}
        self._used_by_position: Dict[str, Decimal] = {}
        self._released_positions: Set[str] = set()
        self._applied_event_ids: Set[int] = set()
        self._updated_at_utc = datetime.now(timezone.utc).isoformat()

        for event in store.replay():
            if not _is_own_event(event, pm_id):
                continue
            self._apply_event(event)

    # -- persistence --

    def _namespaced_key(self, key: str) -> str:
        return f"{_EVENT_SOURCE_TAG}:{self._pm_id}:{key}"

    def _get_cached(self, key: str) -> Optional[PortfolioSnapshot]:
        existing = self._store.get_by_idempotency_key(self._namespaced_key(key))
        if existing is not None:
            return self._apply_event(existing)
        return None

    def _persist(self, action: str, details: Dict[str, Any], key: str) -> Event:
        payload = {"source": _EVENT_SOURCE_TAG, "pm_id": self._pm_id, "action": action, "details": details}
        return self._store.append(_event_type_for_action(action), payload, idempotency_key=self._namespaced_key(key))

    def _apply_event(self, event: Event) -> PortfolioSnapshot:
        if event.event_id in self._applied_event_ids:
            return self._snapshot()
        self._applied_event_ids.add(event.event_id)

        action = event.payload["action"]
        details = event.payload.get("details", {})

        if action == "DEPOSIT":
            amt = Decimal(details["amount"])
            self._available_cash += amt
            self._deposits_cumulative += amt
        elif action == "WITHDRAW":
            amt = Decimal(details["amount"])
            self._available_cash -= amt
            self._withdrawals_cumulative += amt
        elif action == "RESERVE_MARGIN":
            pid, amt = details["position_id"], Decimal(details["amount"])
            self._available_cash -= amt
            self._reserved_margin += amt
            self._reserved_by_position[pid] = self._reserved_by_position.get(pid, Decimal("0")) + amt
        elif action == "ALLOCATE_MARGIN":
            pid, amt = details["position_id"], Decimal(details["amount"])
            self._reserved_margin -= amt
            self._used_margin += amt
            self._reserved_by_position[pid] = self._reserved_by_position.get(pid, Decimal("0")) - amt
            self._used_by_position[pid] = self._used_by_position.get(pid, Decimal("0")) + amt
            self._open_position_ids.add(pid)
        elif action == "RELEASE_MARGIN":
            pid = details["position_id"]
            reserved = self._reserved_by_position.pop(pid, Decimal("0"))
            used = self._used_by_position.pop(pid, Decimal("0"))
            self._reserved_margin -= reserved
            self._used_margin -= used
            self._available_cash += reserved + used
            self._released_positions.add(pid)
            self._open_position_ids.discard(pid)
        elif action == "REALIZED_PNL":
            amt = Decimal(details["amount"])
            self._available_cash += amt
            self._realized_pnl_cumulative += amt
        elif action == "FUNDING":
            amt = Decimal(details["amount"])
            self._available_cash += amt
            self._funding_cumulative += amt
        elif action == "FEE":
            amt = Decimal(details["amount"])
            self._available_cash -= amt
            self._fees_cumulative += amt
        elif action == "UPDATE_MARKS":
            self._unrealized_pnl = Decimal(details["unrealized_pnl"])
            self._exposure = Decimal(details["exposure"])
            self._heat = Decimal(details["heat"])
        else:
            raise ReplayIntegrityError(f"event {event.event_id}: unknown action {action!r}")

        self._updated_at_utc = event.timestamp_utc
        snapshot = self._snapshot()
        self._assert_invariant(snapshot)
        return snapshot

    def _snapshot(self) -> PortfolioSnapshot:
        return PortfolioSnapshot(
            available_cash=self._available_cash,
            reserved_margin=self._reserved_margin,
            used_margin=self._used_margin,
            unrealized_pnl=self._unrealized_pnl,
            realized_pnl_cumulative=self._realized_pnl_cumulative,
            funding_cumulative=self._funding_cumulative,
            fees_cumulative=self._fees_cumulative,
            deposits_cumulative=self._deposits_cumulative,
            withdrawals_cumulative=self._withdrawals_cumulative,
            exposure=self._exposure,
            heat=self._heat,
            open_position_ids=tuple(sorted(self._open_position_ids)),
            updated_at_utc=self._updated_at_utc,
        )

    def _assert_invariant(self, snapshot: PortfolioSnapshot) -> None:
        if snapshot.assets != snapshot.liabilities + snapshot.equity:
            raise AccountingInvariantError(
                f"Assets ({snapshot.assets}) != Liabilities ({snapshot.liabilities}) + "
                f"Equity ({snapshot.equity}) -- accounting invariant violated"
            )

    # -- public: capital movements --

    def deposit(self, amount: Decimal, request_id: str) -> PortfolioSnapshot:
        if amount <= 0:
            raise ValueError("amount must be positive")
        with self._lock:
            cached = self._get_cached(f"deposit:{request_id}")
            if cached is not None:
                return cached
            event = self._persist("DEPOSIT", {"amount": str(amount)}, f"deposit:{request_id}")
            return self._apply_event(event)

    def withdraw(self, amount: Decimal, request_id: str) -> PortfolioSnapshot:
        if amount <= 0:
            raise ValueError("amount must be positive")
        with self._lock:
            cached = self._get_cached(f"withdraw:{request_id}")
            if cached is not None:
                return cached
            if amount > self._available_cash:
                raise InsufficientFundsError(
                    f"withdrawal of {amount} exceeds available cash {self._available_cash}"
                )
            event = self._persist("WITHDRAW", {"amount": str(amount)}, f"withdraw:{request_id}")
            return self._apply_event(event)

    # -- public: margin lifecycle --

    def reserve_margin(self, position_id: str, amount: Decimal, request_id: str) -> PortfolioSnapshot:
        if amount <= 0:
            raise ValueError("amount must be positive")
        with self._lock:
            key = f"reserve_margin:{position_id}:{request_id}"
            cached = self._get_cached(key)
            if cached is not None:
                return cached
            if amount > self._available_cash:
                raise InsufficientFundsError(
                    f"cannot reserve {amount} margin; available cash is {self._available_cash}"
                )
            event = self._persist("RESERVE_MARGIN", {"position_id": position_id, "amount": str(amount)}, key)
            return self._apply_event(event)

    def allocate_margin(self, position_id: str, amount: Decimal, request_id: str) -> PortfolioSnapshot:
        if amount <= 0:
            raise ValueError("amount must be positive")
        with self._lock:
            key = f"allocate_margin:{position_id}:{request_id}"
            cached = self._get_cached(key)
            if cached is not None:
                return cached
            reserved = self._reserved_by_position.get(position_id, Decimal("0"))
            if amount > reserved:
                raise InsufficientMarginError(
                    f"cannot allocate {amount} for {position_id}; only {reserved} reserved"
                )
            event = self._persist("ALLOCATE_MARGIN", {"position_id": position_id, "amount": str(amount)}, key)
            return self._apply_event(event)

    def release_margin(self, position_id: str, request_id: str) -> PortfolioSnapshot:
        with self._lock:
            if position_id in self._released_positions:
                # Released already, possibly via a different request_id --
                # "exactly once" is enforced on the position itself, not
                # only on the literal request, so this is always a safe
                # no-op rather than a silent double-release.
                return self._snapshot()
            key = f"release_margin:{position_id}:{request_id}"
            cached = self._get_cached(key)
            if cached is not None:
                return cached
            event = self._persist("RELEASE_MARGIN", {"position_id": position_id}, key)
            return self._apply_event(event)

    # -- public: PnL / funding / fees (recording facts, not authorizing movements) --

    def apply_realized_pnl(self, position_id: str, leg_id: str, amount: Decimal, request_id: str) -> PortfolioSnapshot:
        with self._lock:
            key = f"realized_pnl:{position_id}:{leg_id}"
            cached = self._get_cached(key)
            if cached is not None:
                return cached
            event = self._persist(
                "REALIZED_PNL", {"position_id": position_id, "leg_id": leg_id, "amount": str(amount)}, key
            )
            return self._apply_event(event)

    def apply_funding(self, position_id: str, funding_id: str, amount: Decimal, request_id: str) -> PortfolioSnapshot:
        with self._lock:
            key = f"funding:{position_id}:{funding_id}"
            cached = self._get_cached(key)
            if cached is not None:
                return cached
            event = self._persist(
                "FUNDING", {"position_id": position_id, "funding_id": funding_id, "amount": str(amount)}, key
            )
            return self._apply_event(event)

    def apply_fee(self, reference_id: str, fee_id: str, amount: Decimal, request_id: str) -> PortfolioSnapshot:
        if amount < 0:
            raise ValueError("fee amount must be non-negative")
        with self._lock:
            key = f"fee:{reference_id}:{fee_id}"
            cached = self._get_cached(key)
            if cached is not None:
                return cached
            event = self._persist(
                "FEE", {"reference_id": reference_id, "fee_id": fee_id, "amount": str(amount)}, key
            )
            return self._apply_event(event)

    # -- public: mark-to-market refresh --

    def update_marks(
        self, unrealized_pnl: Decimal, exposure: Decimal, heat: Decimal, request_id: str
    ) -> PortfolioSnapshot:
        with self._lock:
            key = f"update_marks:{request_id}"
            cached = self._get_cached(key)
            if cached is not None:
                return cached
            event = self._persist(
                "UPDATE_MARKS",
                {"unrealized_pnl": str(unrealized_pnl), "exposure": str(exposure), "heat": str(heat)},
                key,
            )
            return self._apply_event(event)

    # -- public: queries --

    def get_snapshot(self) -> PortfolioSnapshot:
        with self._lock:
            return self._snapshot()

    def __repr__(self) -> str:
        return f"PortfolioManager(pm_id={self._pm_id!r}, positions={len(self._open_position_ids)})"

    __str__ = __repr__
