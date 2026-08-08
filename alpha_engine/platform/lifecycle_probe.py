"""ENGINE_TEST lifecycle probe: one entry, one reduce-only exit, then silence.

WHAT THIS IS. Infrastructure validation. It exists to drive exactly one
complete pass through the canonical execution path --

    Strategy -> Portfolio -> Sizing -> Risk -> Execution -> Quantization
    -> Adapter -> venue -> Fill -> POSITION_OPENED -> reduce-only exit
    -> Fill -> POSITION_CLOSED -> Accounting

-- against a real venue, so that the close half of that path stops being
theoretical. As of the 2026-08-08 audit NO production component had ever
emitted a reduce_only=True intent, which is why zero POSITION_CLOSED
events exist anywhere in this repository's history.

WHAT THIS IS NOT. Not research, not a trading strategy, not evidence of
anything about alpha. It is registered as PluginKind.ENGINE_TEST and must
never appear in the Alpha Library, Research Ledger, a campaign, the
Mechanism Atlas, a scorecard, or any profitability claim. Its expectancy
is irrelevant and unmeasured by construction.

THE SAFETY MODEL -- STATED HONESTLY.

    small notional + supervised execution + manual UI close fallback

It is NOT "a risk-limited, stop-protected trade". There is currently no
venue-side trigger order (hyperliquid_adapter.capabilities declares
supports_trigger_orders=False, because OrderRequest carries no trigger
price) and no production stop-breach monitor. The stop prices below are
SIZING INPUTS ONLY. Nothing will act on them. If this process stops
between entry and exit, the position remains open at the venue with no
protection until closed by hand.

HOW THE NOTIONAL IS KEPT SMALL. Not by a new parameter and not by
weakening any risk control -- by the EXISTING sizing identity in
trading_system.sizing.calculator:

    risk_amount = equity * risk_pct_per_trade      (unchanged: 0.5%)
    size        = risk_amount / |entry - stop|

A deliberately WIDE entry stop therefore yields a SMALL size. At equity
999 and BTC ~64,900 a 30% stop distance gives ~0.00026 BTC, about $17 --
above the venue's $10 minimum order value and ~1.7% of the account, while
risk_amount stays exactly what the risk profile already says it is.

HOW THE EXIT IS GUARANTEED TO CLOSE FULLY. The same identity, inverted: a
NARROW exit stop yields a size LARGER than the open position, and
reduce_only=True then clamps it at the venue to exactly the remaining
quantity. Over-asking is safe precisely because reduce-only cannot
increase a position; under-asking would silently leave a residue.
exit_stop_fraction is therefore a fraction of the entry's, never larger.
"""

from decimal import Decimal
from typing import Optional, Tuple

from exchange_adapter import OrderSide, OrderType, Symbol, TimeInForce

from trading_system.strategy import Strategy, StrategyContext, TradeIntent


class LifecycleProbeStrategy(Strategy):
    """Flat -> entry. Position open -> reduce-only exit. Closed -> silence.

    The transition is driven by StrategyContext.open_positions, which the
    PositionManager reconstructs from FILL events -- never from the fact
    that an order was submitted. A submitted-but-unfilled entry leaves
    open_positions empty, so no exit is emitted and the entry is simply
    re-evaluated next cycle (the engine's own duplicate-order suppression,
    keyed on (symbol, reduce_only), prevents a second resting order).
    """

    __slots__ = ("_symbol", "_stop_fraction", "_exit_stop_fraction",
                 "_limit_slip", "_saw_position", "_done", "_features")

    # The thesis is CONSTANT and honest: this strategy has no view on
    # price. Recording it prevents a future reader from mistaking an
    # infrastructure test for a trading decision.
    THESIS = ("Infrastructure validation only: drive one entry and one "
              "reduce-only exit through the canonical execution path. No "
              "market view, no signal, no expected edge.")

    def __init__(
        self,
        symbol: Symbol,
        *,
        stop_fraction: Decimal = Decimal("0.30"),
        exit_stop_fraction: Decimal = Decimal("0.075"),
        limit_slip: Decimal = Decimal("0.001"),
    ):
        if not isinstance(symbol, Symbol):
            raise TypeError(f"symbol must be a Symbol, got {type(symbol).__name__}")
        for nm, v in (("stop_fraction", stop_fraction),
                      ("exit_stop_fraction", exit_stop_fraction),
                      ("limit_slip", limit_slip)):
            if not isinstance(v, Decimal) or v <= 0:
                raise ValueError(f"{nm} must be a positive Decimal, got {v!r}")
        if stop_fraction >= Decimal("1"):
            raise ValueError("stop_fraction must be < 1 (a stop below zero is meaningless)")
        if exit_stop_fraction > stop_fraction:
            # Guarantees the computed exit size >= the open position, so
            # reduce_only clamps to a FULL close rather than a partial one.
            raise ValueError(
                "exit_stop_fraction must be <= stop_fraction, otherwise the "
                "sized exit could be smaller than the position and leave a residue")
        self._symbol = symbol
        self._stop_fraction = stop_fraction
        self._exit_stop_fraction = exit_stop_fraction
        self._limit_slip = limit_slip
        self._saw_position = False
        self._done = False
        # id(intent) -> the point-in-time scalars this decision used.
        # Recorded at the decision instant because a mark price cannot be
        # recovered later without look-ahead risk.
        self._features = {}

    @property
    def name(self) -> str:
        return "lifecycle_probe"

    @property
    def thesis(self) -> str:
        return self.THESIS

    @property
    def features_by_intent(self):
        """id(intent) -> {feature: value}, for the attribution writer.
        Same-cycle only; the writer clears its own maps each cycle."""
        return self._features

    @property
    def completed(self) -> bool:
        """True once a position has been opened and subsequently closed."""
        return self._done

    def _position(self, context: StrategyContext):
        for p in context.open_positions:
            if p.symbol == self._symbol:
                return p
        return None

    def generate_intents(self, context: StrategyContext) -> Tuple[TradeIntent, ...]:
        if self._done:
            return ()

        position = self._position(context)

        if position is not None:
            # A real fill exists. Ask to close it, reduce-only.
            self._saw_position = True
            mark = context.market_data.get_mark_price(self._symbol).price
            intent = TradeIntent(
                symbol=self._symbol,
                side=OrderSide.SELL if position.side is OrderSide.BUY else OrderSide.BUY,
                order_type=OrderType.LIMIT,
                time_in_force=TimeInForce.GTC,
                reduce_only=True,
                # Sizing input only -- see module docstring. Narrow, so the
                # computed size exceeds the position and reduce_only clamps.
                stop_price=mark * (Decimal("1") - self._exit_stop_fraction)
                if position.side is OrderSide.BUY
                else mark * (Decimal("1") + self._exit_stop_fraction),
                # Priced through the mark so the exit is marketable.
                limit_price=mark * (Decimal("1") - self._limit_slip)
                if position.side is OrderSide.BUY
                else mark * (Decimal("1") + self._limit_slip),
            )
            self._features[id(intent)] = {
                "mark_price": mark,
                "position_side": position.side.value,
                "position_remaining_quantity": position.remaining_quantity,
                "phase": "exit",
            }
            return (intent,)

        if self._saw_position:
            # Had a position, now flat: the lifecycle completed. Latch shut.
            self._done = True
            return ()

        # Never opened yet: one entry.
        mark = context.market_data.get_mark_price(self._symbol).price
        intent = TradeIntent(
            symbol=self._symbol,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.GTC,
            reduce_only=False,
            # WIDE -- this is what makes the notional small. Sizing input only.
            stop_price=mark * (Decimal("1") - self._stop_fraction),
            limit_price=mark * (Decimal("1") + self._limit_slip),
        )
        self._features[id(intent)] = {
            "mark_price": mark,
            "stop_fraction": self._stop_fraction,
            "limit_slip": self._limit_slip,
            "phase": "entry",
        }
        return (intent,)
