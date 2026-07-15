"""Typed models for the Risk Manager.

Reuses frozen modules directly wherever their schema already covers a
need (Symbol/OrderSide/OrderType/TimeInForce/ExchangeCapabilities from
Module 5, PositionSnapshot from Module 7, PortfolioSnapshot from Module
8, State from Module 4, RiskProfileParams from Module 1). Only genuinely
new inputs -- a proposed trade, funding/correlation data, and this
module's own additional limits -- get new types here.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Optional, Tuple

from exchange_adapter import OrderSide, OrderType, Symbol, TimeInForce

from .errors import RiskManagerConfigurationError

# Frozen C4 methodology value, verbatim -- not configurable. Risk Manager
# applies this threshold to already-computed correlation figures; it
# never computes correlation itself.
CORRELATION_THRESHOLD = Decimal("0.5")


@dataclass(frozen=True)
class TradeRequest:
    symbol: Symbol
    side: OrderSide
    order_type: OrderType
    time_in_force: TimeInForce
    reduce_only: bool
    quantity: Decimal
    entry_price: Decimal
    stop_price: Decimal
    proposed_risk_amount: Decimal
    proposed_notional: Decimal
    proposed_margin_required: Decimal
    leverage: Decimal
    estimated_liquidation_price: Optional[Decimal] = None

    def __post_init__(self):
        for name in ("quantity", "entry_price", "stop_price", "proposed_notional", "proposed_margin_required", "leverage"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or value <= 0:
                raise RiskManagerConfigurationError(f"TradeRequest.{name} must be a positive Decimal, got {value!r}")
        if not isinstance(self.proposed_risk_amount, Decimal) or self.proposed_risk_amount <= 0:
            raise RiskManagerConfigurationError("TradeRequest.proposed_risk_amount must be a positive Decimal")
        if self.estimated_liquidation_price is not None and not isinstance(self.estimated_liquidation_price, Decimal):
            raise RiskManagerConfigurationError("TradeRequest.estimated_liquidation_price must be a Decimal or None")


@dataclass(frozen=True)
class FundingInfo:
    symbol: Symbol
    funding_rate: Decimal
    as_of_utc: str

    def __post_init__(self):
        if not isinstance(self.funding_rate, Decimal):
            raise RiskManagerConfigurationError("FundingInfo.funding_rate must be a Decimal")


@dataclass(frozen=True)
class CorrelationEntry:
    symbol: Symbol
    correlation: Decimal

    def __post_init__(self):
        if not isinstance(self.correlation, Decimal) or not (Decimal("-1") <= self.correlation <= Decimal("1")):
            raise RiskManagerConfigurationError("CorrelationEntry.correlation must be a Decimal in [-1, 1]")


@dataclass(frozen=True)
class CorrelationInfo:
    entries: Tuple[CorrelationEntry, ...]
    as_of_utc: str


@dataclass(frozen=True)
class RiskManagerLimits:
    """This module's own additive configuration -- covers dimensions
    Module 1's frozen RiskProfileParams was never scoped to include
    (leverage, liquidation buffer, funding, correlation, staleness).
    Immutable; validated at construction, never at evaluation time."""

    max_leverage: Decimal
    min_liquidation_buffer_pct: Decimal
    max_funding_rate_abs: Decimal
    max_correlated_positions: int
    max_stale_data_seconds: int

    def __post_init__(self):
        if not isinstance(self.max_leverage, Decimal) or self.max_leverage <= 0:
            raise RiskManagerConfigurationError("max_leverage must be a positive Decimal")
        if not isinstance(self.min_liquidation_buffer_pct, Decimal) or not (0 <= self.min_liquidation_buffer_pct):
            raise RiskManagerConfigurationError("min_liquidation_buffer_pct must be a non-negative Decimal")
        if not isinstance(self.max_funding_rate_abs, Decimal) or self.max_funding_rate_abs < 0:
            raise RiskManagerConfigurationError("max_funding_rate_abs must be a non-negative Decimal")
        if (
            not isinstance(self.max_correlated_positions, int)
            or isinstance(self.max_correlated_positions, bool)
            or self.max_correlated_positions < 0
        ):
            raise RiskManagerConfigurationError("max_correlated_positions must be a non-negative integer")
        if (
            not isinstance(self.max_stale_data_seconds, int)
            or isinstance(self.max_stale_data_seconds, bool)
            or self.max_stale_data_seconds <= 0
        ):
            raise RiskManagerConfigurationError("max_stale_data_seconds must be a positive integer")


class Decision(Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"
    FAIL_SAFE = "FAIL_SAFE"


class ReasonCode(Enum):
    OK = "OK"
    KILL_SWITCH_SOFT = "KILL_SWITCH_SOFT"
    KILL_SWITCH_HARD = "KILL_SWITCH_HARD"
    KILL_SWITCH_EMERGENCY = "KILL_SWITCH_EMERGENCY"
    ENGINE_STOPPED = "ENGINE_STOPPED"
    RISK_PER_TRADE_EXCEEDED = "RISK_PER_TRADE_EXCEEDED"
    PORTFOLIO_HEAT_EXCEEDED = "PORTFOLIO_HEAT_EXCEEDED"
    MAX_POSITIONS_EXCEEDED = "MAX_POSITIONS_EXCEEDED"
    INSUFFICIENT_MARGIN = "INSUFFICIENT_MARGIN"
    LEVERAGE_EXCEEDED = "LEVERAGE_EXCEEDED"
    LIQUIDATION_TOO_CLOSE = "LIQUIDATION_TOO_CLOSE"
    FUNDING_RATE_TOO_HIGH = "FUNDING_RATE_TOO_HIGH"
    CORRELATION_LIMIT_EXCEEDED = "CORRELATION_LIMIT_EXCEEDED"
    EXCHANGE_CAPABILITY_UNSUPPORTED = "EXCHANGE_CAPABILITY_UNSUPPORTED"
    NON_POSITIVE_EQUITY = "NON_POSITIVE_EQUITY"
    MISSING_REQUIRED_DATA = "MISSING_REQUIRED_DATA"
    STALE_DATA = "STALE_DATA"


@dataclass(frozen=True)
class RiskDecision:
    decision: Decision
    reason_codes: Tuple[ReasonCode, ...]
    violated_limits: Tuple[str, ...]
    calculated_exposure: Optional[Decimal]
    calculated_heat: Optional[Decimal]
    leverage: Optional[Decimal]
    liquidation_buffer: Optional[Decimal]
    funding_estimate: Optional[Decimal]
    timestamp_utc: str
    audit_metadata: Mapping[str, Any]

    def __post_init__(self):
        object.__setattr__(self, "audit_metadata", MappingProxyType(dict(self.audit_metadata)))
