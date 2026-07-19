"""Result types for portfolio construction. Every candidate TradeIntent's
fate is traceable in exactly one of ConstructionResult's three
collections -- nothing is silently dropped."""

from dataclasses import dataclass
from typing import Tuple

from risk_manager import RiskDecision, TradeRequest

from ..strategy import TradeIntent


@dataclass(frozen=True)
class SkippedIntent:
    """A TradeIntent that never reached RiskManager at all: excluded by
    portfolio-level filtering (out of universe, deduplicated against a
    higher-conviction same-symbol intent) or because sizing itself could
    not responsibly produce a TradeRequest (see trading_system.sizing.
    SizingError)."""

    intent: TradeIntent
    reason: str


@dataclass(frozen=True)
class RejectedTrade:
    """A TradeIntent that WAS sized and evaluated, but RiskManager did not
    return APPROVED. decision.reason_codes/violated_limits carry the full
    explanation -- this wrapper only adds back the originating intent."""

    intent: TradeIntent
    trade_request: TradeRequest
    decision: RiskDecision


@dataclass(frozen=True)
class ConstructionResult:
    approved: Tuple[TradeRequest, ...]
    rejected: Tuple[RejectedTrade, ...]
    skipped: Tuple[SkippedIntent, ...]
