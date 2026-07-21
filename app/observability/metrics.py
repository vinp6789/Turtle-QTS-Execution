"""Prometheus text-exposition metrics, rendered with stdlib only (no
prometheus_client dependency).

render_metrics(state) returns a str in the Prometheus 0.0.4 text format,
served verbatim at GET /metrics. Every value is derived from a single
read-only EngineSnapshot -- metrics never mutate the engine and never run
a cycle.
"""

from decimal import Decimal, InvalidOperation
from typing import List

from app.runtime.state import AppState


def _f(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError, InvalidOperation):
        return 0.0


def _metric(lines: List[str], name: str, value, help_text: str, mtype: str = "gauge") -> None:
    lines.append(f"# HELP {name} {help_text}")
    lines.append(f"# TYPE {name} {mtype}")
    lines.append(f"{name} {value}")


def render_metrics(state: AppState) -> str:
    # H3: metrics are scraped frequently and unauthenticated -- they must
    # never trigger venue I/O or contend for the engine lock.
    snapshot = state.snapshot_for_reads()
    p = snapshot.portfolio_snapshot
    lines: List[str] = []

    _metric(lines, "turtle_engine_up", 1 if snapshot.is_started else 0,
            "1 if the engine is started (connected), else 0")
    _metric(lines, "turtle_emergency_stopped", 1 if state.emergency_stopped else 0,
            "1 if emergency stop (signing revoked) has been triggered")
    _metric(lines, "turtle_kill_switch_active", 1 if snapshot.is_kill_switch_active else 0,
            "1 if the execution state machine is in a kill state")
    _metric(lines, "turtle_cycles_run_total", state.cycles_run,
            "Total trading cycles run since process start", mtype="counter")
    _metric(lines, "turtle_open_orders", snapshot.open_order_count if snapshot.open_order_count is not None else 0,
            "Number of open orders at the venue (0 if not started)")
    _metric(lines, "turtle_positions", snapshot.position_count,
            "Number of open positions")
    _metric(lines, "turtle_equity", _f(p.equity), "Portfolio equity")
    _metric(lines, "turtle_available_cash", _f(p.available_cash), "Available cash")
    _metric(lines, "turtle_used_margin", _f(p.used_margin), "Used margin")
    _metric(lines, "turtle_unrealized_pnl", _f(p.unrealized_pnl), "Unrealized PnL")
    _metric(lines, "turtle_realized_pnl_cumulative", _f(p.realized_pnl_cumulative), "Cumulative realized PnL")
    _metric(lines, "turtle_exposure", _f(p.exposure), "Total exposure")
    _metric(lines, "turtle_heat", _f(p.heat), "Portfolio heat")
    _metric(lines, "turtle_leverage", _f(p.leverage), "Portfolio leverage")
    reconciled = 1 if (snapshot.reconciliation is not None and snapshot.reconciliation.matches) else 0
    _metric(lines, "turtle_reconciliation_matches", reconciled,
            "1 if local and venue positions reconcile, else 0")

    return "\n".join(lines) + "\n"
