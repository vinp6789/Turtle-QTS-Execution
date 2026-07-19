"""Portfolio-level filtering/prioritization across multiple TradeIntents,
producing RiskManager-approved TradeRequests.

Ownership boundary (why this does not duplicate risk logic): every
pass/fail RULE (risk-per-trade, heat cap, max positions, margin,
leverage, liquidation buffer, funding, correlation, capability support)
lives exclusively in risk_manager.RiskManager.evaluate(), called here
unchanged, once per surviving candidate. This module only decides, among
several simultaneous candidates, WHICH ones are even considered and in
WHAT ORDER -- concerns RiskManager has no visibility into, since it only
ever evaluates one already-built TradeRequest at a time:

  1. Universe filtering: an intent for a symbol outside context.universe
     is out of scope for this engine instance and is skipped (a scope
     guard, not a risk rule).
  2. Deduplication: if multiple intents target the same symbol (e.g. two
     strategies both propose BTC), only the highest-|conviction| one is
     kept -- RiskManager has no concept of "which of several ideas for
     the same symbol wins."
  3. Prioritization: surviving intents are evaluated in descending
     |conviction| order (missing conviction sorts last), so that when
     capacity is genuinely limited, RiskManager's own max_positions/
     heat_cap checks are exercised against the most-preferred candidates
     first.

Known, deliberate limitation (documented, not silently assumed): each
candidate is evaluated against context.portfolio_snapshot/open_positions
UNCHANGED across the whole batch -- this module does not simulate the
cumulative effect of approving several candidates within the same call.
Each RiskDecision therefore answers "would this be approved if it were
the only new trade proposed this cycle," not "approved accounting for
sibling approvals in this same batch." Simulating the latter would mean
fabricating synthetic PositionSnapshot/PortfolioSnapshot state RiskManager
never actually computed -- a correctness risk this milestone declines to
take on. A future milestone that submits approved TradeRequests
sequentially through the real OrderManager will see the true, updated
state from PositionManager/PortfolioManager before each subsequent
evaluation, which is where the real cumulative check belongs.

No caching, no polling, no scheduling, no thread, no OrderManager call.
Every market-data read goes through context.market_data (Milestone 5's
facade) fresh, every time.
"""

from decimal import Decimal
from typing import Mapping, Optional, Tuple

from config import RiskProfileParams
from exchange_adapter import ExchangeCapabilities, Symbol
from risk_manager import CorrelationInfo, Decision, FundingInfo, RiskManager

from ..sizing import SizingError, size_intent
from ..strategy import StrategyContext, TradeIntent
from .errors import PortfolioConstructionError
from .models import ConstructionResult, RejectedTrade, SkippedIntent


def _conviction_sort_key(intent: TradeIntent) -> Decimal:
    # Missing conviction sorts LAST (lowest priority), never treated as
    # "maximally convicted" by defaulting to something large.
    return abs(intent.conviction) if intent.conviction is not None else Decimal("-1")


def construct_trade_requests(
    intents: Tuple[TradeIntent, ...],
    context: StrategyContext,
    *,
    risk_manager: RiskManager,
    risk_profile: RiskProfileParams,
    capabilities: ExchangeCapabilities,
    correlation_info: CorrelationInfo,
    maintenance_margin_rate: Decimal,
    target_leverage: Decimal = Decimal("1"),
    volatility_by_symbol: Optional[Mapping[Symbol, Decimal]] = None,
) -> ConstructionResult:
    if not isinstance(context, StrategyContext):
        raise PortfolioConstructionError(f"context must be a StrategyContext, got {type(context).__name__}")
    if not isinstance(risk_manager, RiskManager):
        raise PortfolioConstructionError(f"risk_manager must be a RiskManager, got {type(risk_manager).__name__}")
    if not isinstance(risk_profile, RiskProfileParams):
        raise PortfolioConstructionError(f"risk_profile must be a RiskProfileParams, got {type(risk_profile).__name__}")
    if not isinstance(correlation_info, CorrelationInfo):
        raise PortfolioConstructionError(f"correlation_info must be a CorrelationInfo, got {type(correlation_info).__name__}")
    if not all(isinstance(i, TradeIntent) for i in intents):
        raise PortfolioConstructionError("intents must contain only TradeIntent instances")

    skipped = []
    in_universe = []
    for intent in intents:
        if intent.symbol not in context.universe:
            skipped.append(SkippedIntent(intent, f"symbol {intent.symbol.value} is outside context.universe"))
        else:
            in_universe.append(intent)

    by_symbol: "dict[Symbol, list]" = {}
    for intent in in_universe:
        by_symbol.setdefault(intent.symbol, []).append(intent)

    survivors = []
    for symbol, group in by_symbol.items():
        if len(group) == 1:
            survivors.append(group[0])
            continue
        winner = max(group, key=_conviction_sort_key)
        survivors.append(winner)
        for loser in group:
            if loser is not winner:
                skipped.append(
                    SkippedIntent(
                        loser,
                        f"duplicate intent for {symbol.value}: a higher-|conviction| intent for the "
                        "same symbol was kept instead",
                    )
                )

    survivors.sort(key=_conviction_sort_key, reverse=True)

    approved = []
    rejected = []
    for intent in survivors:
        entry_price = intent.limit_price if intent.limit_price is not None else context.market_data.get_mark_price(intent.symbol).price
        volatility = volatility_by_symbol.get(intent.symbol) if volatility_by_symbol else None
        try:
            trade_request = size_intent(
                intent,
                equity=context.portfolio_snapshot.equity,
                risk_profile=risk_profile,
                current_price=entry_price,
                maintenance_margin_rate=maintenance_margin_rate,
                target_leverage=target_leverage,
                volatility=volatility,
            )
        except SizingError as exc:
            skipped.append(SkippedIntent(intent, f"sizing failed: {exc}"))
            continue

        funding_rate = context.market_data.get_funding_rate(intent.symbol)
        funding_info = FundingInfo(
            symbol=intent.symbol, funding_rate=funding_rate.rate, as_of_utc=funding_rate.timestamp_utc,
        )

        decision = risk_manager.evaluate(
            trade_request=trade_request,
            risk_profile=risk_profile,
            evaluated_at_utc=context.evaluated_at_utc,
            kill_switch_state=context.kill_switch_state,
            portfolio_snapshot=context.portfolio_snapshot,
            open_positions=context.open_positions,
            capabilities=capabilities,
            funding_info=funding_info,
            correlation_info=correlation_info,
        )

        if decision.decision is Decision.APPROVED:
            approved.append(trade_request)
        else:
            rejected.append(RejectedTrade(intent=intent, trade_request=trade_request, decision=decision))

    return ConstructionResult(approved=tuple(approved), rejected=tuple(rejected), skipped=tuple(skipped))
