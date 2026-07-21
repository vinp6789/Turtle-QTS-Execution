"""Accounting synchronization: wires venue fills into OrderManager,
PositionManager, and PortfolioManager (fix for audit finding C1).

Before this module existed, fills stopped at the venue: nothing moved them
into position/portfolio accounting, so RiskManager evaluated every cycle
against a permanently empty portfolio (open_positions=(), heat=0,
exposure=0) -- max_positions/heat/margin checks were blind and identical
intents could stack unbounded positions across cycles and restarts.

WHAT THIS MODULE DOES (and nothing more):
  1. After each execution, durably records the order's price levels
     (stop/entry) so a fill arriving in ANY later cycle or process can
     still be booked (`record_execution_levels`).
  2. Each cycle, fetches engine-owned fills and routes every one through
     the already-existing frozen machinery (`sync`):
       - OrderManager     via orchestration.dispatch(FillObserved)  [fill dedup]
       - PositionManager  via create_position / record_entry_fill /
                          record_exit / complete_close               [fill dedup]
       - PortfolioManager via reserve_margin / allocate_margin /
                          apply_fee / apply_realized_pnl /
                          release_margin                             [key dedup]
  3. Refreshes portfolio marks (unrealized PnL / exposure / heat)
     aggregated from the live positions (`update_marks`).

WHY DUPLICATE FILLS CANNOT OCCUR (defense in depth, all durable):
  - OrderManager.report_fill dedups per fill_id (idempotency key
    "{cid}:fill:{fill_id}", order_manager/manager.py:570,592) and its
    processed-fill set is rebuilt on replay.
  - PositionManager.record_entry_fill/record_exit dedup per fill_id per
    position (idempotency keys "{pid}:entry:{fill_id}" /
    "{pid}:exit:{fill_id}", manager.py:341,379,401,435).
  - Every PortfolioManager call here uses a DETERMINISTIC key derived
    from the fill_id (reserve/allocate request_id=fill_id, fee_id=fill_id,
    leg_id=fill_id), and PortfolioManager checks Module 3's durable
    idempotency ledger before applying anything (manager.py:90-94,217-220).
  So re-processing the full venue fill history every cycle -- and across
  any restart -- is a durable no-op for already-booked fills.

WHY A CRASH CANNOT ORPHAN THE PORTFOLIO LEG (F1 fix):
  Portfolio calls are ALWAYS attempted for every fill, with amounts
  recomputed deterministically from the fill itself (never from an
  observed in-memory delta) -- the durable idempotency ledger, not a
  volatile gate, is what makes re-application a no-op. A crash at ANY
  point between the position fsync and the portfolio fsyncs therefore
  heals on the next sync: whatever was already applied dedups, whatever
  was not applies then. (An earlier build gated portfolio calls on the
  position call's observed delta; a crash between the two fsyncs then
  skipped the portfolio leg FOREVER -- audit finding F1.) The one
  deliberate exception: margin is never booked for a position already
  CLOSED/ARCHIVED, so a late-healing entry fill can never resurrect a
  dead position into open_position_ids.

EXIT POLICY (F2 conservative-skip, GENERALIZED to N fills by H-B):
  Frozen Module 7's CLOSE is a WHOLE-POSITION transition
  (position_manager/states.py:61,66,72 -- one step to CLOSED) and its
  transition table exposes only two sequential quantity-reducing edges
  (T1 then T2), so the frozen PositionManager STRUCTURALLY cannot
  represent a reduce-only close that arrives in N>=3 fills, and calling
  record_exit(CLOSE) on any single partial fill would terminate the
  position early with a nonzero residual. Real venues routinely split a
  reduce-only close into many fills (100 -> 30 + 40 + 30), which the
  earlier build skipped every time -- so the position never closed, its
  margin never released, and the slot was consumed forever (audit
  finding H-B).

  This layer therefore closes a position across ANY number of fills
  without fabricating a fill, inferring a quantity, or inventing a price:

    - Realized PnL is booked to the PORTFOLIO ledger PER FILL (side-aware,
      F3), each with idempotency key leg_id=fill_id -- so every partial
      tranche's PnL is captured exactly once at its own real price, and
      re-processing the full fill history (each cycle, and after any
      restart) is a durable no-op.
    - Closed quantity is accumulated in memory against the position's
      STABLE filled_quantity (record_exit changes remaining, never
      filled_quantity). Accumulation is idempotent within a process
      (guarded by a processed-fill set) and rebuilt from the venue's fill
      history on restart -- it is NOT persisted, so it adds no EventStore
      state and cannot slow replay.
    - When the accumulated close reaches filled_quantity, the position is
      finalized EXACTLY ONCE: a single frozen record_exit(CLOSE) moves it
      to the durable terminal CLOSED state (so it replays terminal and is
      excluded from _find_open_position after any restart), and
      release_margin frees the slot + returns margin (idempotent per
      position). Both are no-ops on every subsequent re-sync.

  Margin is released only at FULL close (frozen release_margin is
  whole-position); during a partial close the position's margin stays
  fully held -- risk over-counts, the safe direction. Exit attribution is
  made durable BEFORE the first state change (an exit-cid -> position_id
  mapping event), so the exit leg has no crash window: a restart re-finds
  the position by the durable map even after it is CLOSED.

  Known cosmetic residual (capital-irrelevant): the frozen PositionManager
  snapshot for a multi-fill close ends in state CLOSED with
  remaining_quantity = filled_quantity - (final fill's quantity), because
  the single record_exit(CLOSE) can only subtract one fill's quantity and
  fabricating a full-size fill is forbidden. Once release_margin removes
  the pid from PortfolioManager.open_position_ids, NOTHING (risk,
  reconciliation, marks, exit attribution) reads that snapshot again -- so
  the residual is inert. The authoritative equity/margin/slot record is
  the portfolio ledger, which is exactly correct.

SHORT POSITIONS (F3 fix):
  Frozen Module 7's PnL arithmetic is long-only ((exit-entry)*qty and
  (mark-entry)*qty, position_manager/pnl.py:72-80, no side parameter).
  This layer therefore computes BOTH realized and unrealized PnL
  side-aware itself (direction = +1 long / -1 short) and never feeds
  Module 7's own realized/unrealized figures into the portfolio ledger.
  PositionSnapshot.realized_pnl / realized_r remain long-biased
  frozen-internal bookkeeping; the PORTFOLIO ledger is the authoritative
  equity record.

WHY DUPLICATE POSITIONS CANNOT OCCUR (and the one bounded exception):
  PositionManager.create_position mints its own position_id, so this
  module durably records client_order_id -> position_id in the shared
  EventStore (source-tagged "app_accounting", the same additive pattern
  every frozen module uses) and rebuilds that map on construction. The
  only gap is a hard crash in the microseconds between create_position's
  fsync'd CREATE event and this module's fsync'd mapping event: on
  restart the map misses, a second position is created, and the first
  remains an ORPHAN in state NEW forever. That orphan is inert by
  construction: it never receives a fill, never has margin allocated,
  and therefore NEVER appears in PortfolioManager.open_position_ids --
  so it can never influence a risk decision (fail-safe direction).

DELIBERATE LIMITS (documented, not hidden):
  - An entry fill whose order has no durably recorded levels (e.g. an
    order placed by a pre-fix build) is NOT booked into a position: this
    module never fabricates a stop price for capital bookkeeping. The
    skip is surfaced in the returned error list.
  - T1/T2 levels are not carried by TradeRequest (they die with the
    TradeIntent); positions are created with the classic R-multiple
    defaults t1 = entry +/- 1*stop_d, t2 = entry +/- 2*stop_d purely as
    descriptive bookkeeping fields -- PositionManager never acts on them
    on its own (it is "pure bookkeeping over caller-supplied levels").
  - Reduce-only fills are booked as CLOSE exits against this module's
    own open position for the same symbol/opposite side; an
    unattributable reduce-only fill is skipped and surfaced.
  - A portfolio funding failure (InsufficientFundsError) on a fill that
    ALREADY happened at the venue is surfaced, not raised: the books
    then under-state margin until reconciliation flags it -- refusing to
    crash the cycle loop over it is the lesser risk. RiskManager's own
    margin check makes this path effectively unreachable in normal
    operation.

No frozen module is modified. Every call below is a public, frozen API.
"""

from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from event_store import EventType
from exchange_adapter import Fill, OrderSide
from order_manager import OrderManagerError, OrderNotFoundError
from position_manager import PositionLifecycleState, PositionLifecycleTrigger, PositionManagerError
from portfolio_manager import PortfolioManagerError

from composition_root import Engine
from orchestration import FillObserved, dispatch
from trading_system.execution import ExecutionResult

_SOURCE_TAG = "app_accounting"
_ACTION_LEVELS = "order_levels_recorded"
_ACTION_MAPPED = "order_position_mapped"

_TERMINAL_POSITION_STATES = frozenset({PositionLifecycleState.CLOSED, PositionLifecycleState.ARCHIVED})


class AccountingSync:
    """One instance per Engine (created by AppState). All methods are
    called under AppState.engine_lock, so no additional locking is
    needed here; the frozen modules keep their own internal locks."""

    def __init__(self, engine: Engine, target_leverage: Decimal = Decimal("1")):
        self._engine = engine
        self._target_leverage = target_leverage
        self._levels_by_cid: Dict[str, Tuple[Decimal, Decimal]] = {}  # cid -> (entry, stop)
        self._position_by_cid: Dict[str, str] = {}
        # H-B: in-memory reduce-only close accumulation. NOT persisted --
        # rebuilt from the venue fill history on every sync (and thus after
        # any restart), so it adds no EventStore state and cannot slow
        # replay. `_counted_exit_fills` makes the per-cycle re-scan a no-op
        # (each fill contributes to `_closed_qty_by_pid` exactly once per
        # process lifetime); `_closed_qty_by_pid` is compared against the
        # position's stable filled_quantity to detect a completed close.
        self._closed_qty_by_pid: Dict[str, Decimal] = {}
        self._counted_exit_fills: set = set()
        # Rebuild both maps from this module's own source-tagged events.
        for event in engine.event_store.replay():
            payload = event.payload
            if payload.get("source") != _SOURCE_TAG:
                continue
            if payload.get("action") == _ACTION_LEVELS:
                self._levels_by_cid[payload["client_order_id"]] = (
                    Decimal(payload["entry_price"]), Decimal(payload["stop_price"]),
                )
            elif payload.get("action") == _ACTION_MAPPED:
                self._position_by_cid[payload["client_order_id"]] = payload["position_id"]

    # -- durable helpers --

    def _append(self, action: str, key: str, **fields) -> None:
        payload = {"source": _SOURCE_TAG, "action": action, **fields}
        self._engine.event_store.append(
            EventType.POSITION_UPDATED, payload, idempotency_key=f"{_SOURCE_TAG}:{action}:{key}",
        )

    # -- step 1: persist levels at execution time --

    def record_execution_levels(self, executions: Tuple[ExecutionResult, ...]) -> None:
        """Durably records entry/stop for every executed order so fills in
        later cycles/processes can still be booked. Idempotent per cid."""
        for result in executions:
            if result.trade_request is None:
                continue
            cid = result.order_snapshot.client_order_id
            if cid in self._levels_by_cid:
                continue
            entry = result.trade_request.entry_price
            stop = result.trade_request.stop_price
            self._append(
                _ACTION_LEVELS, cid, client_order_id=cid,
                entry_price=str(entry), stop_price=str(stop),
            )
            self._levels_by_cid[cid] = (entry, stop)

    # -- step 2: book fills --

    def sync(self) -> List[str]:
        """Fetches engine-owned fills and books every one. Returns a list
        of human-readable notes for anything skipped/failed; an empty
        list means everything reconciled cleanly. Never raises for a
        single bad fill -- one unbookable fill must not stall the rest."""
        notes: List[str] = []
        try:
            fills = self._engine.order_manager.get_fills()
        except Exception as exc:  # noqa: BLE001 -- venue read failure: report, retry next cycle
            return [f"fill fetch failed: {type(exc).__name__}: {exc}"]

        for fill in fills:
            try:
                self._book_one(fill, notes)
            except (OrderManagerError, PositionManagerError, PortfolioManagerError, ValueError) as exc:
                notes.append(f"fill {fill.fill_id} ({fill.client_order_id}): {type(exc).__name__}: {exc}")
        return notes

    def _book_one(self, fill: Fill, notes: List[str]) -> None:
        cid = fill.client_order_id
        # 2a. OrderManager, via the frozen orchestration route (dedups by fill_id).
        try:
            dispatch(self._engine, FillObserved(cid, fill))
        except OrderNotFoundError:
            notes.append(f"fill {fill.fill_id}: order {cid!r} unknown to OrderManager -- skipped")
            return

        order = self._engine.order_manager.get_order_status(cid)
        if order.reduce_only:
            self._book_exit(fill, notes)
        else:
            self._book_entry(fill, order.quantity, notes)

    def _book_entry(self, fill: Fill, intended_quantity: Decimal, notes: List[str]) -> None:
        cid = fill.client_order_id
        position_manager = self._engine.position_manager
        portfolio = self._engine.portfolio_manager

        pid = self._position_by_cid.get(cid)
        if pid is None:
            levels = self._levels_by_cid.get(cid)
            if levels is None:
                notes.append(
                    f"fill {fill.fill_id}: no recorded stop/entry levels for {cid!r} -- "
                    "position not created (never fabricating a stop price)"
                )
                return
            entry, stop = levels
            stop_d = abs(entry - stop)
            if stop_d <= 0:
                notes.append(f"fill {fill.fill_id}: degenerate stop distance for {cid!r} -- skipped")
                return
            # T1/T2: descriptive R-multiple bookkeeping defaults (see module
            # docstring) -- the strategy's own levels are not carried by
            # TradeRequest.
            if fill.side is OrderSide.BUY:
                t1, t2 = entry + stop_d, entry + 2 * stop_d
            else:
                t1, t2 = entry - stop_d, entry - 2 * stop_d
            snapshot = position_manager.create_position(
                symbol=fill.symbol, side=fill.side, intended_quantity=intended_quantity,
                stop_price=stop, stop_d=stop_d, t1_price=t1, t2_price=t2,
            )
            pid = snapshot.position_id
            self._append(_ACTION_MAPPED, cid, client_order_id=cid, position_id=pid)
            self._position_by_cid[cid] = pid

        before = position_manager.get_position(pid)
        snapshot = position_manager.record_entry_fill(pid, fill)  # dedups by fill_id

        # F1: ALWAYS attempt the portfolio leg -- the fill-id-keyed durable
        # ledger dedups already-applied calls, and a crash-orphaned leg
        # heals here on the next sync. Amounts are recomputed from the
        # fill itself, so retries are byte-identical. Never book margin
        # for a dead position (see module docstring); the before/after
        # compare below is ONLY note-noise suppression for re-synced
        # historical fills -- it never gates a live position's portfolio
        # calls (that gate was exactly audit finding F1).
        if snapshot.lifecycle_state in _TERMINAL_POSITION_STATES:
            if snapshot.filled_quantity != before.filled_quantity:
                notes.append(
                    f"fill {fill.fill_id}: position {pid} is {snapshot.lifecycle_state.value} -- "
                    "margin not booked for a dead position"
                )
            return
        margin = (fill.quantity * fill.price) / self._target_leverage
        try:
            portfolio.reserve_margin(pid, margin, request_id=fill.fill_id)
            portfolio.allocate_margin(pid, margin, request_id=fill.fill_id)
        except (PortfolioManagerError,) as exc:
            notes.append(f"fill {fill.fill_id}: margin booking failed for {pid}: {exc}")
        if fill.fee > 0:
            portfolio.apply_fee(reference_id=pid, fee_id=fill.fill_id, amount=fill.fee, request_id=fill.fill_id)

    def _book_exit(self, fill: Fill, notes: List[str]) -> None:
        position_manager = self._engine.position_manager
        portfolio = self._engine.portfolio_manager
        cid = fill.client_order_id

        # Durable exit attribution. A previously-attributed exit order
        # (retry / crash continuation / any later tranche of the same
        # order) is honored via the durable map even after the position has
        # CLOSED; only a FIRST attribution goes through discovery.
        pid = self._position_by_cid.get(cid)
        if pid is None:
            pid = self._find_open_position(fill.symbol, closing_side=fill.side)
            if pid is None:
                notes.append(
                    f"reduce-only fill {fill.fill_id} ({fill.symbol.value}): no matching open "
                    "position -- skipped (never guessing an attribution)"
                )
                return
            # Durable claim BEFORE any state change, so a crash after
            # finalization can still re-attribute on restart.
            self._append(_ACTION_MAPPED, cid, client_order_id=cid, position_id=pid)
            self._position_by_cid[cid] = pid

        position = position_manager.get_position(pid)

        # H-B/F3: book THIS fill's realized PnL to the authoritative
        # portfolio ledger, side-aware, at its OWN real price -- PER FILL,
        # including every partial tranche. Idempotent by leg_id=fill_id, so
        # re-processing the fill history (each cycle / after restart) never
        # double-books. avg_entry_price is the entry average and is stable
        # across the close (record_exit changes remaining, never the entry
        # average), so reading it before finalization is exact.
        if position.avg_entry_price is not None:
            direction = Decimal("1") if position.side is OrderSide.BUY else Decimal("-1")
            realized = direction * (fill.price - position.avg_entry_price) * fill.quantity - fill.fee
            portfolio.apply_realized_pnl(pid, leg_id=fill.fill_id, amount=realized, request_id=fill.fill_id)

        # H-B: accumulate closed quantity exactly once per fill per process
        # (rebuilt from the venue fill history on restart; not persisted).
        if fill.fill_id not in self._counted_exit_fills:
            self._counted_exit_fills.add(fill.fill_id)
            self._closed_qty_by_pid[pid] = self._closed_qty_by_pid.get(pid, Decimal("0")) + fill.quantity

        # A tranche of an already-finalized close (re-sync / restart): its
        # PnL was re-booked idempotently above; the position is terminal,
        # margin already released -- nothing is pending, so emit no note and
        # do nothing further. This keeps a re-sync of a completed close a
        # true no-op (no events, no note-noise on last_error).
        if position.lifecycle_state in _TERMINAL_POSITION_STATES:
            return

        closed = self._closed_qty_by_pid.get(pid, Decimal("0"))
        if closed < position.filled_quantity:
            notes.append(
                f"reduce-only fill {fill.fill_id} ({fill.symbol.value}): partial close "
                f"{closed}/{position.filled_quantity} for {pid} -- PnL booked, awaiting remaining fills"
            )
            return

        # Full close reached (closed >= filled_quantity). Finalize EXACTLY
        # ONCE: a single frozen record_exit(CLOSE) moves the position to the
        # durable terminal CLOSED state, and release_margin frees the slot +
        # returns margin (idempotent per position). Both are no-ops on every
        # subsequent re-sync (guarded by the terminal check above and the
        # frozen per-position release ledger).
        position_manager.record_exit(
            pid, fill, PositionLifecycleTrigger.CLOSE, reason="reduce_only_fill",
        )
        portfolio.release_margin(pid, request_id=f"close:{pid}")

    # -- step 3: mark-to-market aggregation --

    def update_marks(self) -> None:
        """Aggregates unrealized PnL / exposure / heat across this
        module's open positions and pushes one UPDATE_MARKS event. Skipped
        entirely when there is nothing open AND marks are already zero, so
        idle cycles still append no events."""
        portfolio = self._engine.portfolio_manager
        position_manager = self._engine.position_manager

        open_pids = [
            pid for pid in self._position_by_cid.values()
            if pid in portfolio.get_snapshot().open_position_ids
        ]
        snapshot = portfolio.get_snapshot()
        if not open_pids and snapshot.exposure == 0 and snapshot.unrealized_pnl == 0 and snapshot.heat == 0:
            return

        total_upnl = Decimal("0")
        total_exposure = Decimal("0")
        total_open_risk = Decimal("0")
        for pid in open_pids:
            pos = position_manager.get_position(pid)
            if pos.remaining_quantity <= 0 or pos.avg_entry_price is None:
                continue
            mark = self._engine.adapter.get_mark_price(pos.symbol).price
            # F3: side-aware unrealized PnL computed here -- frozen
            # PositionManager.unrealized_pnl is long-only (pnl.py:79-80).
            direction = Decimal("1") if pos.side is OrderSide.BUY else Decimal("-1")
            total_upnl += direction * (mark - pos.avg_entry_price) * pos.remaining_quantity
            total_exposure += pos.remaining_quantity * mark
            total_open_risk += pos.remaining_quantity * pos.stop_d

        equity = snapshot.equity
        heat = (total_open_risk / equity) if equity > 0 else Decimal("0")
        # Idempotency key = last-event timestamp + the values themselves:
        # a repeat call with unchanged inputs dedups (no append -- idle
        # cycles with open positions but unmoved marks append nothing),
        # while any change in marks OR any intervening event yields a new
        # key. The timestamp component makes value revisits (100 -> 200
        # -> 100) distinct keys, so replay always lands on the latest.
        portfolio.update_marks(
            unrealized_pnl=total_upnl, exposure=total_exposure, heat=heat,
            request_id=f"marks:{snapshot.updated_at_utc}:{total_upnl}:{total_exposure}:{heat}",
        )

    # -- helpers --

    def _find_open_position(self, symbol, closing_side) -> Optional[str]:
        opening_side = OrderSide.SELL if closing_side is OrderSide.BUY else OrderSide.BUY
        for pid in self._position_by_cid.values():
            try:
                pos = self._engine.position_manager.get_position(pid)
            except PositionManagerError:
                continue
            if (
                pos.symbol.value == symbol.value
                and pos.side is opening_side
                and pos.lifecycle_state not in _TERMINAL_POSITION_STATES
                and pos.remaining_quantity > 0
            ):
                return pid
        return None
