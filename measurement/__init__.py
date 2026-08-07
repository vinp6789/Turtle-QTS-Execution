"""Business measurement layer (Track B, Product).

Answers "did this make money?", never "is this hypothesis supported?" --
that second question belongs to alpha_engine and its five-stage gate.

A top-level package, not part of alpha_engine, because it reads frozen
Execution Engine state (PortfolioSnapshot). Constitution Section 4 forbids
alpha_engine from that coupling, and tests/test_alpha_engine_scaffold.py
enforces it.
"""

from .equity_log import SCHEMA_VERSION, EquityLog, idempotency_key, row_from_snapshot
from .scoreboard import (
    HLP_BENCHMARK_NET_ANNUAL, build, build_all, closed_trades, to_json,
)
from .metrics import (
    cagr, compute, cost_attribution, max_drawdown, period_returns,
    rolling_returns, sharpe, to_jsonable, total_return, trade_metrics,
)

__all__ = [
    "EquityLog", "row_from_snapshot", "idempotency_key", "SCHEMA_VERSION",
    "compute", "to_jsonable", "total_return", "cagr", "sharpe",
    "max_drawdown", "period_returns", "rolling_returns", "trade_metrics",
    "cost_attribution",
    "build", "build_all", "closed_trades", "to_json",
    "HLP_BENCHMARK_NET_ANNUAL",
]
