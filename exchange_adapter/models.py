"""Exchange-agnostic typed models for the Exchange Adapter interface.

Every public method on ExchangeAdapter takes and returns only these types
(or tuples of them) -- never a dict, never a raw exchange-native shape.
All money/quantity fields use Decimal, never float, since float rounding
error is unacceptable for anything capital-related.

These models carry no exchange-specific fields. A concrete adapter (e.g.
a future Hyperliquid adapter) is responsible for translating its own
native REST/WS shapes into these types internally; nothing native to any
particular exchange may cross this boundary.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Optional, Tuple


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class TimeInForce(Enum):
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"
    POST_ONLY = "POST_ONLY"


class OrderStatus(Enum):
    NEW = "NEW"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


class ConnectionState(Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"


@dataclass(frozen=True)
class Symbol:
    value: str

    def __post_init__(self):
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("Symbol.value must be a non-empty string")


@dataclass(frozen=True)
class ExchangeCapabilities:
    """Immutable, exchange-agnostic feature description.

    Purely descriptive metadata -- never business logic. Callers (Order
    Manager, Risk Manager, etc.) must branch on these fields, never on
    exchange_name, so the same calling code works unmodified against
    Hyperliquid, Lighter, Variational, or any future exchange. The
    (deliberately non-exhaustive) `extra` map allows a future exchange to
    describe capabilities not anticipated here without changing this
    dataclass's shape.
    """

    supports_reduce_only: bool
    supports_post_only: bool
    supports_ioc: bool
    supports_fok: bool
    supports_market_orders: bool
    supports_limit_orders: bool
    supports_trigger_orders: bool
    supports_partial_fill_notifications: bool
    supports_funding_rate: bool
    supports_cross_margin: bool
    supports_isolated_margin: bool
    extra: Mapping[str, bool] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self):
        object.__setattr__(self, "extra", MappingProxyType(dict(self.extra)))


@dataclass(frozen=True)
class OrderRequest:
    client_order_id: str
    symbol: Symbol
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    limit_price: Optional[Decimal] = None
    time_in_force: TimeInForce = TimeInForce.GTC
    reduce_only: bool = False

    def __post_init__(self):
        if not isinstance(self.client_order_id, str) or not self.client_order_id.strip():
            raise ValueError("client_order_id must be a non-empty string")
        if not isinstance(self.quantity, Decimal) or self.quantity <= 0:
            raise ValueError("quantity must be a positive Decimal")
        if self.limit_price is not None and (not isinstance(self.limit_price, Decimal) or self.limit_price <= 0):
            raise ValueError("limit_price must be a positive Decimal when provided")


@dataclass(frozen=True)
class AmendRequest:
    request_id: str
    exchange_order_id: str
    new_quantity: Optional[Decimal] = None
    new_limit_price: Optional[Decimal] = None

    def __post_init__(self):
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise ValueError("request_id must be a non-empty string")
        if not isinstance(self.exchange_order_id, str) or not self.exchange_order_id.strip():
            raise ValueError("exchange_order_id must be a non-empty string")
        if self.new_quantity is None and self.new_limit_price is None:
            raise ValueError("amend must change at least one of new_quantity or new_limit_price")


@dataclass(frozen=True)
class CancelRequest:
    request_id: str
    exchange_order_id: str

    def __post_init__(self):
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise ValueError("request_id must be a non-empty string")
        if not isinstance(self.exchange_order_id, str) or not self.exchange_order_id.strip():
            raise ValueError("exchange_order_id must be a non-empty string")


@dataclass(frozen=True)
class CancelAllRequest:
    request_id: str
    symbol: Optional[Symbol] = None

    def __post_init__(self):
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise ValueError("request_id must be a non-empty string")


@dataclass(frozen=True)
class Order:
    client_order_id: str
    exchange_order_id: Optional[str]
    symbol: Symbol
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    filled_quantity: Decimal
    limit_price: Optional[Decimal]
    status: OrderStatus
    time_in_force: TimeInForce
    reduce_only: bool
    created_at_utc: str
    updated_at_utc: str


@dataclass(frozen=True)
class Fill:
    fill_id: str
    client_order_id: str
    exchange_order_id: str
    symbol: Symbol
    side: OrderSide
    price: Decimal
    quantity: Decimal
    fee: Decimal
    timestamp_utc: str


@dataclass(frozen=True)
class Position:
    symbol: Symbol
    quantity: Decimal  # signed: positive = long, negative = short
    entry_price: Decimal
    mark_price: Decimal
    unrealized_pnl: Decimal
    liquidation_price: Optional[Decimal]


@dataclass(frozen=True)
class Balance:
    asset: Symbol
    total: Decimal
    available: Decimal
    reserved: Decimal


@dataclass(frozen=True)
class MarkPrice:
    symbol: Symbol
    price: Decimal
    timestamp_utc: str


@dataclass(frozen=True)
class FundingRate:
    symbol: Symbol
    rate: Decimal
    next_funding_time_utc: str
    timestamp_utc: str


@dataclass(frozen=True)
class HealthStatus:
    connection_state: ConnectionState
    websocket_connected: bool
    rest_reachable: bool
    last_message_age_ms: Optional[float]
    sequence_gap_detected: bool
    checked_at_utc: str


@dataclass(frozen=True)
class ReconciliationReport:
    matches: bool
    local_positions: Tuple[Position, ...]
    exchange_positions: Tuple[Position, ...]
    discrepancies: Tuple[str, ...]
    checked_at_utc: str


@dataclass(frozen=True)
class AuditRecord:
    """Forensic record of an outbound mutation, created before
    transmission. Deliberately minimal: it structurally CANNOT carry a
    signature, raw request, private key, API secret, or (where avoidable)
    a wallet address, because no such field exists on this type at all --
    the exclusion is guaranteed by the shape, not by filtering logic that
    could be gotten wrong."""

    request_id: str
    logical_action: str
    exchange_name: str
    adapter_version: str
    timestamp_utc: str
    payload_hash: str
    idempotency_key: str
