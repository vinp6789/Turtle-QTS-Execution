"""run_cycle(): coordinates exactly one deterministic trading cycle.

This module contains no business logic of its own. Every step below is a
call to an already-existing function/method from a lower layer; this
module only decides the ORDER and wires each stage's output into the
next stage's input:

    Startup (if needed)   -> composition_root.Engine.start()
    Synchronization       -> orchestration.synchronize()
    Reconciliation        -> orchestration.reconcile()
    Market Data           -> trading_system.market_data.MarketDataView
                             + assembling trading_system.strategy.StrategyContext
    Strategies            -> each Strategy.generate_intents(context)
    Sizing + Portfolio
      Construction        -> trading_system.portfolio_construction.
                             construct_trade_requests() (sizing already
                             happens INSIDE this call, per Milestone 6 --
                             there is no separate top-level "sizing step"
                             to call independently without duplicating
                             what portfolio_construction already does)
    Execution             -> trading_system.execution.execute_place()
                             for every approved TradeRequest
    Cycle Complete        -> CycleResult returned

Deployment-agnostic by construction: nothing here imports os, sys,
platform, subprocess, any cloud SDK, any web framework, or any messaging
library. run_cycle() takes plain Python objects in and returns a plain
Python object out -- it has no opinion on whether it is called from a
laptop's __main__ block, a cron entry, a Docker CMD, a FastAPI route
handler, or a Telegram command handler. Calling it once executes one
cycle; calling it in a loop (the caller's own loop, not this module's)
executes many. This module contains no loop, timer, thread, or async of
its own.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Mapping, Optional, Tuple

from config import RiskProfileParams
from exchange_adapter import OrderStatus, Symbol
from risk_manager import CorrelationInfo, Decision, ReasonCode, RiskDecision

from composition_root import Engine
from orchestration import reconcile, synchronize
from trading_system.execution import ExecutionResult, QuantizationRules, execute_place
from trading_system.market_data import MarketDataView
from trading_system.portfolio_construction import construct_trade_requests
from trading_system.strategy import Strategy, StrategyContext

from .errors import SchedulingError
from .models import CycleResult


def _default_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _approved_marker(decision_timestamp: str) -> RiskDecision:
    """A minimal RiskDecision re-affirming a KNOWN fact, never fabricating
    one: every TradeRequest this is attached to came from
    ConstructionResult.approved, which by construct_trade_requests' own
    implementation (Milestone 6) contains only TradeRequests that already
    received a real Decision.APPROVED from THIS SAME cycle's RiskManager.
    evaluate() call moments earlier.

    Why this exists: trading_system.execution.execute_place() (Milestone
    7) requires a RiskDecision as its own safety gate -- by design, it
    never submits an order without one, and this module must not weaken
    that gate. But trading_system.portfolio_construction.ConstructionResult
    (Milestone 6) intentionally returns `approved` as bare TradeRequests
    (matching that milestone's literal instruction), not paired with the
    RiskDecision that approved them. This is a genuine interface gap
    between two already-approved milestones, surfaced only now that both
    are wired together end-to-end -- bridged here via composition (a new,
    additive helper in this new package), not by modifying either frozen
    package. This function never calls RiskManager.evaluate() and never
    decides anything; it only reconstructs the pass/fail token
    execute_place() already requires, for a trade already known to have
    passed. See Milestone 8's delivery report for the full rationale."""
    return RiskDecision(
        decision=Decision.APPROVED,
        reason_codes=(ReasonCode.OK,),
        violated_limits=(),
        calculated_exposure=None,
        calculated_heat=None,
        leverage=None,
        liquidation_buffer=None,
        funding_estimate=None,
        timestamp_utc=decision_timestamp,
        audit_metadata={"source": "trading_system.scheduling: reconstructed from ConstructionResult.approved"},
    )


def run_cycle(
    engine: Engine,
    strategies: Tuple[Strategy, ...],
    *,
    universe: Tuple[Symbol, ...],
    risk_profile: RiskProfileParams,
    correlation_info: CorrelationInfo,
    maintenance_margin_rate: Decimal,
    target_leverage: Decimal = Decimal("1"),
    volatility_by_symbol: Optional[Mapping[Symbol, Decimal]] = None,
    clock: Callable[[], str] = _default_now,
    on_execution: Optional[Callable[[ExecutionResult], None]] = None,
    quantization_rules: Optional[QuantizationRules] = None,
) -> CycleResult:
    """Executes exactly one trading cycle and returns. Never loops, never
    sleeps, never schedules a next call -- call this again yourself
    (from whatever deployment mechanism you choose) for the next cycle.

    engine: an already-built composition_root.Engine (paper or live --
        this function never inspects which; that distinction was already
        resolved when the Engine was built).
    strategies: every configured Strategy is invoked this cycle; their
        TradeIntents are pooled together before portfolio construction
        (which already handles cross-strategy deduplication/prioritization
        -- see Milestone 6).
    universe, risk_profile, correlation_info, maintenance_margin_rate,
        target_leverage, volatility_by_symbol: passed straight through to
        trading_system.portfolio_construction.construct_trade_requests();
        see that function's own docstring for what each means. None of
        these has a natural source on Engine itself (composition_root.Engine
        carries no EngineConfig), so the caller supplies them explicitly --
        deliberately, so this module never guesses.
    clock: returns the current UTC time as an ISO 8601 string; overridable
        only for deterministic tests. Not a timer -- called exactly once
        per run_cycle() invocation, never scheduled.
    on_execution: optional per-execution hook, invoked synchronously with
        each ExecutionResult IMMEDIATELY after its execute_place() returns
        -- before the next order is attempted and before the CycleResult
        exists. Added (additively; None preserves the exact prior
        behavior) so a caller can durably record per-order metadata (e.g.
        app-layer accounting levels) with a crash window of one append
        rather than the remainder of the execution loop: if order N+1's
        placement -- or the process -- fails, orders 1..N have already
        been handed to the hook. A hook exception aborts the cycle
        (fail-loud): an order whose metadata could not be durably
        recorded must surface immediately, not trade on silently.
    quantization_rules: optional venue quantization rules (C2), passed
        straight through to trading_system.execution.execute_place --
        see its docstring. None (the default) preserves prior behavior
        exactly; the app layer supplies real venue rules for live engines.
    """
    if not isinstance(engine, Engine):
        raise SchedulingError(f"engine must be a composition_root.Engine, got {type(engine).__name__}")
    if not all(isinstance(s, Strategy) for s in strategies):
        raise SchedulingError("strategies must contain only Strategy instances")

    started = False
    health = None
    if not engine.is_started:
        health = engine.start()
        started = True

    resynced_orders = synchronize(engine)
    reconciliation = reconcile(engine)

    evaluated_at_utc = clock()
    portfolio_snapshot = engine.portfolio_manager.get_snapshot()
    open_positions = tuple(
        engine.position_manager.get_position(position_id)
        for position_id in portfolio_snapshot.open_position_ids
    )
    context = StrategyContext(
        universe=universe,
        portfolio_snapshot=portfolio_snapshot,
        open_positions=open_positions,
        kill_switch_state=engine.execution_state_machine.current_state,
        market_data=MarketDataView(engine),
        evaluated_at_utc=evaluated_at_utc,
    )

    intents = tuple(
        intent
        for strategy in strategies
        for intent in strategy.generate_intents(context)
    )

    # H-A fix: suppress intents whose (symbol, reduce_only) already has a
    # LIVE engine-owned order at the venue. StrategyContext exposes only
    # FILLED positions, so a limit order resting across cycles is invisible
    # to the strategy -- which then naturally re-emits the same intent, and
    # every cycle would mint a NEW client_order_id (a fresh order, not an
    # idempotent retry): N cycles -> N resting orders -> N fills -> N x the
    # intended exposure. This filter is STRUCTURAL -- correctness never
    # depends on strategy authors remembering to dedup against state they
    # cannot even see.
    #
    # Matching is on (symbol, reduce_only), deliberately:
    #   - a resting ENTRY blocks further entry intents for that symbol
    #     (any side: same-symbol entry churn while an order rests is
    #     exactly the stacking hazard);
    #   - a resting entry NEVER blocks a reduce-only (risk-REDUCING)
    #     intent -- suppressing a close because an entry rests would be
    #     the unsafe direction;
    #   - a resting reduce-only order blocks further reduce-only intents
    #     (duplicate closes would over-close).
    # "Live" = any non-terminal venue status; UNKNOWN counts as live
    # (unknown equals unsafe: never place on top of an order whose state
    # is unclear). Read once per cycle from the frozen adapter's
    # engine-owned view (venue truth on live; O(orders + intents) set
    # membership, no persistence, no new state -- replay, idempotency,
    # and crash recovery are untouched because this writes nothing.
    live_order_keys = {
        (order.symbol.value, order.reduce_only)
        for order in engine.adapter.get_orders()
        if order.status not in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED)
    }
    suppressed_by_open_orders = tuple(
        intent for intent in intents
        if (intent.symbol.value, intent.reduce_only) in live_order_keys
    )
    tradable_intents = tuple(
        intent for intent in intents
        if (intent.symbol.value, intent.reduce_only) not in live_order_keys
    )

    construction = construct_trade_requests(
        tradable_intents,
        context,
        risk_manager=engine.risk_manager,
        risk_profile=risk_profile,
        capabilities=engine.adapter.capabilities,
        correlation_info=correlation_info,
        maintenance_margin_rate=maintenance_margin_rate,
        target_leverage=target_leverage,
        volatility_by_symbol=volatility_by_symbol,
    )

    executed = []
    for trade_request in construction.approved:
        result = execute_place(
            trade_request, _approved_marker(evaluated_at_utc), engine.order_manager,
            rules=quantization_rules,
        )
        if on_execution is not None:
            on_execution(result)
        executed.append(result)
    executions = tuple(executed)

    return CycleResult(
        started=started,
        health=health,
        resynced_orders=resynced_orders,
        reconciliation=reconciliation,
        intents=intents,
        construction=construction,
        executions=executions,
        evaluated_at_utc=evaluated_at_utc,
        suppressed_by_open_orders=suppressed_by_open_orders,
    )
