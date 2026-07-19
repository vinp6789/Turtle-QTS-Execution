"""AppState: the process-wide, thread-safe holder of the single Engine and
the most recent cycle outcome.

Concurrency model: a single reentrant lock (`engine_lock`) serializes ALL
engine access -- the background worker's cycle runs and the API's snapshot
reads both acquire it, so an HTTP request can never observe the engine
mid-cycle. The frozen modules have their own internal locks too; this
outer lock adds cross-module consistency for a whole cycle/observation,
which no single frozen module can provide on its own.

AppState owns NO trading logic. run_one_cycle delegates entirely to
trading_system.scheduling.run_cycle; capture delegates entirely to
trading_system.monitoring.capture_snapshot. It only stores the results so
the API/Telegram/metrics layers can read the latest without re-running
anything.
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Tuple

from config import RiskProfileParams
from exchange_adapter import Symbol
from risk_manager import CorrelationInfo

from composition_root import Engine
from trading_system.monitoring import EngineSnapshot, capture_snapshot
from trading_system.scheduling import CycleResult, run_cycle
from trading_system.strategy import Strategy

from .engine_builder import build_engine_from_settings
from .settings import AppSettings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AppState:
    settings: AppSettings
    engine: Engine
    universe: Tuple[Symbol, ...]
    risk_profile: RiskProfileParams
    strategies: Tuple[Strategy, ...] = ()
    engine_lock: threading.RLock = field(default_factory=threading.RLock)

    # -- latest-cycle bookkeeping (read by API/metrics/telegram) --
    last_cycle: Optional[CycleResult] = None
    last_cycle_completed_at_utc: Optional[str] = None
    last_error: Optional[str] = None
    cycles_run: int = 0
    started_at_utc: str = field(default_factory=_now)
    emergency_stopped: bool = False

    @classmethod
    def create(cls, settings: AppSettings, env=None, strategies: Tuple[Strategy, ...] = ()) -> "AppState":
        engine, universe, risk_profile = build_engine_from_settings(settings, env)
        return cls(
            settings=settings, engine=engine, universe=universe,
            risk_profile=risk_profile, strategies=tuple(strategies),
        )

    # -- cycle execution --

    def run_one_cycle(self) -> CycleResult:
        """Runs exactly one trading cycle under the engine lock and records
        the outcome. Never swallows a cycle failure silently -- it records
        it on last_error AND re-raises, so a caller (worker/endpoint) can
        decide how to react."""
        with self.engine_lock:
            try:
                result = run_cycle(
                    self.engine,
                    self.strategies,
                    universe=self.universe,
                    risk_profile=self.risk_profile,
                    correlation_info=CorrelationInfo(entries=(), as_of_utc=_now()),
                    maintenance_margin_rate=self.settings.maintenance_margin_rate,
                    target_leverage=self.settings.target_leverage,
                )
            except Exception as exc:  # noqa: BLE001 -- recorded for observability, then re-raised
                self.last_error = f"{type(exc).__name__}: {exc}"
                raise
            self.last_cycle = result
            self.last_cycle_completed_at_utc = _now()
            self.cycles_run += 1
            return result

    # -- observation (read-only) --

    def capture(self) -> EngineSnapshot:
        with self.engine_lock:
            construction = self.last_cycle.construction if self.last_cycle is not None else None
            executions = self.last_cycle.executions if self.last_cycle is not None else None
            resynced = len(self.last_cycle.resynced_orders) if self.last_cycle is not None else None
            return capture_snapshot(
                self.engine,
                last_cycle_completed_at_utc=self.last_cycle_completed_at_utc,
                last_cycle_construction=construction,
                last_cycle_executions=executions,
                last_cycle_resynced_order_count=resynced,
                last_error=self.last_error,
            )

    # -- control --

    def emergency_stop(self) -> None:
        """Emergency Kill: revoke every signing capability so no further
        mutation can ever be authorized on this process's engine. Uses the
        frozen SigningBoundary.revoke_all() (and the wallet signer's own
        revoke) -- both are one-way by design. Idempotent."""
        with self.engine_lock:
            self.engine.signing_boundary.revoke_all()
            signer = self.engine.wallet_signer
            if signer is not None and hasattr(signer, "revoke"):
                signer.revoke()
            self.emergency_stopped = True

    def shutdown(self) -> None:
        with self.engine_lock:
            try:
                self.engine.stop()
            except Exception:  # noqa: BLE001 -- shutdown must not raise
                pass
