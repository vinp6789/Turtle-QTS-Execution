"""Runtime: environment/config loading, engine construction, shared state,
and the background cycle worker.

Public API:
    AppSettings                -- env-driven configuration (from_env)
    build_engine_from_settings -- AppSettings -> (Engine, universe, risk_profile)
    AppState                   -- process-wide, thread-safe Engine holder;
                                  run_one_cycle() / capture() / emergency_stop()
    CycleWorker                -- interval-driven caller of run_one_cycle()
"""

from .engine_builder import build_engine_from_settings
from .settings import AppSettings
from .state import AppState
from .worker import CycleWorker

__all__ = ["AppSettings", "build_engine_from_settings", "AppState", "CycleWorker"]
