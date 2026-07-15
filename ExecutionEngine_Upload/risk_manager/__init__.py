"""Risk Manager for the Turtle Execution Engine.

A pure approval/veto module: given a fully-specified proposed trade and
already-computed inputs from other frozen modules, determines whether
the trade is permitted. Never generates signals, computes conviction,
calculates indicators, sizes positions, or submits requests. Pure,
deterministic, side-effect-free -- no filesystem, no network, no
randomness, no wall-clock access, no persistence.

Public API:
    RiskManager(limits)
    RiskManagerLimits, TradeRequest, FundingInfo, CorrelationInfo, CorrelationEntry
    Decision, ReasonCode, RiskDecision
    CORRELATION_THRESHOLD
"""

from .errors import RiskManagerConfigurationError, RiskManagerError
from .manager import RiskManager
from .models import (
    CORRELATION_THRESHOLD,
    CorrelationEntry,
    CorrelationInfo,
    Decision,
    FundingInfo,
    ReasonCode,
    RiskDecision,
    RiskManagerLimits,
    TradeRequest,
)

__all__ = [
    "RiskManager",
    "RiskManagerLimits",
    "TradeRequest",
    "FundingInfo",
    "CorrelationInfo",
    "CorrelationEntry",
    "Decision",
    "ReasonCode",
    "RiskDecision",
    "CORRELATION_THRESHOLD",
    "RiskManagerError",
    "RiskManagerConfigurationError",
]
