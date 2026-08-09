"""Supervised ENGINE_TEST lifecycle runner for Hyperliquid TESTNET.

WHAT THIS IS. Infrastructure validation, and nothing else. It drives ONE
complete pass of the canonical execution path against a real venue:

    entry -> real fill -> position -> natural ageing >150s
    -> reduce-only close -> real close fill -> position 0
    -> reconciliation -> attribution -> clean shutdown

Its specific purpose is to prove that commit 788729e (the stale-position
fix) works against a live venue: that a position which has aged past
max_stale_data_seconds can still be closed automatically through
Strategy -> Portfolio -> Sizing -> Risk -> Execution -> OrderManager ->
HyperliquidAdapter -> /exchange.

WHAT THIS IS NOT. Not alpha, not performance, not profitability, not
research or campaign evidence. strategy_kind is ENGINE_TEST throughout.

WHY IT EXISTS AT ALL -- THE LESSON THAT SHAPED IT.
Lifecycle #1 submitted a real order, filled it, and then DIED on a print
statement that referenced OrderSnapshot.status, an attribute that does not
exist. A real position was left open at the venue with nothing supervising
it, and had to be closed by hand. The entire design below follows from
that single failure:

  1. CRITICAL PATH vs REPORTING. Every diagnostic goes through _report(),
     which cannot raise. Reporting is structurally incapable of ending the
     lifecycle. The critical path touches only verified attributes.
  2. GUARANTEED CLEANUP. The lifecycle body is wrapped in try/finally.
     Shutdown runs on every exit path and is itself protected so cleanup
     can never mask the original error.
  3. PREFLIGHT FAILS LOUDLY, BEFORE ANY ORDER. Every interface the runner
     will touch is verified against the real classes first. A missing
     attribute stops the run while it is still harmless.
  4. NO hasattr() API MASKING. In lifecycle #1 a hasattr() guard around
     PositionManager.list_open_positions() (which does not exist) silently
     returned None and the script carried on as though it had checked.
     Preflight asserts existence; the body then uses the API directly.

FORBIDDEN ATTRIBUTES, verified absent 2026-08-09 and never referenced:
    OrderSnapshot.status              -> use .lifecycle_state
    Engine.connect()                  -> use .start()
    PositionManager.list_open_positions() -> use PortfolioSnapshot
                                         .open_position_ids + get_position()
    PortfolioSnapshot.total_equity    -> use .equity

SAFETY MODEL, STATED HONESTLY. Small notional + supervised execution +
manual UI close fallback. There is NO venue-side stop: OrderType is
{MARKET, LIMIT}, hyperliquid_adapter declares supports_trigger_orders=False,
no stop-breach monitor exists and auto_flatten is disabled. If this process
dies between entry and close, the position stays open until closed by hand.
That is why the runner never exits early after a fill, and why the operator
must remain present.

THIS MODULE SUBMITS NOTHING ON IMPORT. run() must be called explicitly, and
main() additionally requires LIFECYCLE_CONFIRM=I-AUTHORIZE-ONE-TESTNET-LIFECYCLE
in the environment. Importing it -- as the tests do -- is inert.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, List, Optional

_log = logging.getLogger("turtle.lifecycle2")

# The natural-ageing target. max_stale_data_seconds is 150; this leaves a
# comfortable margin without inviting a long unsupervised window.
AGE_SECONDS = 195

# How long to keep polling the venue for a fill before giving up. A fill
# that has not appeared in this window is a STOP, never a retry.
FILL_POLL_ATTEMPTS = 12
FILL_POLL_INTERVAL = 5

# READ retries only. Venue reads are idempotent, so a transient transport
# error is worth retrying; an ORDER SUBMISSION never is. That asymmetry is
# the whole point -- see _venue_read.
READ_RETRY_ATTEMPTS = 3
READ_RETRY_DELAY = 2

CONFIRM_ENV = "LIFECYCLE_CONFIRM"
CONFIRM_VALUE = "I-AUTHORIZE-ONE-TESTNET-LIFECYCLE"


class LifecycleAbort(RuntimeError):
    """Raised to stop the lifecycle deliberately. Cleanup still runs."""


class UnknownVenueState(LifecycleAbort):
    """The venue could not be read after bounded retries.

    Deliberately its own type so no caller can collapse it into "flat",
    "filled" or "closed". Unknown stays unknown, and unknown means a human
    verifies the venue before anything else happens.
    """


class PreflightFailure(RuntimeError):
    """Raised before any order can be submitted. Nothing has happened yet."""


# --------------------------------------------------------------- reporting
def _report(label: str, fn: Callable[[], Any]) -> Any:
    """Run a diagnostic. NEVER raises -- this is the whole point.

    Lifecycle #1 died inside a print. Every optional read, format and log in
    this runner goes through here, so no reporting defect can terminate a
    lifecycle that has an open position.
    """
    try:
        return fn()
    except Exception as exc:                                   # noqa: BLE001
        _log.error("REPORTING FAILURE in %s (lifecycle continues): %s: %s",
                   label, type(exc).__name__, exc)
        return None


# --------------------------------------------------------------- preflight
# (owner, attribute, is_callable). Verified against the real classes on
# 2026-08-09. Preflight fails loudly if any of these ever stops existing.
_REQUIRED = {
    "CycleResult": ("trading_system.scheduling", "CycleResult",
                    ["intents", "construction", "executions", "reconciliation",
                     "evaluated_at_utc", "suppressed_by_open_orders"]),
    "ConstructionResult": ("trading_system.portfolio_construction.models", "ConstructionResult",
                           ["approved", "rejected", "skipped"]),
    "RejectedTrade": ("trading_system.portfolio_construction.models", "RejectedTrade",
                      ["intent", "trade_request", "decision"]),
    "SkippedIntent": ("trading_system.portfolio_construction.models", "SkippedIntent",
                      ["intent", "reason"]),
    "ExecutionResult": ("trading_system.execution.models", "ExecutionResult",
                        ["operation", "order_snapshot", "trade_request", "decision"]),
    "OrderSnapshot": ("order_manager", "OrderSnapshot",
                      ["client_order_id", "lifecycle_state", "exchange_order_id",
                       "quantity", "filled_quantity", "limit_price", "reduce_only",
                       "reject_reason", "symbol", "side"]),
    "PositionSnapshot": ("position_manager", "PositionSnapshot",
                         ["position_id", "lifecycle_state", "symbol", "side",
                          "remaining_quantity", "avg_entry_price", "realized_pnl",
                          "fees_paid", "updated_at_utc"]),
    "PortfolioSnapshot": ("portfolio_manager", "PortfolioSnapshot",
                          ["open_position_ids", "equity", "updated_at_utc"]),
    "ReconciliationReport": ("exchange_adapter", "ReconciliationReport",
                             ["matches", "discrepancies", "local_positions",
                              "exchange_positions"]),
    "RiskDecision": ("risk_manager", "RiskDecision",
                     ["decision", "reason_codes", "violated_limits"]),
}

# Attributes that DO NOT EXIST and must never be referenced. Preflight
# asserts their continued absence, so if one is ever added the runner is
# reviewed rather than silently changing meaning.
_FORBIDDEN = [
    ("order_manager", "OrderSnapshot", "status"),
    ("composition_root", "Engine", "connect"),
    ("position_manager", "PositionManager", "list_open_positions"),
    ("portfolio_manager", "PortfolioSnapshot", "total_equity"),
]


def _dataclass_field_names(cls) -> List[str]:
    import dataclasses
    try:
        return [f.name for f in dataclasses.fields(cls)]
    except TypeError:
        return [a for a in dir(cls) if not a.startswith("_")]


def preflight() -> List[str]:
    """Verify every interface the runner uses. Returns a list of failures.

    Runs BEFORE the platform is built and before any order can exist, so a
    missing interface costs nothing. Uses no hasattr() fallbacks: an absent
    attribute is a failure, never a silently skipped branch.
    """
    import importlib
    failures: List[str] = []

    for label, (module_name, cls_name, attrs) in _REQUIRED.items():
        try:
            cls = getattr(importlib.import_module(module_name), cls_name)
        except Exception as exc:                               # noqa: BLE001
            failures.append(f"{label}: cannot import {module_name}.{cls_name}: {exc}")
            continue
        names = set(_dataclass_field_names(cls)) | set(dir(cls))
        for attr in attrs:
            if attr not in names:
                failures.append(f"{label}.{attr} MISSING on {module_name}.{cls_name}")

    for module_name, cls_name, attr in _FORBIDDEN:
        try:
            cls = getattr(importlib.import_module(module_name), cls_name)
        except Exception:                                      # noqa: BLE001
            continue
        if attr in set(_dataclass_field_names(cls)) | set(dir(cls)):
            failures.append(
                f"FORBIDDEN {cls_name}.{attr} now EXISTS -- the runner was written "
                f"assuming it does not; review before running")

    # Engine / AppState methods the critical path calls by name.
    try:
        from composition_root import Engine
        for m in ("start", "stop"):
            if not hasattr(Engine, m):
                failures.append(f"Engine.{m} MISSING")
        for p in ("adapter", "event_store", "position_manager", "portfolio_manager"):
            if not hasattr(Engine, p):
                failures.append(f"Engine.{p} MISSING")
    except Exception as exc:                                   # noqa: BLE001
        failures.append(f"composition_root.Engine unavailable: {exc}")

    try:
        from app.runtime import AppState
        for m in ("create", "run_one_cycle", "shutdown"):
            if not hasattr(AppState, m):
                failures.append(f"AppState.{m} MISSING")
    except Exception as exc:                                   # noqa: BLE001
        failures.append(f"app.runtime.AppState unavailable: {exc}")

    # The ENGINE_TEST plugin must exist and be classified correctly.
    try:
        from alpha_engine.platform import PluginKind, get_plugin
        entry = get_plugin("lifecycle_probe")
        if entry.kind is not PluginKind.ENGINE_TEST:
            failures.append(f"lifecycle_probe kind is {entry.kind}, expected ENGINE_TEST")
    except Exception as exc:                                   # noqa: BLE001
        failures.append(f"lifecycle_probe plugin unavailable: {exc}")

    # Attribution writer must exist and be non-raising by contract.
    try:
        from measurement import attribution
        if not callable(getattr(attribution, "record", None)):
            failures.append("measurement.attribution.record MISSING")
    except Exception as exc:                                   # noqa: BLE001
        failures.append(f"measurement.attribution unavailable: {exc}")

    return failures


# ----------------------------------------------------------------- outcome
@dataclass
class LifecycleOutcome:
    """What actually happened. Every field is set from verified attributes."""

    preflight_failures: List[str] = field(default_factory=list)
    precheck_flat: Optional[bool] = None
    entry_intent_side: Optional[str] = None
    entry_submitted_quantity: Optional[Decimal] = None
    venue_entry_quantity: Optional[Decimal] = None
    freshness_age_seconds: Optional[float] = None
    entry_submitted: bool = False
    entry_client_order_id: Optional[str] = None
    entry_exchange_order_id: Optional[str] = None
    entry_filled_quantity: Optional[Decimal] = None
    entry_lifecycle_state: Optional[str] = None
    position_id: Optional[str] = None
    position_quantity: Optional[Decimal] = None
    aged_seconds: Optional[float] = None
    close_submitted: bool = False
    close_reduce_only: Optional[bool] = None
    close_client_order_id: Optional[str] = None
    close_filled_quantity: Optional[Decimal] = None
    position_closed_locally: bool = False
    reconciliation_matches: Optional[bool] = None
    attribution_error: Optional[str] = None
    shutdown_clean: bool = False
    aborted_reason: Optional[str] = None
    risk_rejection: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        return (self.entry_submitted and self.close_submitted
                and self.position_closed_locally and self.aborted_reason is None)


# ------------------------------------------------------------------ runner
class SupervisedLifecycle:
    """One entry, natural ageing, one reduce-only close, guaranteed cleanup.

    venue_position_fn: callable returning the venue's current position
        quantity for the symbol (Decimal) or None when flat. Injected so the
        unit tests never touch the network; in the live run it is a
        read-only /info query.
    sleep_fn: injected so tests do not wait. This abstracts ELAPSED TIME
        ONLY -- it never fabricates a timestamp, never touches the engine or
        venue clock, and no clock injection reaches RiskManager. The live
        run passes time.sleep and ages the position for real.
    """

    def __init__(self, state, entries, *, venue_positions_fn,
                 sleep_fn: Callable[[float], None] = time.sleep,
                 now_fn: Callable[[], float] = time.monotonic,
                 age_seconds: int = AGE_SECONDS,
                 symbol: str = "BTC"):
        self._state = state
        self._entries = entries
        # Returns the venue's CURRENT positions -- a sequence of records
        # exposing .symbol and a SIGNED .quantity (exchange_adapter.Position
        # already satisfies this; hyperliquid_adapter/codec.py:146 sets
        # quantity=szi, so the sign carries the side and no separate field
        # is needed). Injected so unit tests never touch the network; the
        # live run passes engine.adapter.get_positions.
        self._venue_positions_fn = venue_positions_fn
        self._sleep = sleep_fn
        self._now = now_fn
        self._age_seconds = age_seconds
        self._symbol = symbol
        self._before_ids = None
        self.outcome = LifecycleOutcome()

    # -- helpers on the CRITICAL path: verified attributes only -----------

    def _place_executions(self, cycle_result):
        from trading_system.execution.models import ExecutionOperation
        return [e for e in cycle_result.executions
                if e.operation is ExecutionOperation.PLACE]

    def _open_position_ids(self):
        """Canonical enumeration: portfolio's own list of open ids.
        PositionManager has no list API -- see the module docstring."""
        return list(self._state.engine.portfolio_manager.get_snapshot().open_position_ids)

    # -- B-5: bounded READ retries -----------------------------------------

    def _venue_read(self):
        """Read venue positions with bounded retries.

        READS ONLY. A venue read is idempotent, so a transient transport
        failure is worth retrying; an order submission never is, and nothing
        in this class retries one.

        On exhaustion this raises UnknownVenueState rather than returning
        anything. That is deliberate: an exception must never be allowed to
        become "flat", "filled" or "closed". Unknown stays unknown.
        """
        last = None
        for attempt in range(READ_RETRY_ATTEMPTS):
            try:
                return list(self._venue_positions_fn())
            except Exception as exc:                           # noqa: BLE001
                last = exc
                _report("venue-read-retry", lambda a=attempt, e=exc: _log.warning(
                    "venue read failed (%d/%d): %s: %s",
                    a + 1, READ_RETRY_ATTEMPTS, type(e).__name__, e))
                if attempt + 1 < READ_RETRY_ATTEMPTS:
                    self._sleep(READ_RETRY_DELAY)
        raise UnknownVenueState(
            f"venue unreadable after {READ_RETRY_ATTEMPTS} attempts "
            f"({type(last).__name__}: {last}); STATE UNKNOWN -- verify the venue "
            f"manually before anything else")

    @staticmethod
    def _symbol_of(pos) -> str:
        sym = getattr(pos, "symbol", None)
        return getattr(sym, "value", sym)

    def _venue_positions_for_symbol(self, positions):
        return [p for p in positions
                if self._symbol_of(p) == self._symbol and p.quantity != 0]

    def _quantize(self, quantity: Decimal) -> Decimal:
        """Compare quantities on the VENUE's own grid, never a hand-rolled
        tolerance. Reuses the existing quantizer and the live venue rules."""
        from trading_system.execution.quantization import quantize_size
        rules = (self._state.quantization_rules or {}).get(self._symbol)
        if rules is None:
            return quantity
        return quantize_size(quantity, rules)

    # -- B-1: flat precheck ------------------------------------------------

    def _precheck_flat(self):
        """No entry may be submitted while ANY position exists.

        Without this, a pre-existing position makes the fill check below
        succeed instantly and the runner would age and close a position it
        never opened. A venue read failure aborts BEFORE submission, so an
        unknown venue can never be mistaken for a flat one.
        """
        positions = self._venue_read()          # raises UnknownVenueState
        live = [p for p in positions if p.quantity != 0]
        self.outcome.precheck_flat = not live
        if live:
            detail = ", ".join(f"{self._symbol_of(p)}={p.quantity}" for p in live)
            raise LifecycleAbort(
                f"venue is NOT flat before entry ({detail}); refusing to submit -- "
                f"a pre-existing position must be resolved manually first")
        self._before_ids = set(self._open_position_ids())
        if self._before_ids:
            raise LifecycleAbort(
                f"venue is flat but the engine still lists open positions "
                f"{sorted(self._before_ids)}; local/venue divergence, refusing to submit")

    def _risk_rejections(self, cycle_result) -> List[str]:
        out = []
        for r in cycle_result.construction.rejected:
            d = r.decision
            out.append(f"{getattr(d.decision, 'name', d.decision)} "
                       f"codes={[getattr(c, 'name', c) for c in (d.reason_codes or ())]} "
                       f"limits={list(d.violated_limits or ())}")
        return out

    # -- lifecycle phases -------------------------------------------------

    def _entry(self):
        result = self._state.run_one_cycle()
        _report("entry-cycle-summary", lambda: _log.info(
            "entry cycle: intents=%d approved=%d rejected=%d skipped=%d executions=%d",
            len(result.intents), len(result.construction.approved),
            len(result.construction.rejected), len(result.construction.skipped),
            len(result.executions)))

        rejections = self._risk_rejections(result)
        if rejections:
            self.outcome.risk_rejection = "; ".join(rejections)
            raise LifecycleAbort(f"entry rejected by risk: {self.outcome.risk_rejection}")

        places = self._place_executions(result)
        if not places:
            raise LifecycleAbort("entry produced no PLACE execution; not retrying")

        entry_intents = [i for i in result.intents if not i.reduce_only]
        if not entry_intents:
            raise LifecycleAbort("entry cycle produced no non-reduce_only intent; STOPPING")
        self.outcome.entry_intent_side = getattr(
            entry_intents[0].side, "value",
            getattr(entry_intents[0].side, "name", str(entry_intents[0].side)))

        snap = places[0].order_snapshot
        self.outcome.entry_submitted_quantity = snap.quantity
        self.outcome.entry_submitted = True
        self.outcome.entry_client_order_id = snap.client_order_id
        self.outcome.entry_exchange_order_id = snap.exchange_order_id
        self.outcome.entry_filled_quantity = snap.filled_quantity
        self.outcome.entry_lifecycle_state = getattr(
            snap.lifecycle_state, "name", str(snap.lifecycle_state))

        if snap.reject_reason:
            raise LifecycleAbort(f"entry rejected by venue: {snap.reject_reason}")
        return result

    def _await_entry_fill(self):
        """Submission is NOT a fill, and ANY non-zero position is NOT proof.

        The entry is accepted only when the venue shows EXACTLY ONE position
        in our symbol, whose SIGN matches the intent side and whose absolute
        quantity equals the submitted quantity on the venue's own grid.
        Partial, wrong-side, wrong-symbol and wrong-quantity states are all
        rejected. The order is never resubmitted.
        """
        expected = self._quantize(self.outcome.entry_submitted_quantity)
        want_long = self.outcome.entry_intent_side == "BUY"

        for attempt in range(FILL_POLL_ATTEMPTS):
            positions = self._venue_read()      # raises UnknownVenueState
            mine = self._venue_positions_for_symbol(positions)
            _report("fill-poll", lambda a=attempt, m=mine: _log.info(
                "fill poll %d/%d: %s positions=%s",
                a + 1, FILL_POLL_ATTEMPTS, self._symbol,
                [str(p.quantity) for p in m]))

            others = [p for p in positions
                      if p.quantity != 0 and self._symbol_of(p) != self._symbol]
            if others:
                raise LifecycleAbort(
                    f"unexpected position in another symbol "
                    f"({[self._symbol_of(p) for p in others]}); STOPPING")

            if len(mine) > 1:
                raise LifecycleAbort(
                    f"venue reports {len(mine)} {self._symbol} positions; ambiguous, STOPPING")

            if len(mine) == 1:
                qty = mine[0].quantity
                is_long = qty > 0
                if is_long != want_long:
                    raise LifecycleAbort(
                        f"venue position side does not match the entry intent "
                        f"(quantity={qty}, expected {'long' if want_long else 'short'}); STOPPING")
                actual = self._quantize(abs(qty))
                if actual != expected:
                    raise LifecycleAbort(
                        f"venue quantity {actual} != submitted {expected} "
                        f"(partial or unexpected fill); STOPPING, no retry")
                self.outcome.venue_entry_quantity = abs(qty)
                return abs(qty)

            self._sleep(FILL_POLL_INTERVAL)

        raise LifecycleAbort(
            f"entry not filled after {FILL_POLL_ATTEMPTS * FILL_POLL_INTERVAL}s "
            f"(state={self.outcome.entry_lifecycle_state}); STOPPING, no retry")

    def _identify_position(self):
        """Deterministic identity by SET DIFFERENCE against the pre-entry
        snapshot, which _precheck_flat proved empty. Never ids[0].

        PositionSnapshot carries no order linkage, and the only durable
        client_order_id -> position_id map is AccountingSync._position_by_cid,
        a private attribute of a frozen module. The set difference achieves
        the same identity using public APIs only.
        """
        if self._before_ids is None:
            raise LifecycleAbort("position identification attempted before the flat precheck")
        after = set(self._open_position_ids())
        new_ids = sorted(after - self._before_ids)

        if not new_ids:
            raise LifecycleAbort(
                "venue shows a fill but the engine observed no NEW open position "
                "-- local/venue divergence, STOPPING")
        if len(new_ids) > 1:
            raise LifecycleAbort(
                f"ambiguous position identity: {len(new_ids)} new positions {new_ids}; "
                f"refusing to guess, STOPPING")

        pid = new_ids[0]
        pos = self._state.engine.position_manager.get_position(pid)

        if self._symbol_of(pos) != self._symbol:
            raise LifecycleAbort(
                f"identified position {pid} is {self._symbol_of(pos)}, expected "
                f"{self._symbol}; STOPPING")
        side = getattr(pos.side, "value", getattr(pos.side, "name", str(pos.side)))
        if side != self.outcome.entry_intent_side:
            raise LifecycleAbort(
                f"identified position {pid} side {side} != entry intent "
                f"{self.outcome.entry_intent_side}; STOPPING")
        if pos.remaining_quantity <= 0:
            raise LifecycleAbort(
                f"position {pid} has non-positive quantity {pos.remaining_quantity}; STOPPING")
        if self._quantize(pos.remaining_quantity) != self._quantize(
                self.outcome.venue_entry_quantity):
            raise LifecycleAbort(
                f"position {pid} quantity {pos.remaining_quantity} disagrees with the "
                f"venue {self.outcome.venue_entry_quantity}; STOPPING")

        self.outcome.position_id = pid
        self.outcome.position_quantity = pos.remaining_quantity
        return pid

    def _age(self):
        """Real elapsed time. No clock injection, no timestamp manipulation."""
        started = self._now()
        _report("ageing-start", lambda: _log.warning(
            "ageing position for %ss (natural elapsed time; do not interrupt)",
            self._age_seconds))
        while True:
            elapsed = self._now() - started
            if elapsed >= self._age_seconds:
                break
            self._sleep(min(15, self._age_seconds - elapsed))
        self.outcome.aged_seconds = self._now() - started

    def _log_pre_close_observations(self):
        """OBSERVATION LOG AND REACHABILITY CHECK -- NOT A FRESHNESS GUARANTEE.

        The name matters. An earlier version of this method ABORTED when the
        portfolio observation was older than risk_max_stale_data_seconds, and
        that was wrong in a way that made the whole lifecycle impossible:

          - the observation is refreshed by AccountingSync at the START of a
            cycle (AppState.run_one_cycle), and NO cycle runs while the
            position ages;
          - the lifecycle deliberately ages ~AGE_SECONDS (195s) past the
            150s limit, which is the entire point of the test;
          - so at this moment the observation is ALWAYS ~195s old, and the
            gate fired every time, before the close was ever submitted.

        The close cycle refreshes the portfolio itself, immediately before
        RiskManager.evaluate(). Judging freshness here judges the wrong
        snapshot at the wrong time.

        What this method therefore does, and all it claims:
          1. proves the venue is REACHABLE before a close is attempted
             (an unreadable venue raises UnknownVenueState and stops);
          2. records the pre-close observation age for the evidence record.

        It never aborts on that age. RISKMANAGER REMAINS THE SOLE AUTHORITY
        on freshness -- if it rejects the close as stale, that is the
        definitive answer and _close aborts without retry. No RiskManager or
        AccountingSync logic is duplicated, and no timestamp is fabricated.
        """
        from datetime import datetime, timezone

        # Reachability only -- raises UnknownVenueState if the venue is down.
        # Never interpreted as flat, filled or closed.
        self._venue_read()

        snap = self._state.engine.portfolio_manager.get_snapshot()
        age = None
        try:
            observed = datetime.fromisoformat(snap.updated_at_utc)
            age = (datetime.now(timezone.utc) - observed).total_seconds()
            self.outcome.freshness_age_seconds = age
        except Exception as exc:                                # noqa: BLE001
            _log.error("could not parse portfolio timestamp (recorded, not fatal): "
                       "%s: %s", type(exc).__name__, exc)

        _report("pre-close-observations", lambda: _log.info(
            "pre-close: portfolio updated_at=%s (age=%ss) equity=%s open_positions=%d "
            "-- informational; the close cycle refreshes this and RiskManager decides",
            snap.updated_at_utc, "unknown" if age is None else f"{age:.1f}",
            snap.equity, len(snap.open_position_ids)))
        return snap

    def _close(self, position_id):
        """Close the IDENTIFIED position.

        WHY THIS ASSERTS RATHER THAN PASSES AN ID. The canonical path takes
        no position identifier: the probe emits a TradeIntent keyed by
        symbol, sizing sizes it, and reduce_only clamps at the venue.
        Directing a close at a specific position_id would require changing
        frozen TradeIntent. So the correspondence is established by
        INVARIANT instead -- the identified position must be the only one
        open, and the emitted intent and submitted order must match its
        symbol. position_id is the subject of those assertions, never
        decoration.
        """
        pos = self._state.engine.position_manager.get_position(position_id)
        open_now = set(self._open_position_ids())
        if open_now != {position_id}:
            raise LifecycleAbort(
                f"cannot target the close: expected only {position_id} open, "
                f"found {sorted(open_now)}; STOPPING")

        result = self._state.run_one_cycle()
        _report("close-cycle-summary", lambda: _log.info(
            "close cycle: intents=%d approved=%d rejected=%d executions=%d",
            len(result.intents), len(result.construction.approved),
            len(result.construction.rejected), len(result.executions)))

        reduce_only_intents = [i for i in result.intents if i.reduce_only]
        self.outcome.close_reduce_only = bool(reduce_only_intents)
        if not reduce_only_intents:
            raise LifecycleAbort("probe emitted no reduce_only intent; STOPPING")
        # The reduce-only intent must belong to the identified position.
        for intent in reduce_only_intents:
            if self._symbol_of(intent) != self._symbol_of(pos):
                raise LifecycleAbort(
                    f"reduce_only intent targets {self._symbol_of(intent)} but the "
                    f"identified position {position_id} is {self._symbol_of(pos)}; STOPPING")

        rejections = self._risk_rejections(result)
        if rejections:
            self.outcome.risk_rejection = "; ".join(rejections)
            raise LifecycleAbort(
                f"CLOSE REJECTED BY RISK -- no automatic retry: {self.outcome.risk_rejection}")

        places = self._place_executions(result)
        if not places:
            raise LifecycleAbort("close produced no PLACE execution; STOPPING")

        snap = places[0].order_snapshot
        if not snap.reduce_only:
            raise LifecycleAbort("submitted close order is NOT reduce_only; STOPPING")
        self.outcome.close_submitted = True
        self.outcome.close_client_order_id = snap.client_order_id
        self.outcome.close_filled_quantity = snap.filled_quantity
        if snap.reject_reason:
            raise LifecycleAbort(f"close rejected by venue: {snap.reject_reason}")
        return result

    def _await_close_fill(self):
        """Success requires the position to reach ZERO at the venue.

        A partial close is NOT success -- any residual quantity keeps
        polling and ultimately demands manual intervention. A venue read
        failure raises UnknownVenueState and is never read as "closed".
        The close order is never resubmitted.
        """
        for attempt in range(FILL_POLL_ATTEMPTS):
            positions = self._venue_read()      # raises UnknownVenueState
            mine = self._venue_positions_for_symbol(positions)
            _report("close-poll", lambda a=attempt, m=mine: _log.info(
                "close poll %d/%d: %s residual=%s", a + 1, FILL_POLL_ATTEMPTS,
                self._symbol, [str(p.quantity) for p in m] or "FLAT"))
            if not mine:
                return True
            self._sleep(FILL_POLL_INTERVAL)
        residual = self._venue_positions_for_symbol(self._venue_read())
        raise LifecycleAbort(
            f"close submitted but venue still shows "
            f"{[str(p.quantity) for p in residual]} in {self._symbol} "
            f"(partial or unfilled); MANUAL UI CLOSE REQUIRED, no automatic retry")

    def _verify_local_close(self):
        """Position-SPECIFIC: our pid must be gone. Using "no positions at
        all" would be permanently false if any unrelated position existed."""
        pid = self.outcome.position_id
        self.outcome.position_closed_locally = pid not in set(self._open_position_ids())
        if not self.outcome.position_closed_locally:
            _report("local-close-mismatch", lambda: _log.error(
                "venue reports flat but engine still lists open positions -- "
                "local/venue MISMATCH, reporting only"))

    def _reconcile(self):
        try:
            local = tuple(
                self._state.engine.position_manager.get_position(pid)
                for pid in self._open_position_ids())
            report = self._state.engine.adapter.reconcile(local)
            self.outcome.reconciliation_matches = report.matches
            if not report.matches:
                _report("reconcile-mismatch", lambda: _log.error(
                    "RECONCILIATION MISMATCH: %s", list(report.discrepancies)))
        except Exception as exc:                               # noqa: BLE001
            # Reconciliation is verification, not the trading path.
            _log.error("reconciliation failed (reported, not fatal): %s: %s",
                       type(exc).__name__, exc)
            self.outcome.reconciliation_matches = None

    def _shutdown(self):
        """Protected cleanup. Must never mask the original error."""
        try:
            self._state.shutdown()
            self.outcome.shutdown_clean = True
        except Exception as exc:                               # noqa: BLE001
            _log.error("shutdown failed: %s: %s", type(exc).__name__, exc)

    # -- the lifecycle ----------------------------------------------------

    def run(self) -> LifecycleOutcome:
        """Critical path in try/finally. Cleanup always runs."""
        try:
            self._precheck_flat()
            self._entry()
            self._await_entry_fill()
            pid = self._identify_position()
            self._age()
            self._log_pre_close_observations()
            self._close(pid)
            self._await_close_fill()
            self._verify_local_close()
            self._reconcile()
        except LifecycleAbort as exc:
            self.outcome.aborted_reason = str(exc)
            _log.error("LIFECYCLE ABORTED: %s", exc)
        except Exception as exc:                               # noqa: BLE001
            self.outcome.aborted_reason = f"{type(exc).__name__}: {exc}"
            _log.exception("LIFECYCLE FAILED UNEXPECTEDLY")
        finally:
            self._shutdown()
        return self.outcome


def main() -> int:
    """Deliberately hard to run by accident. Requires an explicit env
    confirmation in addition to whatever the operator configures."""
    if os.environ.get(CONFIRM_ENV) != CONFIRM_VALUE:
        print(f"refusing to run: set {CONFIRM_ENV}={CONFIRM_VALUE} to confirm "
              f"ONE supervised testnet lifecycle")
        return 2
    failures = preflight()
    if failures:
        for f in failures:
            print("PREFLIGHT FAILURE:", f)
        return 3
    print("preflight OK -- wiring is intentionally NOT performed by this module; "
          "the live run is assembled and authorized separately")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
