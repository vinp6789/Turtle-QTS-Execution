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

from execution_state_machine import State as EsmState, Trigger as EsmTrigger

from composition_root import Engine
from trading_system.execution import QuantizationRules
from trading_system.monitoring import EngineSnapshot, capture_snapshot
from trading_system.scheduling import CycleResult, run_cycle
from trading_system.strategy import Strategy

from .accounting import AccountingSync
from .engine_builder import build_engine_from_settings
from .settings import AppSettings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ESM states in which the engine must never attempt another cycle. These
# are exactly the states risk_manager treats as BLOCKING, and both survive
# restart via the ESM's own durable replay.
_STOPPED_ESM_STATES = frozenset({EsmState.EMERGENCY_KILL, EsmState.STOPPED})

# Kill-tier states for the cheap snapshot's is_kill_switch_active --
# independently declared (config/schema.py's own established pattern),
# consistent with trading_system.monitoring's derivation.
_KILL_ESM_STATES = frozenset({EsmState.SOFT_KILL, EsmState.HARD_KILL, EsmState.EMERGENCY_KILL})


class EmergencyStopActive(RuntimeError):
    """Raised by run_one_cycle when an emergency stop is in effect (in
    this process, or durably recorded by a previous one): no cycle may
    run, nothing is persisted, no venue I/O is performed."""


@dataclass
class AppState:
    settings: AppSettings
    engine: Engine
    universe: Tuple[Symbol, ...]
    risk_profile: RiskProfileParams
    strategies: Tuple[Strategy, ...] = ()
    accounting: Optional[AccountingSync] = None
    # C2: venue quantization rules -- populated for live engines (fetched
    # fail-fast at build time), None for paper. Immutable mapping; replace
    # wholesale to refresh (atomic rebind).
    quantization_rules: Optional[QuantizationRules] = None
    engine_lock: threading.RLock = field(default_factory=threading.RLock)

    # -- latest-cycle bookkeeping (read by API/metrics/telegram) --
    last_cycle: Optional[CycleResult] = None
    last_cycle_completed_at_utc: Optional[str] = None
    last_error: Optional[str] = None
    cycles_run: int = 0
    started_at_utc: str = field(default_factory=_now)
    emergency_stopped: bool = False

    @classmethod
    def create(
        cls,
        settings: AppSettings,
        env=None,
        strategies: Tuple[Strategy, ...] = (),
        quantization_rules: Optional[QuantizationRules] = None,
    ) -> "AppState":
        engine, universe, risk_profile, built_rules = build_engine_from_settings(settings, env)
        # C1 fix: one-time equity seed. The FIXED request_id makes this
        # exactly-once per event store (durable idempotency): every later
        # boot -- and any change to the env var -- is a no-op.
        if settings.initial_deposit > 0:
            engine.portfolio_manager.deposit(
                settings.initial_deposit, request_id="app_accounting:initial-deposit:v1",
            )
        state = cls(
            settings=settings, engine=engine, universe=universe,
            risk_profile=risk_profile, strategies=tuple(strategies),
            accounting=AccountingSync(engine, target_leverage=settings.target_leverage),
            # C2: an explicit caller-supplied mapping (tests) wins; else the
            # builder's (live: fetched fail-fast; paper: None).
            quantization_rules=quantization_rules if quantization_rules is not None else built_rules,
        )
        # M1: a prior process's emergency stop is durable (the ESM replays
        # into EMERGENCY_KILL/STOPPED) -- restore the flag so /health,
        # metrics, and the cycle gate are truthful from the first moment
        # of a restarted process, not only after the first blocked cycle.
        if engine.execution_state_machine.current_state in _STOPPED_ESM_STATES:
            state.emergency_stopped = True
        return state

    # -- cycle execution --

    def run_one_cycle(self) -> CycleResult:
        """Runs exactly one trading cycle under the engine lock and records
        the outcome. Never swallows a cycle failure silently -- it records
        it on last_error AND re-raises, so a caller (worker/endpoint) can
        decide how to react.

        C1 fix -- accounting synchronization brackets the cycle:
          BEFORE run_cycle: book every fill that occurred since the last
            cycle and refresh marks, so this cycle's risk evaluation sees
            the true portfolio (open positions, margin, heat, exposure),
            not an empty one.
          AFTER run_cycle: durably record the executed orders' stop/entry
            levels, then book any immediate fills of this cycle's own
            orders. Every step is durably idempotent (see accounting.py),
            so re-running any part after a crash is a no-op."""
        with self.engine_lock:
            # M1 gate: never start a cycle under an emergency stop -- in
            # this process (flag) OR recorded durably by a previous one
            # (replayed ESM kill state). Nothing is persisted, no venue
            # I/O happens; the refusal itself is the fail-safe.
            if self.emergency_stopped or self.engine.execution_state_machine.current_state in _STOPPED_ESM_STATES:
                raise EmergencyStopActive(
                    "emergency stop is active (signing revoked, execution state "
                    f"{self.engine.execution_state_machine.current_state.value}): refusing to run a "
                    "trading cycle. Resuming requires a fresh deployment (new event store + signing config)."
                )
            try:
                accounting_notes: list = []
                if self.accounting is not None and self.engine.is_started:
                    accounting_notes += self.accounting.sync()
                    self.accounting.update_marks()
                # Levels are recorded PER EXECUTION via the on_execution
                # hook -- immediately after each order's execute_place
                # returns, before the next order is attempted -- so a crash
                # mid-loop (or a later order's failure) can no longer lose
                # an already-placed order's stop/entry metadata. The
                # post-cycle batch call below remains as a redundant,
                # write-free safety net (record_execution_levels is
                # idempotent per cid: already-recorded orders are skipped
                # in memory, appending nothing).
                on_execution = (
                    (lambda execution: self.accounting.record_execution_levels((execution,)))
                    if self.accounting is not None else None
                )
                result = run_cycle(
                    self.engine,
                    self.strategies,
                    universe=self.universe,
                    risk_profile=self.risk_profile,
                    correlation_info=CorrelationInfo(entries=(), as_of_utc=_now()),
                    maintenance_margin_rate=self.settings.maintenance_margin_rate,
                    target_leverage=self.settings.target_leverage,
                    on_execution=on_execution,
                    quantization_rules=self.quantization_rules,
                )
                if self.accounting is not None:
                    self.accounting.record_execution_levels(result.executions)
                    accounting_notes += self.accounting.sync()
                if accounting_notes:
                    self.last_error = "accounting: " + " | ".join(accounting_notes)
            except Exception as exc:  # noqa: BLE001 -- recorded for observability, then re-raised
                self.last_error = f"{type(exc).__name__}: {exc}"
                raise
            self.last_cycle = result
            self.last_cycle_completed_at_utc = _now()
            self.cycles_run += 1
            # H3: refresh the read-side snapshot HERE -- the single
            # sanctioned venue-touching context (we already hold the lock
            # and are mid-cycle-budget). Read endpoints then never need
            # venue I/O of their own. Best-effort: a capture failure must
            # not fail an otherwise-successful cycle.
            try:
                self.latest_snapshot = self.capture()
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"snapshot refresh failed: {type(exc).__name__}: {exc}"
            return result

    # -- observation (read-only) --

    # H3: latest full snapshot, produced ONLY by the cycle/stop paths (the
    # single producer that is already allowed to touch the venue). Read
    # endpoints consume this via snapshot_for_reads() -- never capture().
    # A plain attribute: replacing it is an atomic reference rebind, so
    # lock-free readers can never observe a half-built snapshot (the
    # EngineSnapshot itself is a frozen dataclass).
    latest_snapshot: Optional[EngineSnapshot] = None

    def snapshot_for_reads(self) -> EngineSnapshot:
        """H3: the ONLY observation path HTTP read endpoints may use.
        Takes NO engine lock and performs NO venue I/O -- a slow venue or
        a long-running cycle can never block, or be blocked by, a read.
        Serves the worker-produced snapshot when one exists; otherwise a
        degraded-but-honest snapshot from lock-free, in-memory sources
        (open_order_count/reconciliation None -- monitoring's own 'not
        fetched' shape). Freshness is cycle-cadence by design; the
        snapshot carries its own captured_at_utc."""
        snapshot = self.latest_snapshot
        if snapshot is not None:
            return snapshot
        return self._cheap_snapshot()

    def _cheap_snapshot(self) -> EngineSnapshot:
        """Venue-free, engine-lock-free snapshot. Safe concurrently: the
        frozen managers guard their own state (PortfolioManager's single
        lock; adapter.health() reads only connection flags -- no network
        on either adapter)."""
        engine = self.engine
        current_state = engine.execution_state_machine.current_state
        portfolio_snapshot = engine.portfolio_manager.get_snapshot()
        return EngineSnapshot(
            captured_at_utc=_now(),
            health=engine.adapter.health(),
            current_state=current_state,
            is_kill_switch_active=current_state in _KILL_ESM_STATES,
            is_started=engine.is_started,
            open_order_count=None,        # honest: not fetched without venue I/O
            position_count=len(portfolio_snapshot.open_position_ids),
            portfolio_snapshot=portfolio_snapshot,
            reconciliation=None,          # honest: not fetched without venue I/O
            last_cycle_completed_at_utc=self.last_cycle_completed_at_utc,
            last_cycle_construction=self.last_cycle.construction if self.last_cycle else None,
            last_cycle_executions=self.last_cycle.executions if self.last_cycle else None,
            last_cycle_resynced_order_count=(
                len(self.last_cycle.resynced_orders) if self.last_cycle else None
            ),
            last_error=self.last_error,
        )

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

    def emergency_stop(self) -> tuple:
        """Emergency Kill, in fail-safe order (H2 + M1 fixes):

          1. CANCEL resting venue orders FIRST (H2) -- while signing is
             still valid. Revocation is one-way (frozen design), so any
             order not cancelled before it becomes permanently
             unmanageable by this engine: it would rest at the venue and
             could fill hours later with no way to cancel it. The cancel
             is BEST-EFFORT and bounded: it must never delay or prevent
             revocation (any failure is recorded and revocation proceeds),
             it is attempted only on the FIRST stop (signing is revoked
             afterwards, so a retry could only fail noisily), and only
             when the engine is started (a never-connected engine has
             transmitted nothing and cannot reach the venue anyway). Uses
             the frozen OrderManager.cancel_all(), which durably records
             the intent BEFORE transmission and reports only
             venue-AFFIRMED cancellations -- an order it does not return
             (e.g. filled in the race) is never falsely marked cancelled.
          2. REVOKE all signing, unconditionally -- the capital lever.
          3. Propagate DURABLY into the ESM (M1): EMERGENCY_KILL_TRIGGERED
             is legal from every live state, replayed on restart, one-way;
             RiskManager then BLOCKS everything and monitoring shows the
             kill switch active. An append failure never undoes the
             revocation (surfaced on last_error).

        Returns the venue-confirmed cancelled OrderSnapshots (empty on a
        repeat stop, an unstarted engine, or a cancel failure). Idempotent."""
        with self.engine_lock:
            cancelled: tuple = ()
            already_stopped = (
                self.emergency_stopped
                or self.engine.execution_state_machine.current_state in _STOPPED_ESM_STATES
            )
            if not already_stopped and self.engine.is_started:
                try:
                    cancelled = self.engine.order_manager.cancel_all()
                except Exception as exc:  # noqa: BLE001 -- NOTHING may delay revocation
                    self.last_error = (
                        f"emergency stop: cancel_all before revocation failed "
                        f"({type(exc).__name__}: {exc}) -- resting venue orders may remain "
                        "live and are now unmanageable by this engine; cancel them at the venue"
                    )
            self.engine.signing_boundary.revoke_all()
            signer = self.engine.wallet_signer
            if signer is not None and hasattr(signer, "revoke"):
                signer.revoke()
            esm = self.engine.execution_state_machine
            if esm.current_state not in _STOPPED_ESM_STATES:
                try:
                    esm.transition(
                        EsmTrigger.EMERGENCY_KILL_TRIGGERED,
                        request_id=f"app:emergency-stop:{_now()}",
                        context={"source": "app_runtime", "reason": "operator_emergency_stop"},
                    )
                except Exception as exc:  # noqa: BLE001 -- revocation already holds; surface, never mask
                    self.last_error = (
                        f"emergency stop: signing revoked, but recording EMERGENCY_KILL "
                        f"failed: {type(exc).__name__}: {exc}"
                    )
            self.emergency_stopped = True
            # H3: cycles are refused from now on, so the cached snapshot
            # would otherwise stay frozen pre-stop forever. Refresh it
            # venue-free so monitoring immediately shows the kill.
            self.latest_snapshot = self._cheap_snapshot()
            return cancelled

    def shutdown(self) -> None:
        with self.engine_lock:
            try:
                self.engine.stop()
            except Exception:  # noqa: BLE001 -- shutdown must not raise
                pass
