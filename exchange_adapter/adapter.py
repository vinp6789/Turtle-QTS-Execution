"""Abstract Exchange Adapter interface.

Defines the contract only -- no exchange-specific code, no trading
decisions, no real network calls. A concrete adapter (Hyperliquid,
Lighter, Variational, or any future exchange) implements the abstract
hooks below; nothing about this module changes to add a new exchange.

Responsibilities that belong to a concrete adapter and NOT to any other
module: authentication, request signing (via SigningBoundary only --
never a raw key), websocket lifecycle, REST communication, order/
position/balance translation, and exchange-specific error mapping into
the closed hierarchy in errors.py. This module never decides WHETHER,
WHEN, or HOW MUCH to trade -- it only executes exactly what it is told
and reports normalized state back.

Two guarantees are enforced structurally, not by convention, so no
subclass can skip them:
  1. Idempotency: place_order/amend_order/cancel_order/cancel_all are
     concrete methods here that check an IdempotencyCache before ever
     calling the abstract `_transmit_*` hook, and store the result after.
  2. Audit: the same four methods always construct and record a
     deterministic AuditRecord BEFORE calling `_transmit_*` -- forensic
     reconstruction of "what was about to be sent" never depends on a
     concrete adapter remembering to log it.
"""

import threading
from abc import ABC, abstractmethod
from typing import Optional, Tuple

from secrets_boundary import SigningBoundary

from .audit import (
    amend_request_audit_payload,
    cancel_all_request_audit_payload,
    cancel_request_audit_payload,
    compute_audit_record,
    order_request_audit_payload,
)
from .idempotency import IdempotencyCache
from .models import (
    AmendRequest,
    AuditRecord,
    Balance,
    CancelAllRequest,
    CancelRequest,
    ExchangeCapabilities,
    Fill,
    FundingRate,
    HealthStatus,
    MarkPrice,
    Order,
    OrderRequest,
    Position,
    ReconciliationReport,
    Symbol,
)


class ExchangeAdapter(ABC):
    """The frozen interface every exchange adapter implements.

    `capabilities` is fixed at construction and never changes afterward.
    `exchange_name` exists for logging, domain-separated signing (see
    SigningBoundary), and audit records -- callers must make behavioral
    decisions from `capabilities`, never from `exchange_name` string
    comparisons, so the same calling code works unmodified across
    exchanges.
    """

    def __init__(
        self,
        signing_boundary: SigningBoundary,
        exchange_name: str,
        adapter_version: str,
        capabilities: ExchangeCapabilities,
    ):
        if not isinstance(signing_boundary, SigningBoundary):
            raise TypeError(f"signing_boundary must be a SigningBoundary, got {type(signing_boundary).__name__}")
        if not isinstance(exchange_name, str) or not exchange_name.strip():
            raise ValueError("exchange_name must be a non-empty string")
        if not isinstance(adapter_version, str) or not adapter_version.strip():
            raise ValueError("adapter_version must be a non-empty string")
        if not isinstance(capabilities, ExchangeCapabilities):
            raise TypeError(f"capabilities must be an ExchangeCapabilities, got {type(capabilities).__name__}")

        self._signing = signing_boundary
        self._exchange_name = exchange_name
        self._adapter_version = adapter_version
        self._capabilities = capabilities
        self._idempotency: IdempotencyCache = IdempotencyCache()
        self._audit_log: list = []
        self._mutation_lock = threading.Lock()

    @property
    def exchange_name(self) -> str:
        return self._exchange_name

    @property
    def adapter_version(self) -> str:
        return self._adapter_version

    @property
    def capabilities(self) -> ExchangeCapabilities:
        return self._capabilities

    @property
    def audit_records(self) -> Tuple[AuditRecord, ...]:
        return tuple(self._audit_log)

    # -- connection lifecycle & read-only queries: abstract, no audit/idempotency needed --

    @abstractmethod
    def connect(self) -> HealthStatus: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def health(self) -> HealthStatus: ...

    @abstractmethod
    def get_positions(self) -> Tuple[Position, ...]: ...

    @abstractmethod
    def get_orders(self) -> Tuple[Order, ...]: ...

    @abstractmethod
    def get_balances(self) -> Tuple[Balance, ...]: ...

    @abstractmethod
    def get_mark_price(self, symbol: Symbol) -> MarkPrice: ...

    @abstractmethod
    def get_funding_rate(self, symbol: Symbol) -> FundingRate: ...

    @abstractmethod
    def get_order_status(self, exchange_order_id: str) -> Order: ...

    @abstractmethod
    def get_fills(self, since_utc: Optional[str] = None) -> Tuple[Fill, ...]: ...

    @abstractmethod
    def reconcile(self, local_positions: Tuple[Position, ...]) -> ReconciliationReport: ...

    # -- mutations: concrete template methods, audit + idempotency enforced here --

    def place_order(self, request: OrderRequest) -> Order:
        if not isinstance(request, OrderRequest):
            raise TypeError(f"request must be an OrderRequest, got {type(request).__name__}")
        with self._mutation_lock:
            cached = self._idempotency.get(request.client_order_id)
            if cached is not None:
                return cached
            record = compute_audit_record(
                request_id=request.client_order_id,
                logical_action="PLACE_ORDER",
                exchange_name=self._exchange_name,
                adapter_version=self._adapter_version,
                idempotency_key=request.client_order_id,
                payload=order_request_audit_payload(request),
            )
            self._audit_log.append(record)
            result = self._transmit_place_order(request)
            return self._idempotency.store(request.client_order_id, result)

    def amend_order(self, request: AmendRequest) -> Order:
        if not isinstance(request, AmendRequest):
            raise TypeError(f"request must be an AmendRequest, got {type(request).__name__}")
        with self._mutation_lock:
            cached = self._idempotency.get(request.request_id)
            if cached is not None:
                return cached
            record = compute_audit_record(
                request_id=request.request_id,
                logical_action="AMEND_ORDER",
                exchange_name=self._exchange_name,
                adapter_version=self._adapter_version,
                idempotency_key=request.request_id,
                payload=amend_request_audit_payload(request),
            )
            self._audit_log.append(record)
            result = self._transmit_amend_order(request)
            return self._idempotency.store(request.request_id, result)

    def cancel_order(self, request: CancelRequest) -> Order:
        if not isinstance(request, CancelRequest):
            raise TypeError(f"request must be a CancelRequest, got {type(request).__name__}")
        with self._mutation_lock:
            cached = self._idempotency.get(request.request_id)
            if cached is not None:
                return cached
            record = compute_audit_record(
                request_id=request.request_id,
                logical_action="CANCEL_ORDER",
                exchange_name=self._exchange_name,
                adapter_version=self._adapter_version,
                idempotency_key=request.request_id,
                payload=cancel_request_audit_payload(request),
            )
            self._audit_log.append(record)
            result = self._transmit_cancel_order(request)
            return self._idempotency.store(request.request_id, result)

    def cancel_all(self, request: CancelAllRequest) -> Tuple[Order, ...]:
        if not isinstance(request, CancelAllRequest):
            raise TypeError(f"request must be a CancelAllRequest, got {type(request).__name__}")
        with self._mutation_lock:
            cached = self._idempotency.get(request.request_id)
            if cached is not None:
                return cached
            record = compute_audit_record(
                request_id=request.request_id,
                logical_action="CANCEL_ALL",
                exchange_name=self._exchange_name,
                adapter_version=self._adapter_version,
                idempotency_key=request.request_id,
                payload=cancel_all_request_audit_payload(request),
            )
            self._audit_log.append(record)
            result = self._transmit_cancel_all(request)
            return self._idempotency.store(request.request_id, result)

    # -- abstract transmission hooks: implemented per exchange --

    @abstractmethod
    def _transmit_place_order(self, request: OrderRequest) -> Order: ...

    @abstractmethod
    def _transmit_amend_order(self, request: AmendRequest) -> Order: ...

    @abstractmethod
    def _transmit_cancel_order(self, request: CancelRequest) -> Order: ...

    @abstractmethod
    def _transmit_cancel_all(self, request: CancelAllRequest) -> Tuple[Order, ...]: ...

    def __repr__(self) -> str:
        return f"{type(self).__name__}(exchange_name={self._exchange_name!r}, version={self._adapter_version!r})"

    __str__ = __repr__
