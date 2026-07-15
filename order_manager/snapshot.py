"""Immutable order snapshot -- the Order Manager's own normalized view of
an order's lifecycle. Distinct from exchange_adapter.Order (the exchange's
normalized view, which Module 6 consumes but never re-exposes directly)."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from exchange_adapter import OrderSide, OrderType, Symbol, TimeInForce

from .states import OrderLifecycleState


@dataclass(frozen=True)
class OrderSnapshot:
    client_order_id: str
    lifecycle_state: OrderLifecycleState
    exchange_order_id: Optional[str]
    symbol: Symbol
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    filled_quantity: Decimal
    limit_price: Optional[Decimal]
    time_in_force: TimeInForce
    reduce_only: bool
    created_at_utc: str
    updated_at_utc: str
    reject_reason: Optional[str] = None
