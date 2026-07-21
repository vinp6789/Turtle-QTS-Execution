"""Thin adapter between an already-approved TradeRequest and OrderManager.

Every byte of order-lifecycle logic (idempotency, state legality, audit
records, venue transmission) already lives in OrderManager
(order_manager/manager.py) and, beneath it, ExchangeAdapter
(exchange_adapter/adapter.py). This module adds none of its own: each
function here is a direct, one-to-one call to the corresponding
OrderManager method, with no re-validation of anything OrderManager
already validates and no computation of quantity, leverage, liquidation
price, or conviction -- those stages (sizing, portfolio_construction) are
already finished by the time a TradeRequest reaches here.

This module never calls RiskManager.evaluate() -- it only reads the
RiskDecision a caller already obtained from
trading_system.portfolio_construction and refuses to submit unless that
decision is APPROVED. It never touches ExchangeAdapter directly (only
OrderManager, which itself is the only thing that talks to the adapter),
and it never touches orchestration's synchronize()/reconcile()/dispatch()
-- this is the write/submit path; those are the read/observe path.
"""

from decimal import Decimal
from typing import Optional

from exchange_adapter import OrderType
from order_manager import OrderManager
from risk_manager import Decision, RiskDecision, TradeRequest

from .errors import ExecutionError
from .models import ExecutionOperation, ExecutionResult
from .quantization import QuantizationRules, quantize_price, quantize_size


def _rules_for(symbol, rules: Optional[QuantizationRules]):
    """None rules disables quantization entirely (paper/mock mode --
    prior behavior, byte-identical). With rules present, a symbol they do
    not cover is REFUSED: transmitting an unquantized order to a venue
    that enforces quantization is a guaranteed rejection at best and an
    untracked precision surprise at worst -- fail closed instead (C2)."""
    if rules is None:
        return None
    symbol_rules = rules.get(symbol.value)
    if symbol_rules is None:
        raise ExecutionError(
            f"no quantization rules for symbol {symbol.value!r}: refusing to "
            "transmit an unquantized order to a quantized venue (C2 fail-closed). "
            "Refresh the venue metadata or remove the symbol from the universe."
        )
    return symbol_rules


def execute_place(
    trade_request: TradeRequest,
    decision: RiskDecision,
    order_manager: OrderManager,
    *,
    rules: Optional[QuantizationRules] = None,
) -> ExecutionResult:
    """Submits a NEW order for an already-approved TradeRequest. Refuses
    (ExecutionError, no OrderManager call made) unless decision.decision
    is exactly Decision.APPROVED -- REJECTED/BLOCKED/FAIL_SAFE are never
    submitted, and this function never re-evaluates or overrides that
    verdict.

    rules (C2): optional venue quantization rules. When provided, size is
    rounded DOWN to szDecimals and a LIMIT price to the venue price grid
    (BUY floor / SELL ceil) BEFORE OrderManager durably records the order,
    so books, events, replay, and the venue all carry the same on-grid
    values, and the transmitted order is never larger or worse-priced than
    what RiskManager approved. An order whose size or price quantizes to
    zero is impossible at this venue and is rejected with no OrderManager
    call (nothing persisted, nothing transmitted)."""
    if not isinstance(trade_request, TradeRequest):
        raise ExecutionError(f"trade_request must be a TradeRequest, got {type(trade_request).__name__}")
    if not isinstance(decision, RiskDecision):
        raise ExecutionError(f"decision must be a RiskDecision, got {type(decision).__name__}")
    if not isinstance(order_manager, OrderManager):
        raise ExecutionError(f"order_manager must be an OrderManager, got {type(order_manager).__name__}")
    if decision.decision is not Decision.APPROVED:
        raise ExecutionError(
            f"refusing to execute a TradeRequest for {trade_request.symbol.value}: "
            f"its RiskDecision is {decision.decision.value}, not APPROVED -- "
            "execution never submits a trade RiskManager did not approve"
        )

    quantity = trade_request.quantity
    limit_price = trade_request.entry_price if trade_request.order_type is OrderType.LIMIT else None
    symbol_rules = _rules_for(trade_request.symbol, rules)
    if symbol_rules is not None:
        quantity = quantize_size(quantity, symbol_rules)
        if quantity <= 0:
            raise ExecutionError(
                f"impossible order for {trade_request.symbol.value}: size "
                f"{trade_request.quantity} quantizes to zero at szDecimals="
                f"{symbol_rules.sz_decimals} -- rejected before transmission"
            )
        if limit_price is not None:
            limit_price = quantize_price(limit_price, trade_request.side, symbol_rules)
            if limit_price <= 0:
                raise ExecutionError(
                    f"impossible order for {trade_request.symbol.value}: price "
                    f"{trade_request.entry_price} quantizes to zero -- rejected before transmission"
                )

    snapshot = order_manager.place_order(
        symbol=trade_request.symbol,
        side=trade_request.side,
        order_type=trade_request.order_type,
        quantity=quantity,
        limit_price=limit_price,
        time_in_force=trade_request.time_in_force,
        reduce_only=trade_request.reduce_only,
    )
    return ExecutionResult(
        operation=ExecutionOperation.PLACE, order_snapshot=snapshot, trade_request=trade_request, decision=decision,
    )


def execute_amend(
    client_order_id: str,
    order_manager: OrderManager,
    *,
    new_quantity: Optional[Decimal] = None,
    new_limit_price: Optional[Decimal] = None,
    rules: Optional[QuantizationRules] = None,
) -> ExecutionResult:
    """Amends an existing order by client_order_id. No TradeRequest/
    RiskDecision is involved -- OrderManager.amend_order's own state-
    legality checks (and its own ValueError if neither new_quantity nor
    new_limit_price is given) are the only validation; nothing here
    duplicates them.

    rules (C2): when provided, the amended values are quantized the same
    way as a placement -- size DOWN, price directional by the ORDER's own
    side (read from OrderManager's snapshot) -- before the frozen amend
    path transmits them. A new_quantity that quantizes to zero is rejected
    (an amend-to-nothing is a cancel, and must be requested as one)."""
    if not isinstance(order_manager, OrderManager):
        raise ExecutionError(f"order_manager must be an OrderManager, got {type(order_manager).__name__}")
    if not isinstance(client_order_id, str) or not client_order_id.strip():
        raise ExecutionError("client_order_id must be a non-empty string")

    if rules is not None and (new_quantity is not None or new_limit_price is not None):
        existing = order_manager.get_order_status(client_order_id)
        symbol_rules = _rules_for(existing.symbol, rules)
        if new_quantity is not None:
            new_quantity = quantize_size(new_quantity, symbol_rules)
            if new_quantity <= 0:
                raise ExecutionError(
                    f"impossible amend for {client_order_id!r}: new_quantity quantizes to zero "
                    "-- use cancel instead"
                )
        if new_limit_price is not None:
            new_limit_price = quantize_price(new_limit_price, existing.side, symbol_rules)
            if new_limit_price <= 0:
                raise ExecutionError(
                    f"impossible amend for {client_order_id!r}: new_limit_price quantizes to zero"
                )

    snapshot = order_manager.amend_order(client_order_id, new_quantity=new_quantity, new_limit_price=new_limit_price)
    return ExecutionResult(operation=ExecutionOperation.AMEND, order_snapshot=snapshot)


def execute_cancel(client_order_id: str, order_manager: OrderManager) -> ExecutionResult:
    """Cancels an existing order by client_order_id."""
    if not isinstance(order_manager, OrderManager):
        raise ExecutionError(f"order_manager must be an OrderManager, got {type(order_manager).__name__}")
    if not isinstance(client_order_id, str) or not client_order_id.strip():
        raise ExecutionError("client_order_id must be a non-empty string")

    snapshot = order_manager.cancel_order(client_order_id)
    return ExecutionResult(operation=ExecutionOperation.CANCEL, order_snapshot=snapshot)
