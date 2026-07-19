"""Typed models for the strategy interface.

TradeIntent expresses WHAT a strategy wants -- direction and conviction --
never HOW MUCH or WHETHER it is allowed: no quantity, no notional, no
margin, no leverage field exists here. Turning an intent into a fully
specified risk_manager.TradeRequest is trading_system.sizing's job (a
future milestone); deciding whether that TradeRequest may proceed remains
exclusively RiskManager.evaluate()'s job. This module calls neither.

StrategyContext bundles everything a Strategy may READ to decide. It
carries no handle capable of a mutation (no OrderManager, no RiskManager,
no write-capable adapter method) -- only already-computed snapshots plus
a read-only MarketDataView for on-demand price/funding lookups.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Tuple

from exchange_adapter import OrderSide, OrderType, Symbol, TimeInForce
from execution_state_machine import State
from portfolio_manager import PortfolioSnapshot
from position_manager import PositionSnapshot

from ..market_data import MarketDataView
from .errors import StrategyError


@dataclass(frozen=True)
class TradeIntent:
    """A strategy's expressed desire to open, add to, or reduce a
    position for one symbol. Not a sized order, not a risk-checked order
    -- purely direction, conviction, and the price levels the strategy
    itself is responsible for choosing (stop/T1/T2), the same levels
    position_manager.PositionSnapshot already tracks once a position
    exists."""

    symbol: Symbol
    side: OrderSide
    order_type: OrderType
    time_in_force: TimeInForce
    reduce_only: bool
    stop_price: Decimal
    conviction: Optional[Decimal] = None
    limit_price: Optional[Decimal] = None
    t1_price: Optional[Decimal] = None
    t2_price: Optional[Decimal] = None

    def __post_init__(self):
        if not isinstance(self.symbol, Symbol):
            raise StrategyError(f"TradeIntent.symbol must be a Symbol, got {type(self.symbol).__name__}")
        if not isinstance(self.side, OrderSide):
            raise StrategyError(f"TradeIntent.side must be an OrderSide, got {type(self.side).__name__}")
        if not isinstance(self.order_type, OrderType):
            raise StrategyError(f"TradeIntent.order_type must be an OrderType, got {type(self.order_type).__name__}")
        if not isinstance(self.time_in_force, TimeInForce):
            raise StrategyError(f"TradeIntent.time_in_force must be a TimeInForce, got {type(self.time_in_force).__name__}")
        if not isinstance(self.stop_price, Decimal) or self.stop_price <= 0:
            raise StrategyError(f"TradeIntent.stop_price must be a positive Decimal, got {self.stop_price!r}")
        if self.conviction is not None and (
            not isinstance(self.conviction, Decimal) or not (Decimal("-1") <= self.conviction <= Decimal("1"))
        ):
            raise StrategyError(f"TradeIntent.conviction must be a Decimal in [-1, 1] or None, got {self.conviction!r}")
        for field_name in ("limit_price", "t1_price", "t2_price"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, Decimal) or value <= 0):
                raise StrategyError(f"TradeIntent.{field_name} must be a positive Decimal or None, got {value!r}")


@dataclass(frozen=True)
class StrategyContext:
    """Everything a Strategy may read for one decision cycle. Immutable;
    a fresh StrategyContext is built per cycle by a future milestone
    (trading_system.scheduling, deferred) -- this type has no
    construction-time knowledge of when or how often it is built."""

    universe: Tuple[Symbol, ...]
    portfolio_snapshot: PortfolioSnapshot
    open_positions: Tuple[PositionSnapshot, ...]
    kill_switch_state: State
    market_data: MarketDataView
    evaluated_at_utc: str

    def __post_init__(self):
        if not all(isinstance(s, Symbol) for s in self.universe):
            raise StrategyError("StrategyContext.universe must contain only Symbol instances")
        if not isinstance(self.portfolio_snapshot, PortfolioSnapshot):
            raise StrategyError(
                f"StrategyContext.portfolio_snapshot must be a PortfolioSnapshot, "
                f"got {type(self.portfolio_snapshot).__name__}"
            )
        if not all(isinstance(p, PositionSnapshot) for p in self.open_positions):
            raise StrategyError("StrategyContext.open_positions must contain only PositionSnapshot instances")
        if not isinstance(self.kill_switch_state, State):
            raise StrategyError(
                f"StrategyContext.kill_switch_state must be a State, got {type(self.kill_switch_state).__name__}"
            )
        if not isinstance(self.market_data, MarketDataView):
            raise StrategyError(
                f"StrategyContext.market_data must be a MarketDataView, got {type(self.market_data).__name__}"
            )
        if not isinstance(self.evaluated_at_utc, str) or not self.evaluated_at_utc.strip():
            raise StrategyError("StrategyContext.evaluated_at_utc must be a non-empty ISO 8601 string")
