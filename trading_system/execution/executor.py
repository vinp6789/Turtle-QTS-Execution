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


def execute_place(trade_request: TradeRequest, decision: RiskDecision, order_manager: OrderManager) -> ExecutionResult:
    """Submits a NEW order for an already-approved TradeRequest. Refuses
    (ExecutionError, no OrderManager call made) unless decision.decision
    is exactly Decision.APPROVED -- REJECTED/BLOCKED/FAIL_SAFE are never
    submitted, and this function never re-evaluates or overrides that
    verdict."""
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

    limit_price = trade_request.entry_price if trade_request.order_type is OrderType.LIMIT else None
    snapshot = order_manager.place_order(
        symbol=trade_request.symbol,
        side=trade_request.side,
        order_type=trade_request.order_type,
        quantity=trade_request.quantity,
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
) -> ExecutionResult:
    """Amends an existing order by client_order_id. No TradeRequest/
    RiskDecision is involved -- OrderManager.amend_order's own state-
    legality checks (and its own ValueError if neither new_quantity nor
    new_limit_price is given) are the only validation; nothing here
    duplicates them."""
    if not isinstance(order_manager, OrderManager):
        raise ExecutionError(f"order_manager must be an OrderManager, got {type(order_manager).__name__}")
    if not isinstance(client_order_id, str) or not client_order_id.strip():
        raise ExecutionError("client_order_id must be a non-empty string")

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
