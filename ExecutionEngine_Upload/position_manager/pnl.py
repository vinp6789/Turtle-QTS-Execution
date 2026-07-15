"""Pure PnL and R-multiple math for the Position Manager.

Preserves the frozen Research Engine's exact formula structure from
turtle_backtest.py:

    frac = 0.5 if t1_hit else 1.0
    r = (exit_px / entry - 1) / stop_d * frac - FEE - SLIP

`frac` there is always exactly the fraction of the ORIGINAL position
being closed by this leg (0.5 for a T1 half-exit, 0.5 again for the
remainder's closing leg when T1 already fired, 1.0 for a leg that closes
the whole original position in one shot). Computing
`fraction = quantity_closed / original_intended_quantity` from real
fill quantities reproduces this exactly in the normal case and remains
correct even when real lot sizes don't split a position perfectly in
half -- it is a faithful generalization, not a reinterpretation.

FEE and SLIP in the backtest are fixed modeling constants (an assumed
cost per trade). This module has no such constants: it uses the REAL fee
reported on each Fill (Module 5's normalized fee field), converted into
the same R-units via the same stop_d divisor, which is the correct live
substitution for a backtest cost *assumption* -- not a reinterpretation
of the strategy's exit logic itself, which is untouched.
"""

from decimal import Decimal
from typing import Optional


def fraction_of_original(quantity_closed: Decimal, original_intended_quantity: Decimal) -> Decimal:
    if original_intended_quantity <= 0:
        raise ValueError("original_intended_quantity must be positive")
    return quantity_closed / original_intended_quantity


def fee_in_r_units(fee_amount: Decimal, entry_price: Decimal, quantity_closed: Decimal, stop_d: Decimal) -> Decimal:
    """Real fee (in quote currency) expressed in the same R-units as the
    rest of the formula, via the same stop_d divisor the price-return
    term uses -- keeps fee and price-return terms commensurable."""
    if entry_price <= 0 or quantity_closed <= 0 or stop_d <= 0:
        return Decimal("0")
    notional = entry_price * quantity_closed
    if notional <= 0:
        return Decimal("0")
    fee_fraction_of_notional = fee_amount / notional
    return fee_fraction_of_notional / stop_d


def leg_r_multiple(
    entry_price: Decimal,
    exit_price: Decimal,
    stop_d: Decimal,
    fraction: Decimal,
    fee_amount: Decimal,
    quantity_closed: Decimal,
) -> Decimal:
    if entry_price <= 0:
        raise ValueError("entry_price must be positive")
    if stop_d <= 0:
        raise ValueError("stop_d must be positive")
    price_return = (exit_price / entry_price - Decimal("1")) / stop_d * fraction
    fee_r = fee_in_r_units(fee_amount, entry_price, quantity_closed, stop_d)
    return price_return - fee_r


def leg_pct(entry_price: Decimal, exit_price: Decimal, fraction: Decimal) -> Decimal:
    if entry_price <= 0:
        raise ValueError("entry_price must be positive")
    return (exit_price / entry_price - Decimal("1")) * Decimal("100") * fraction


def leg_realized_pnl(entry_price: Decimal, exit_price: Decimal, quantity_closed: Decimal, fee_amount: Decimal) -> Decimal:
    """Direct currency PnL for one closing leg -- distinct from the
    risk-normalized R-multiple, tracked separately per the requirement
    for both realized PnL and R-multiple compatibility."""
    return (exit_price - entry_price) * quantity_closed - fee_amount


def unrealized_pnl(avg_entry_price: Decimal, mark_price: Decimal, remaining_quantity: Decimal) -> Decimal:
    return (mark_price - avg_entry_price) * remaining_quantity


def weighted_average_price(
    current_avg: Optional[Decimal], current_qty: Decimal, new_price: Decimal, new_qty: Decimal
) -> Decimal:
    if current_avg is None or current_qty == 0:
        return new_price
    total_qty = current_qty + new_qty
    return (current_avg * current_qty + new_price * new_qty) / total_qty
