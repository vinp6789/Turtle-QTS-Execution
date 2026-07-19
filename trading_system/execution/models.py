"""Result types for the execution layer."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from order_manager import OrderSnapshot
from risk_manager import RiskDecision, TradeRequest


class ExecutionOperation(Enum):
    PLACE = "PLACE"
    AMEND = "AMEND"
    CANCEL = "CANCEL"


@dataclass(frozen=True)
class ExecutionResult:
    """Surfaces what OrderManager actually did, tagged with which
    operation produced it. trade_request/decision are populated only for
    a PLACE result (the only operation with a sizing/risk pipeline behind
    it) -- AMEND/CANCEL operate on an existing order by client_order_id
    and have no TradeRequest of their own."""

    operation: ExecutionOperation
    order_snapshot: OrderSnapshot
    trade_request: Optional[TradeRequest] = None
    decision: Optional[RiskDecision] = None
