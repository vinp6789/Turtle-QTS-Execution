"""Framework-agnostic serialization: turns AppState / EngineSnapshot into
plain JSON-serializable dicts.

This is the seam that keeps HTTP concerns out of the engine: it depends on
trading_system.monitoring / trading_system.reporting (read-only) and knows
NOTHING about FastAPI, requests, or responses. Every function returns a
dict/str built from already-computed values -- no trading logic, no new
computation. FastAPI (app.api.app) and Telegram (app.telegram) both consume
these same functions, so the two interfaces can never drift.

Decimals are emitted as strings (exact, no float rounding); enums as their
.value.
"""

from decimal import Decimal
from typing import Any, Dict

from trading_system.monitoring import EngineSnapshot
from trading_system.reporting import (
    cycle_summary,
    execution_summary,
    portfolio_summary,
    reconciliation_summary,
    risk_summary,
)

from app.runtime.state import AppState


def _d(value) -> str:
    return str(value) if isinstance(value, Decimal) else value


def health_dict(state: AppState) -> Dict[str, Any]:
    """Lightweight liveness/readiness -- does NOT run reconciliation, so it
    is cheap enough for frequent polling / container health checks."""
    engine = state.engine
    health = engine.adapter.health()
    return {
        "status": "ok",
        "engine_started": engine.is_started,
        "connection_state": health.connection_state.value,
        "rest_reachable": health.rest_reachable,
        "current_state": engine.execution_state_machine.current_state.value,
        "emergency_stopped": state.emergency_stopped,
        "cycles_run": state.cycles_run,
        "checked_at_utc": health.checked_at_utc,
    }


def _snapshot_dict(snapshot: EngineSnapshot) -> Dict[str, Any]:
    p = snapshot.portfolio_snapshot
    return {
        "captured_at_utc": snapshot.captured_at_utc,
        "is_started": snapshot.is_started,
        "current_state": snapshot.current_state.value,
        "kill_switch_active": snapshot.is_kill_switch_active,
        "connection_state": snapshot.health.connection_state.value,
        "rest_reachable": snapshot.health.rest_reachable,
        "open_order_count": snapshot.open_order_count,
        "position_count": snapshot.position_count,
        "portfolio": {
            "equity": _d(p.equity),
            "wallet_balance": _d(p.wallet_balance),
            "available_cash": _d(p.available_cash),
            "reserved_margin": _d(p.reserved_margin),
            "used_margin": _d(p.used_margin),
            "unrealized_pnl": _d(p.unrealized_pnl),
            "realized_pnl_cumulative": _d(p.realized_pnl_cumulative),
            "exposure": _d(p.exposure),
            "heat": _d(p.heat),
            "leverage": _d(p.leverage),
            "updated_at_utc": p.updated_at_utc,
        },
        "reconciliation": (
            None if snapshot.reconciliation is None
            else {
                "matches": snapshot.reconciliation.matches,
                "discrepancies": list(snapshot.reconciliation.discrepancies),
                "checked_at_utc": snapshot.reconciliation.checked_at_utc,
            }
        ),
        "last_cycle_completed_at_utc": snapshot.last_cycle_completed_at_utc,
        "last_cycle_resynced_order_count": snapshot.last_cycle_resynced_order_count,
        "last_error": snapshot.last_error,
    }


def status_dict(state: AppState) -> Dict[str, Any]:
    """Full status from the worker-produced snapshot (H3: read endpoints
    never touch the venue or the engine lock; freshness is cycle-cadence,
    carried in captured_at_utc)."""
    snapshot = state.snapshot_for_reads()
    data = _snapshot_dict(snapshot)
    data["cycles_run"] = state.cycles_run
    data["emergency_stopped"] = state.emergency_stopped
    data["started_at_utc"] = state.started_at_utc
    data["strategy_count"] = len(state.strategies)
    return data


def portfolio_dict(state: AppState) -> Dict[str, Any]:
    return _snapshot_dict(state.snapshot_for_reads())["portfolio"]


def reports_dict(state: AppState) -> Dict[str, str]:
    """All five human-readable reports in one call (H3: cached snapshot)."""
    snapshot = state.snapshot_for_reads()
    return {
        "portfolio": portfolio_summary(snapshot),
        "execution": execution_summary(snapshot),
        "cycle": cycle_summary(snapshot),
        "risk": risk_summary(snapshot),
        "reconciliation": reconciliation_summary(snapshot),
    }
