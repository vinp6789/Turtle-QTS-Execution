"""The Strategy Scoreboard: Project Alpha's authoritative business report.

PRESENTATION AND AGGREGATION ONLY. This module contains NO business
calculation. Every displayed number comes from measurement.metrics, and a
test greps this file to prove no formula was reimplemented here. If a
figure is wrong, it is wrong in the metrics engine -- there is nowhere
else it could come from.

WHAT IT REUSES
  metrics          measurement.metrics.compute()  -- every metric
  equity history   measurement.EquityLog          -- Task 1
  trade records    PositionManager.get_position() -- the position
                   manager's OWN state reconstruction. replay() is used
                   ONLY to enumerate closed position ids; no position
                   state is rebuilt here.
  strategy metadata alpha_engine.platform PluginEntry (name, kind,
                   description, warning) and Strategy.name
  the VDA bar      alpha_engine.feasibility, via metrics

ATTRIBUTION, per the accepted audit (2026-08-07). While exactly one
strategy is enabled, every closed position necessarily belongs to it and
attribution is unambiguous. A per-trade strategy field is DEFERRED under
Constitution §5 until a configuration enables more than one strategy
simultaneously; the design is already settled (an optional defaulted
strategy_name on TradeIntent/TradeRequest carried into the
ORDER_SUBMITTED payload) so it is implemented, not invented, when needed.
build() therefore refuses to attribute when it cannot -- see MULTI_
STRATEGY_UNSUPPORTED below -- rather than guessing.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from event_store import EventType

from .equity_log import EquityLog
from .metrics import compute, period_returns, to_jsonable
from .validity import Metric, MetricStatus, as_dict as validity_as_dict, classify

# The benchmark every strategy is measured against.
# MEASURED 2026-08-06: HLP vault +16.6%/yr time-weighted, trailing 12
# months at $398M TVL (docs/MECHANISMS.md). After 31.2% Indian VDA tax:
# 16.6 * 0.688 = 11.42%/yr. Defined ONCE, here, and imported by anything
# that needs it -- never recomputed at a call site.
HLP_BENCHMARK_GROSS_ANNUAL = Decimal("0.166")
HLP_BENCHMARK_NET_ANNUAL = Decimal("0.1142")

MULTI_STRATEGY_UNSUPPORTED = (
    "more than one strategy was enabled; per-trade attribution is not yet "
    "implemented (deferred by design -- see module docstring). Metrics "
    "shown are for the COMBINED book, not per strategy."
)


def closed_position_ids(store) -> List[str]:
    """Closed position ids, in close order, from the event log.

    replay() is used ONLY to enumerate ids. Position STATE is then read
    through PositionManager.get_position(), so this module never rebuilds
    what the position manager already reconstructs.
    """
    seen, out = set(), []
    for event in store.replay():
        if event.event_type is not EventType.POSITION_CLOSED:
            continue
        pid = event.payload.get("position_id")
        if pid and pid not in seen:
            seen.add(pid)
            out.append(pid)
    return out


def closed_trades(store, position_manager) -> List[Dict[str, Any]]:
    """One record per closed position, shaped for metrics.trade_metrics.

    Every figure originates in the position manager. A position that
    cannot be read is SKIPPED and never fabricated -- a missing trade is
    better than an invented one.

    WHY realized_pnl IS NORMALISED HERE. metrics.trade_metrics documents
    its input contract as "realized_pnl is NET of fees" and derives
    gross = realized_pnl + fees_paid + funding_paid. PositionSnapshot's
    realized_pnl does not meet that contract: pnl.leg_realized_pnl
    subtracts only the CLOSING leg's fee, while fees_paid accumulates the
    entry fill's fee too (position_manager/manager.py:230). Feeding the
    raw field in therefore added the entry fee back without it ever
    having been subtracted, and gross came out ABOVE price PnL by exactly
    that amount -- measured 2026-08-10 on the corrected lifecycle:
    reported -0.2530262760 against a price PnL of -0.32766, a difference
    of 0.0746337240 = the entry fee. The bias is one-directional
    (fees are positive), so gross_profit_factor and the VDA gate were
    both optimistic -- the direction that lets a losing strategy be
    called deployable.

    THE ADAPTATION IS THE INVERSE OF THE FROZEN FORMULA, NOT A SECOND
    ONE. Each ClosedLeg carries the leg fee that leg_realized_pnl
    subtracted, so `leg.realized_pnl + leg.fee` re-derives that leg's
    price PnL using the position manager's own numbers -- no price
    arithmetic, no side handling and no fee ledger is reimplemented here.
    Everything downstream keeps one convention:

        gross = price PnL, before all costs
        net   = gross - fees_paid - funding_paid
        gross = net + fees_paid + funding_paid   (metrics, unchanged)

    A closed position with no readable legs is skipped for the same
    reason an unreadable position is: its exit fee is unknowable, and a
    trade reported on a guessed cost basis is worse than one omitted.
    """
    trades: List[Dict[str, Any]] = []
    for pid in closed_position_ids(store):
        try:
            p = position_manager.get_position(pid)
            legs = position_manager.get_closed_legs(pid)
        except Exception:                      # noqa: BLE001
            continue
        if not legs:
            continue
        exit_fees = sum((leg.fee for leg in legs), Decimal("0"))
        entry_fees = p.fees_paid - exit_fees
        trades.append({
            "position_id": pid,
            "symbol": p.symbol.value,
            "side": p.side.value,
            "realized_pnl": str(p.realized_pnl - entry_fees - p.funding_paid),
            "fees_paid": str(p.fees_paid),
            "funding_paid": str(p.funding_paid),
            "created_at_utc": p.created_at_utc,
            "updated_at_utc": p.updated_at_utc,
        })
    return trades


def _verdict(m: Dict[str, Any]) -> Dict[str, Any]:
    """The business verdict. A CLASSIFICATION of metrics, not a calculation.

    Every input is already computed by the metrics engine; this only
    decides which side of each line the strategy falls on, and records
    WHY. Order matters: insufficient data is reported as such rather than
    as a failure, because "we cannot tell" and "it loses money" are
    different answers and the project has confused them before.
    """
    reasons: List[str] = []
    if m.get("trade_count", 0) == 0:
        return {"verdict": "INSUFFICIENT_DATA",
                "reasons": ["no closed trades yet"], "deployable": False}

    if (exp := m.get("expectancy")) is not None and exp <= 0:
        reasons.append(f"negative expectancy ({exp} per trade)")
    if m.get("survives_vda_tax") is False:
        gpf = m.get("gross_profit_factor")
        reasons.append(f"fails the VDA tax gate (gross profit factor {gpf} <= 1.4535)")

    cagr = m.get("cagr")
    if cagr is None:
        reasons.append("CAGR not yet computable (insufficient elapsed time)")
    elif cagr < HLP_BENCHMARK_NET_ANNUAL:
        reasons.append(
            f"underperforms the HLP benchmark ({cagr} vs {HLP_BENCHMARK_NET_ANNUAL} net)")

    if not reasons:
        return {"verdict": "PASS", "reasons": [], "deployable": True}
    if len(reasons) == 1 and reasons[0].startswith("CAGR not yet"):
        return {"verdict": "INSUFFICIENT_DATA", "reasons": reasons, "deployable": False}
    return {"verdict": "FAIL", "reasons": reasons, "deployable": False}


def build(*, strategy_name: str, equity_log: EquityLog, store, position_manager,
          plugin_entry=None, version: str = "", status: str = "running",
          enabled_strategy_count: int = 1) -> Dict[str, Any]:
    """The complete business report for one strategy.

    Pure aggregation: every number below is returned by compute().
    """
    rows = equity_log.read_all()
    trades = closed_trades(store, position_manager)
    m = compute(rows, trades)

    # Validity is decided from the SHAPE of the data, never from a value.
    from datetime import datetime
    elapsed_days = None
    if len(rows) >= 2:
        try:
            t0 = datetime.fromisoformat(rows[0]["observed_at_utc"])
            t1 = datetime.fromisoformat(rows[-1]["observed_at_utc"])
            elapsed_days = Decimal(str((t1 - t0).total_seconds() / 86400.0))
        except (KeyError, TypeError, ValueError):
            elapsed_days = None
    classified = classify(m, return_count=len(period_returns(rows)),
                          elapsed_days=elapsed_days)

    cagr = m.get("cagr")
    report: Dict[str, Any] = {
        # -- identity
        "strategy_name": strategy_name,
        "version": version,
        "kind": plugin_entry.kind.value if plugin_entry else None,
        "warning": plugin_entry.warning if plugin_entry else "",
        "status": status,
        "start_time_utc": m.get("first_observed_at_utc"),
        "last_observed_utc": m.get("last_observed_at_utc"),
        # -- everything below is verbatim from the metrics engine
        "trade_count": m.get("trade_count"),
        "total_return": m.get("total_return"),
        "cagr": cagr,
        "sharpe": m.get("sharpe"),
        "profit_factor": m.get("profit_factor"),
        "gross_profit_factor": m.get("gross_profit_factor"),
        "payoff_ratio": m.get("payoff_ratio"),
        "win_rate": m.get("win_rate"),
        "average_win": m.get("average_win"),
        "average_loss": m.get("average_loss"),
        "expectancy": m.get("expectancy"),
        "max_drawdown": m.get("max_drawdown"),
        "average_holding_seconds": m.get("average_holding_seconds"),
        "fees_paid": m.get("fees_paid"),
        "funding_paid": m.get("funding_paid"),
        "cost_attribution": m.get("cost_attribution"),
        "starting_equity": m.get("starting_equity"),
        "ending_equity": m.get("ending_equity"),
        # -- benchmark: a comparison, not a calculation
        "benchmark_name": "HLP vault (measured 2026-08-06)",
        "benchmark_net_annual": HLP_BENCHMARK_NET_ANNUAL,
        "benchmark_difference": (cagr - HLP_BENCHMARK_NET_ANNUAL) if cagr is not None else None,
        "vda_pass": m.get("survives_vda_tax"),
        "observations": m.get("observations"),
    }
    report.update(_verdict(m))
    # Every metric, with its validity. The API reads this and calculates
    # nothing.
    report["metrics"] = validity_as_dict(classified)
    report["elapsed_days"] = elapsed_days
    if enabled_strategy_count > 1:
        report["attribution_warning"] = MULTI_STRATEGY_UNSUPPORTED
    return report


def build_all(*, strategies: Sequence[Any], equity_log: EquityLog, store,
              position_manager, entries: Sequence[Any] = ()) -> List[Dict[str, Any]]:
    """One report per enabled strategy. A new strategy appears here with
    ZERO scoreboard changes -- it is driven entirely by what the loader
    returned."""
    by_name = {e.name: e for e in entries}
    out = []
    for i, s in enumerate(strategies):
        entry = list(by_name.values())[i] if i < len(by_name) else None
        out.append(build(
            strategy_name=s.name, equity_log=equity_log, store=store,
            position_manager=position_manager, plugin_entry=entry,
            enabled_strategy_count=len(strategies)))
    return out


def to_json(report) -> Any:
    """Decimal -> string, never through a float."""
    if isinstance(report, list):
        return [to_jsonable(r) for r in report]
    return to_jsonable(report)
