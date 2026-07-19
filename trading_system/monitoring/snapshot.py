"""capture_snapshot(): the entire monitoring layer's one operation.

Every live field is a direct, unmodified call to an already-existing
read-only method -- this module computes nothing except the two trivial,
honest derivations noted inline (is_kill_switch_active, position_count).
It never calls place_order/amend_order/cancel_order, never calls
RiskManager.evaluate(), never calls Strategy.generate_intents(), and
never calls run_cycle() -- and, unlike orchestration.synchronize() (which
durably records resync outcomes), orchestration.reconcile() is used here
specifically because it is provably read-only: it only calls
PortfolioManager.get_snapshot()/PositionManager.get_position()/
unrealized_pnl() (all pure reads) and ExchangeAdapter.get_mark_price()/
reconcile() (both abstract READ methods on the frozen ExchangeAdapter
contract, no mutation). orchestration.synchronize() is deliberately never
called here, since resync_order() durably corrects order state -- a
mutation, however benign -- which would violate "monitoring must never
mutate engine state."
"""

from datetime import datetime, timezone
from typing import Callable, Optional, Tuple

from execution_state_machine import State
from orchestration import reconcile as orchestration_reconcile

from composition_root import Engine

from ..execution import ExecutionResult
from ..portfolio_construction import ConstructionResult
from .errors import MonitoringError
from .models import EngineSnapshot

# Independently declared here (not imported from risk_manager, which
# keeps this frozenset private) -- mirrors config/schema.py's own
# established pattern of independently declaring an allowed-value set
# that must stay consistent with another module's, rather than reaching
# into that module's private internals.
_KILL_SWITCH_STATES = frozenset({State.SOFT_KILL, State.HARD_KILL, State.EMERGENCY_KILL})


def _default_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def capture_snapshot(
    engine: Engine,
    *,
    last_cycle_completed_at_utc: Optional[str] = None,
    last_cycle_construction: Optional[ConstructionResult] = None,
    last_cycle_executions: Optional[Tuple[ExecutionResult, ...]] = None,
    last_cycle_resynced_order_count: Optional[int] = None,
    last_error: Optional[str] = None,
    clock: Callable[[], str] = _default_now,
) -> EngineSnapshot:
    """Observes the engine's current state. Never raises because of the
    ENGINE's condition (disconnected, kill-switched, empty) -- only for a
    wrong-type argument to this function itself. open_order_count and
    reconciliation are None when the engine is not yet started (both
    require a live adapter connection); every other field is always
    populated."""
    if not isinstance(engine, Engine):
        raise MonitoringError(f"engine must be a composition_root.Engine, got {type(engine).__name__}")

    is_started = engine.is_started
    health = engine.adapter.health()  # safe whether connected or not
    current_state = engine.execution_state_machine.current_state
    portfolio_snapshot = engine.portfolio_manager.get_snapshot()  # no adapter access, always safe
    position_count = len(portfolio_snapshot.open_position_ids)

    if is_started:
        open_order_count = len(engine.adapter.get_orders())
        reconciliation = orchestration_reconcile(engine)
    else:
        open_order_count = None
        reconciliation = None

    return EngineSnapshot(
        captured_at_utc=clock(),
        health=health,
        current_state=current_state,
        is_kill_switch_active=current_state in _KILL_SWITCH_STATES,
        is_started=is_started,
        open_order_count=open_order_count,
        position_count=position_count,
        portfolio_snapshot=portfolio_snapshot,
        reconciliation=reconciliation,
        last_cycle_completed_at_utc=last_cycle_completed_at_utc,
        last_cycle_construction=last_cycle_construction,
        last_cycle_executions=last_cycle_executions,
        last_cycle_resynced_order_count=last_cycle_resynced_order_count,
        last_error=last_error,
    )
