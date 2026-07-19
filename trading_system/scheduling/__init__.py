"""Scheduling: coordinates exactly one complete trading cycle (Milestone 8).

Public API:
    run_cycle   -- executes one deterministic cycle: startup (if needed)
                   -> synchronization -> reconciliation -> market data ->
                   strategies -> sizing+portfolio construction -> execution
                   -> done. Contains no business logic of its own -- every
                   step is a call into an already-existing lower layer.
    CycleResult -- every stage's outcome for one run_cycle() call.
    SchedulingError -- this sub-package's error base.

Deployment-agnostic: run_cycle() has no knowledge of what calls it. The
exact same function is callable from a laptop's __main__ loop, a cron
entry, a Docker container's entrypoint, a FastAPI route handler, or a
Telegram command handler, without any change to this package. Calling it
repeatedly (a caller's own loop, timer, or request handler -- never
this module's) executes many cycles; nothing here loops, sleeps, or
schedules on its own.
"""

from .errors import SchedulingError
from .cycle import run_cycle
from .models import CycleResult

__all__ = ["run_cycle", "CycleResult", "SchedulingError"]
