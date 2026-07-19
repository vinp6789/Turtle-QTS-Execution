"""Monitoring (Milestone 9): read-only observation of a running Engine.

Public API:
    capture_snapshot -- the one operation this layer performs. Reads
                        engine/adapter health, current execution state,
                        kill-switch status, portfolio/position counts,
                        and a fresh reconciliation check; accepts
                        caller-supplied historical context (last
                        completed cycle's construction/execution results,
                        resynced-order count, last error) since this
                        module has no autonomous way to discover those.
    EngineSnapshot   -- the result type.
    MonitoringError  -- this sub-package's error base.

Never mutates engine state. Never calls place_order/amend_order/
cancel_order, RiskManager.evaluate(), Strategy.generate_intents(), or
run_cycle(). No threads, polling, timers, scheduling, or servers of any
kind -- capture_snapshot() is called once per invocation, by whatever
external mechanism (a script's loop, a REST endpoint, a Telegram command)
a future milestone wires up.
"""

from .errors import MonitoringError
from .models import EngineSnapshot
from .snapshot import capture_snapshot

__all__ = ["capture_snapshot", "EngineSnapshot", "MonitoringError"]
