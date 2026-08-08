"""Records which strategy produced which TradeIntent, without touching a
frozen module.

THE PROBLEM. trading_system.scheduling.run_cycle pools every strategy's
intents into one flat tuple before portfolio construction, so by the time
a CycleResult exists the origin of each intent is gone. TradeIntent has no
strategy field and is frozen.

THE MECHANISM. TradeIntent instances are passed by REFERENCE all the way
through -- pooling, suppression filtering, construction, and into
RejectedTrade.intent / SkippedIntent.intent / CycleResult.intents. Nothing
reconstructs them. So this decorator delegates generate_intents() to the
real strategy and records id(intent) -> its metadata. The attribution
writer then joins on identity.

THIS IS PROVISIONAL AND TEST-ENFORCED. The identity assumption is verified
end-to-end by tests/test_attribution.py::TestIntentIdentitySurvivesPooling
against a real paper engine. If a future change ever copies a TradeIntent,
that test fails loudly rather than attribution silently degrading. The
correct response would be to request a strategy_id field on TradeIntent
under §9 -- NOT to patch around it here.

id() IS ONLY EVER USED WITHIN A SINGLE CYCLE, while the intent objects are
alive and reachable from CycleResult. It is never persisted, never
compared across cycles, and never treated as an identifier.
"""

from typing import Any, Dict, NamedTuple, Tuple

from trading_system.strategy import Strategy, StrategyContext, TradeIntent


class StrategyIdentity(NamedTuple):
    """What produced an intent. `kind` comes from the registry's
    PluginEntry, never from the strategy's name -- naming is not a
    classification mechanism."""

    strategy_id: str
    strategy_version: str
    strategy_kind: str


class AttributedStrategy(Strategy):
    """Wraps a Strategy, delegating everything and observing nothing else.

    It changes no behaviour: generate_intents returns exactly the tuple
    the wrapped strategy returned, with the same objects in the same
    order.
    """

    __slots__ = ("_inner", "_identity", "_by_intent_id")

    def __init__(self, inner: Strategy, identity: StrategyIdentity):
        if not isinstance(inner, Strategy):
            raise TypeError(f"inner must be a Strategy, got {type(inner).__name__}")
        if not isinstance(identity, StrategyIdentity):
            raise TypeError("identity must be a StrategyIdentity")
        self._inner = inner
        self._identity = identity
        self._by_intent_id: Dict[int, StrategyIdentity] = {}

    @property
    def name(self) -> str:
        return self._inner.name

    @property
    def inner(self) -> Strategy:
        return self._inner

    @property
    def identity(self) -> StrategyIdentity:
        return self._identity

    def generate_intents(self, context: StrategyContext) -> Tuple[TradeIntent, ...]:
        intents = self._inner.generate_intents(context)
        for intent in intents:
            self._by_intent_id[id(intent)] = self._identity
        return intents

    # -- read side, used only by the attribution writer, same cycle --

    def lookup(self, intent: TradeIntent):
        return self._by_intent_id.get(id(intent))

    def forget(self) -> None:
        """Drop the per-cycle map. Called after each cycle's attribution is
        written so this never grows without bound, and so an id() can
        never be reused across cycles by a recycled object address."""
        self._by_intent_id.clear()


def resolve(strategies, intent: TradeIntent) -> StrategyIdentity:
    """First wrapper claiming this intent, else an explicit UNATTRIBUTED
    marker. Never guesses, and never falls back to a name."""
    for s in strategies:
        if isinstance(s, AttributedStrategy):
            found = s.lookup(intent)
            if found is not None:
                return found
    return StrategyIdentity("UNATTRIBUTED", "", "UNKNOWN")


def forget_all(strategies) -> None:
    for s in strategies:
        if isinstance(s, AttributedStrategy):
            s.forget()
