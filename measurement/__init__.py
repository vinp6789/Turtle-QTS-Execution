"""Business measurement layer (Track B, Product).

Answers "did this make money?", never "is this hypothesis supported?" --
that second question belongs to alpha_engine and its five-stage gate.

A top-level package, not part of alpha_engine, because it reads frozen
Execution Engine state (PortfolioSnapshot). Constitution Section 4 forbids
alpha_engine from that coupling, and tests/test_alpha_engine_scaffold.py
enforces it.
"""

from .equity_log import SCHEMA_VERSION, EquityLog, idempotency_key, row_from_snapshot

__all__ = ["EquityLog", "row_from_snapshot", "idempotency_key", "SCHEMA_VERSION"]
