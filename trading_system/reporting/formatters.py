"""Human-readable text formatters over an EngineSnapshot.

Every function here does string formatting only -- no new computation,
no new comparison, no new decision. Every number/fact displayed was
already computed by monitoring (which in turn only read it from an
already-existing frozen-module method). This module depends on
monitoring; monitoring never depends on this module (no reverse edge).
"""

from .errors import ReportingError
from ..monitoring import EngineSnapshot


def _require_snapshot(snapshot: EngineSnapshot) -> None:
    if not isinstance(snapshot, EngineSnapshot):
        raise ReportingError(f"snapshot must be an EngineSnapshot, got {type(snapshot).__name__}")


def portfolio_summary(snapshot: EngineSnapshot) -> str:
    _require_snapshot(snapshot)
    p = snapshot.portfolio_snapshot
    return (
        f"Portfolio as of {p.updated_at_utc}\n"
        f"  Equity: {p.equity}\n"
        f"  Available cash: {p.available_cash}\n"
        f"  Reserved margin: {p.reserved_margin}\n"
        f"  Used margin: {p.used_margin}\n"
        f"  Exposure: {p.exposure}\n"
        f"  Heat: {p.heat}\n"
        f"  Leverage: {p.leverage}\n"
        f"  Unrealized PnL: {p.unrealized_pnl}\n"
        f"  Realized PnL (cumulative): {p.realized_pnl_cumulative}\n"
        f"  Open positions: {snapshot.position_count}"
    )


def execution_summary(snapshot: EngineSnapshot) -> str:
    _require_snapshot(snapshot)
    executions = snapshot.last_cycle_executions
    if not executions:
        return "No executions in the last completed cycle."
    lines = [f"{len(executions)} execution(s) in the last cycle:"]
    for result in executions:
        order = result.order_snapshot
        lines.append(
            f"  [{result.operation.value}] {order.symbol.value} qty={order.quantity} "
            f"state={order.lifecycle_state.value} (client_order_id={order.client_order_id})"
        )
    return "\n".join(lines)


def cycle_summary(snapshot: EngineSnapshot) -> str:
    _require_snapshot(snapshot)
    if snapshot.last_cycle_completed_at_utc is None:
        return "No cycle has completed yet."
    construction = snapshot.last_cycle_construction
    approved = len(construction.approved) if construction is not None else 0
    rejected = len(construction.rejected) if construction is not None else 0
    skipped = len(construction.skipped) if construction is not None else 0
    executions = len(snapshot.last_cycle_executions) if snapshot.last_cycle_executions else 0
    resynced = snapshot.last_cycle_resynced_order_count or 0
    return (
        f"Last cycle completed at {snapshot.last_cycle_completed_at_utc}\n"
        f"  Resynced orders: {resynced}\n"
        f"  Approved: {approved}, Rejected: {rejected}, Skipped: {skipped}\n"
        f"  Executions: {executions}"
    )


def risk_summary(snapshot: EngineSnapshot) -> str:
    _require_snapshot(snapshot)
    lines = [
        f"Kill switch active: {snapshot.is_kill_switch_active}",
        f"Current engine state: {snapshot.current_state.value}",
    ]
    construction = snapshot.last_cycle_construction
    if construction is not None and construction.rejected:
        lines.append(f"{len(construction.rejected)} rejected trade(s) in the last cycle:")
        for rejected_trade in construction.rejected:
            reasons = ", ".join(code.value for code in rejected_trade.decision.reason_codes)
            lines.append(
                f"  {rejected_trade.intent.symbol.value}: "
                f"{rejected_trade.decision.decision.value} ({reasons})"
            )
    else:
        lines.append("No rejected trades in the last cycle.")
    return "\n".join(lines)


def reconciliation_summary(snapshot: EngineSnapshot) -> str:
    _require_snapshot(snapshot)
    report = snapshot.reconciliation
    if report is None:
        return "Reconciliation unavailable: engine is not started."
    if report.matches:
        return f"Reconciliation OK as of {report.checked_at_utc}: local and venue positions match."
    lines = [f"Reconciliation MISMATCH as of {report.checked_at_utc}:"]
    for discrepancy in report.discrepancies:
        lines.append(f"  {discrepancy}")
    return "\n".join(lines)
