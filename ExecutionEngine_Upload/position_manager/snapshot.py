"""Immutable snapshot types for the Position Manager.

ClosedLeg mirrors the frozen Research Engine trade-leg schema (sym, r,
pct, reason, conv, entry_day, exit_day, entry_px, exit_px, stop_d) field
for field, substituting UTC timestamps for the backtest's integer day
index (the live-appropriate analog of "which bar," not a change to any
strategy semantic) so a future reporting tool can consume live legs the
same way it consumes backtest legs.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from exchange_adapter import OrderSide, Symbol

from .states import PositionLifecycleState


@dataclass(frozen=True)
class PositionSnapshot:
    position_id: str
    lifecycle_state: PositionLifecycleState
    symbol: Symbol
    side: OrderSide
    intended_quantity: Decimal
    filled_quantity: Decimal
    remaining_quantity: Decimal
    avg_entry_price: Optional[Decimal]
    stop_price: Decimal
    stop_d: Decimal
    t1_price: Decimal
    t2_price: Decimal
    conviction: Optional[Decimal]
    realized_pnl: Decimal
    realized_r: Decimal
    fees_paid: Decimal
    funding_paid: Decimal
    created_at_utc: str
    updated_at_utc: str


@dataclass(frozen=True)
class ClosedLeg:
    position_id: str
    symbol: str
    r: Decimal
    pct: Decimal
    reason: str
    conv: Optional[Decimal]
    entry_at_utc: str
    exit_at_utc: str
    entry_px: Decimal
    exit_px: Decimal
    stop_d: Decimal
    quantity: Decimal
    fee: Decimal
    realized_pnl: Decimal
