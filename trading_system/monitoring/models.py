"""EngineSnapshot: one consistent, read-only observation of a running
Engine.

Two kinds of field, clearly separated:

  - LIVE fields are read fresh, every time capture_snapshot() is called:
    health, current_state, is_kill_switch_active, is_started,
    open_order_count, position_count, portfolio_snapshot, reconciliation.
    The last two of these (open_order_count, reconciliation) are None
    when the engine is not yet started -- they require a live adapter
    connection (ExchangeAdapter.get_orders()/reconcile() both raise
    ExchangeConnectionError otherwise), and monitoring must never crash
    just because nothing is connected yet; "not connected" is itself
    exactly the kind of fact a monitoring layer exists to report.

  - HISTORICAL fields are supplied by the CALLER, never discovered by
    this module on its own: last_cycle_completed_at_utc,
    last_cycle_construction, last_cycle_executions,
    last_cycle_resynced_order_count, last_error. Monitoring never calls
    run_cycle() (forbidden) and has no other way to know a cycle ever
    ran -- whoever DOES call run_cycle() (a future scheduling entrypoint)
    is responsible for handing its CycleResult's pieces to
    capture_snapshot() afterward.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

from exchange_adapter import HealthStatus, ReconciliationReport
from execution_state_machine import State
from portfolio_manager import PortfolioSnapshot

from ..execution import ExecutionResult
from ..portfolio_construction import ConstructionResult


@dataclass(frozen=True)
class EngineSnapshot:
    captured_at_utc: str

    # -- live --
    health: HealthStatus
    current_state: State
    is_kill_switch_active: bool
    is_started: bool
    open_order_count: Optional[int]
    position_count: int
    portfolio_snapshot: PortfolioSnapshot
    reconciliation: Optional[ReconciliationReport]

    # -- historical, caller-supplied --
    last_cycle_completed_at_utc: Optional[str] = None
    last_cycle_construction: Optional[ConstructionResult] = None
    last_cycle_executions: Optional[Tuple[ExecutionResult, ...]] = None
    last_cycle_resynced_order_count: Optional[int] = None
    last_error: Optional[str] = None
