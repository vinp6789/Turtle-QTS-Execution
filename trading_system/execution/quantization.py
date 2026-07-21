"""Venue order quantization (fix for audit finding C2).

Hyperliquid rejects any order whose size does not conform to the asset's
szDecimals or whose price violates its tick rules. Nothing in the engine
previously enforced either, so any non-hand-picked quantity (e.g. sizing's
exact `2000/10.3 = 194.174757...`) was transmitted verbatim and rejected
at the venue -- including risk-REDUCING orders.

VENUE RULES IMPLEMENTED (Hyperliquid perpetuals):
  - Size must have at most `szDecimals` decimal places (per-asset, from
    the venue's `meta` endpoint universe).
  - Price must have at most 5 significant figures AND at most
    (6 - szDecimals) decimal places (MAX_DECIMALS = 6 for perps).
    Integer prices are ALWAYS allowed regardless of significant figures.
  Spot (MAX_DECIMALS = 8) is out of scope: the engine's capabilities are
  perps-only (hyperliquid_adapter/capabilities.py).

DETERMINISTIC ROUNDING POLICY (never silently increases risk):
  - Size: ROUND_DOWN (toward zero). Exposure/notional/margin can only
    SHRINK relative to what RiskManager approved -- never grow. A size
    that rounds to zero is an impossible order and is REJECTED before
    transmission, never transmitted as dust or bumped up.
  - Price: directional. BUY floors (never bid more than approved);
    SELL ceils (never offer less than approved). The transmitted limit
    is always equal-or-better than the risk-approved price, so the
    worst-case fill can never be worse than what was approved. The cost
    of this conservatism is that a marginally-marketable order may rest
    instead of filling -- a missed fill, never a worse fill.

WHERE THIS RUNS (and why): at trading_system.execution -- the last point
BEFORE the frozen execution stack. Quantizing any later (e.g. inside the
frozen adapter) would make OrderManager's durable SUBMIT event disagree
with what the venue holds: FULL_FILL (filled >= quantity) could never
trigger for a rounded-down order, wedging its lifecycle open forever and
desynchronizing accounting. Quantizing here means books, events, replay,
fills, and the venue all carry the same on-grid values.

Pure Decimal arithmetic; no I/O, no float, no state.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_DOWN, ROUND_FLOOR
from typing import Mapping, Optional

from exchange_adapter import OrderSide

from .errors import ExecutionError

# Hyperliquid perpetuals price constraints.
PRICE_SIG_FIGS = 5
PRICE_MAX_DECIMALS = 6  # minus szDecimals


@dataclass(frozen=True)
class SymbolRules:
    """Per-asset quantization rules, sourced from the venue's meta
    endpoint (`universe[i].szDecimals`)."""

    sz_decimals: int

    def __post_init__(self):
        if not isinstance(self.sz_decimals, int) or isinstance(self.sz_decimals, bool) \
                or not (0 <= self.sz_decimals <= PRICE_MAX_DECIMALS):
            raise ExecutionError(
                f"sz_decimals must be an int in [0, {PRICE_MAX_DECIMALS}], got {self.sz_decimals!r}"
            )

    @property
    def max_price_decimals(self) -> int:
        return PRICE_MAX_DECIMALS - self.sz_decimals


# symbol.value -> SymbolRules. Plain immutable-by-convention mapping;
# built once at startup, replaced wholesale on refresh (atomic rebind),
# so concurrent readers never observe a half-updated set.
QuantizationRules = Mapping[str, SymbolRules]


def quantize_size(quantity: Decimal, rules: SymbolRules) -> Decimal:
    """Rounds DOWN to the asset's szDecimals. May return zero -- the
    caller must treat that as an impossible order and reject it."""
    if not isinstance(quantity, Decimal):
        raise ExecutionError(f"quantity must be a Decimal, got {type(quantity).__name__}")
    return quantity.quantize(Decimal(1).scaleb(-rules.sz_decimals), rounding=ROUND_DOWN)


def quantize_price(price: Decimal, side: OrderSide, rules: SymbolRules) -> Decimal:
    """Rounds to the venue's price grid, directionally (BUY floor / SELL
    ceil). Integer inputs pass through unchanged (always venue-legal).
    May return zero for a BUY of a sub-tick price -- the caller must
    reject that as impossible."""
    if not isinstance(price, Decimal):
        raise ExecutionError(f"price must be a Decimal, got {type(price).__name__}")
    if not isinstance(side, OrderSide):
        raise ExecutionError(f"side must be an OrderSide, got {type(side).__name__}")
    if price == price.to_integral_value():
        # Integer prices are always allowed, at any magnitude.
        return price.to_integral_value()

    mode = ROUND_FLOOR if side is OrderSide.BUY else ROUND_CEILING
    # Exponent that keeps PRICE_SIG_FIGS significant figures...
    sig_exponent = price.adjusted() - (PRICE_SIG_FIGS - 1)
    # ...intersected with the decimal-places cap; the COARSER grid wins.
    exponent = max(sig_exponent, -rules.max_price_decimals)
    # Never coarser than the integer grid: integers are always legal, so
    # a >5-sig-fig magnitude rounds to the nearest integer, not to tens.
    if exponent > 0:
        exponent = 0
    return price.quantize(Decimal(1).scaleb(exponent), rounding=mode)
