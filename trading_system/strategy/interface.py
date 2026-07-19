"""The pluggable Strategy interface.

A Strategy decides WHAT to trade and expresses that as zero or more
TradeIntents -- nothing else. It never sizes a trade, never calls
RiskManager, never calls OrderManager, never touches an ExchangeAdapter
directly (it reads only through StrategyContext.market_data). This is the
entire contract a concrete strategy implements; no concrete strategy is
built in this milestone.
"""

from abc import ABC, abstractmethod
from typing import Tuple

from .models import StrategyContext, TradeIntent


class Strategy(ABC):
    """generate_intents must be a pure function of its context argument:
    no hidden state, no side effects, no I/O of its own beyond whatever
    StrategyContext.market_data already provides. The execution engine
    (composition_root + orchestration) is fully reusable across any
    Strategy implementation that honors this contract."""

    @property
    @abstractmethod
    def name(self) -> str:
        """A short, stable, human-readable identifier for this strategy.
        Stable across restarts for the same strategy configuration --
        future milestones (trading_system.execution) may use it to
        attribute an order back to the strategy that proposed it."""
        ...

    @abstractmethod
    def generate_intents(self, context: StrategyContext) -> Tuple[TradeIntent, ...]:
        """Return zero or more TradeIntents for the given context. An
        empty tuple means "no action this cycle" -- never raise merely to
        signal that there is nothing to do."""
        ...
