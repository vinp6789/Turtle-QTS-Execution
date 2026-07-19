"""Converts a TradeIntent into a risk_manager.TradeRequest.

Pure arithmetic only: no adapter access, no OrderManager, no RiskManager
call, no network, no persistence. Every number this module needs is
either already on the TradeIntent, or is passed in explicitly by the
caller -- nothing is fetched, cached, or fabricated here. This is
deliberate: trading_system.portfolio_construction (the caller) owns
resolving a current price via MarketDataView; this module never imports
composition_root or exchange_adapter's adapter classes at all.

Sizing modes implement config.RiskProfileParams.sizing_mode (the frozen
Module 1 schema's own SUPPORTED_SIZING_MODES = {"fixed", "vol_targeted",
"conviction_weighted"}):

  - fixed: risk_amount = equity * risk_pct_per_trade; the sizing distance
    is the strategy's own literal |entry - stop_price|.
  - conviction_weighted: same risk_amount, scaled by
    abs(TradeIntent.conviction) -- requires conviction to be set; there is
    no sensible default for "how much conviction" so sizing refuses
    rather than guessing.
  - vol_targeted: risk_amount = equity * risk_pct_per_trade; the sizing
    distance is entry_price * volatility (a caller-supplied fractional
    volatility estimate, e.g. ATR% or a return stdev) instead of the
    literal stop distance -- the standard vol-targeting formula. No
    default volatility exists anywhere in this repository (no historical
    price series is available to any frozen module), so sizing refuses
    when it is not supplied rather than fabricating a number.

estimated_liquidation_price is ALWAYS computed, never left None:
risk_manager/manager.py's evaluate() treats a None
estimated_liquidation_price as MISSING_REQUIRED_DATA and unconditionally
returns FAIL_SAFE (see its Precedence-2 check), so leaving it unset would
make every TradeRequest this module produces permanently unapprovable.
The formula used is the standard, venue-agnostic isolated-margin
approximation (ignoring funding accrual):

    long:  liquidation_price = entry_price * (1 - 1/leverage + mmr)
    short: liquidation_price = entry_price * (1 + 1/leverage - mmr)

where mmr (maintenance_margin_rate) is an explicit, caller-supplied
input -- never hardcoded. No Hyperliquid-specific (or any venue-specific)
margin-tier knowledge is embedded here, keeping this module exchange-
agnostic; a caller sources mmr however it chooses (a conservative
constant, or eventually a real venue margin table via a future
milestone).
"""

from decimal import Decimal
from typing import Optional

from config import RiskProfileParams
from exchange_adapter import OrderSide
from risk_manager import TradeRequest

from ..strategy import TradeIntent
from .errors import SizingError


def _as_decimal(value) -> Decimal:
    """Converts a frozen dataclass's float field (e.g.
    RiskProfileParams.risk_pct_per_trade) to Decimal via its string
    representation -- never a direct float->Decimal binary conversion --
    matching the repository's own established pattern
    (hyperliquid_adapter/codec.py's _decimal)."""
    return Decimal(str(value))


def size_intent(
    intent: TradeIntent,
    *,
    equity: Decimal,
    risk_profile: RiskProfileParams,
    current_price: Decimal,
    maintenance_margin_rate: Decimal,
    target_leverage: Decimal = Decimal("1"),
    volatility: Optional[Decimal] = None,
) -> TradeRequest:
    """Builds a fully-specified TradeRequest. Raises SizingError if the
    chosen sizing_mode's required input is missing or if the resulting
    numbers would be degenerate (non-positive). Never calls
    RiskManager.evaluate() -- whether the result is actually PERMITTED
    remains exclusively RiskManager's decision."""
    if not isinstance(intent, TradeIntent):
        raise SizingError(f"intent must be a TradeIntent, got {type(intent).__name__}")
    if not isinstance(equity, Decimal) or equity <= 0:
        raise SizingError(f"equity must be a positive Decimal, got {equity!r}")
    if not isinstance(risk_profile, RiskProfileParams):
        raise SizingError(f"risk_profile must be a RiskProfileParams, got {type(risk_profile).__name__}")
    if not isinstance(current_price, Decimal) or current_price <= 0:
        raise SizingError(f"current_price must be a positive Decimal, got {current_price!r}")
    if not isinstance(maintenance_margin_rate, Decimal) or not (Decimal("0") <= maintenance_margin_rate < Decimal("1")):
        raise SizingError(
            f"maintenance_margin_rate must be a Decimal in [0, 1), got {maintenance_margin_rate!r}"
        )
    if not isinstance(target_leverage, Decimal) or target_leverage <= 0:
        raise SizingError(f"target_leverage must be a positive Decimal, got {target_leverage!r}")

    entry_price = intent.limit_price if intent.limit_price is not None else current_price
    risk_pct = _as_decimal(risk_profile.risk_pct_per_trade)
    sizing_mode = risk_profile.sizing_mode

    if sizing_mode == "fixed":
        risk_amount = equity * risk_pct
        distance = abs(entry_price - intent.stop_price)
    elif sizing_mode == "conviction_weighted":
        if intent.conviction is None:
            raise SizingError(
                "conviction_weighted sizing requires TradeIntent.conviction to be set "
                "-- there is no default 'how much conviction'"
            )
        risk_amount = equity * risk_pct * abs(intent.conviction)
        distance = abs(entry_price - intent.stop_price)
    elif sizing_mode == "vol_targeted":
        if volatility is None:
            raise SizingError(
                "vol_targeted sizing requires an explicit volatility input -- "
                "no historical price series is available anywhere in this build to derive one"
            )
        if not isinstance(volatility, Decimal) or volatility <= 0:
            raise SizingError(f"volatility must be a positive Decimal, got {volatility!r}")
        risk_amount = equity * risk_pct
        distance = entry_price * volatility
    else:
        raise SizingError(f"unsupported sizing_mode: {sizing_mode!r}")

    if distance <= 0:
        raise SizingError(
            f"sizing distance must be positive, got {distance!r} "
            "(entry_price/stop_price/volatility inputs are degenerate)"
        )

    quantity = risk_amount / distance
    proposed_notional = quantity * entry_price
    proposed_margin_required = proposed_notional / target_leverage

    if intent.side is OrderSide.BUY:
        estimated_liquidation_price = entry_price * (
            Decimal("1") - Decimal("1") / target_leverage + maintenance_margin_rate
        )
    else:
        estimated_liquidation_price = entry_price * (
            Decimal("1") + Decimal("1") / target_leverage - maintenance_margin_rate
        )

    return TradeRequest(
        symbol=intent.symbol,
        side=intent.side,
        order_type=intent.order_type,
        time_in_force=intent.time_in_force,
        reduce_only=intent.reduce_only,
        quantity=quantity,
        entry_price=entry_price,
        stop_price=intent.stop_price,
        proposed_risk_amount=risk_amount,
        proposed_notional=proposed_notional,
        proposed_margin_required=proposed_margin_required,
        leverage=target_leverage,
        estimated_liquidation_price=estimated_liquidation_price,
    )
