"""Result type for one trading cycle."""

from dataclasses import dataclass
from typing import Optional, Tuple

from exchange_adapter import HealthStatus, ReconciliationReport
from order_manager import OrderSnapshot

from ..execution import ExecutionResult
from ..portfolio_construction import ConstructionResult
from ..strategy import TradeIntent


@dataclass(frozen=True)
class CycleResult:
    """Surfaces every stage's outcome for one run_cycle() call. Nothing is
    silently dropped: intents/construction/executions are all present even
    when empty, so a caller can always distinguish "nothing to do this
    cycle" from "this cycle did not run"."""

    started: bool
    health: Optional[HealthStatus]
    resynced_orders: Tuple[OrderSnapshot, ...]
    reconciliation: ReconciliationReport
    intents: Tuple[TradeIntent, ...]
    construction: ConstructionResult
    executions: Tuple[ExecutionResult, ...]
    evaluated_at_utc: str
    # H-A fix: intents suppressed because a LIVE engine-owned order for the
    # same (symbol, reduce_only) already rests at the venue -- placing
    # another would stack duplicate exposure across cycles. Additive field
    # (defaulted) so existing constructions are unaffected; nothing is
    # silently dropped: `intents` still shows everything the strategies
    # emitted, and this field shows exactly what the filter withheld.
    suppressed_by_open_orders: Tuple[TradeIntent, ...] = ()
