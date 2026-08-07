"""The explicit, enumerable map of every runtime strategy plugin.

MIRRORS alpha_engine.candidates.catalog BY DESIGN, and for the same
stated reasons: entries are registered here explicitly, in source, at
import time -- no filesystem scanning, no entry-point magic, no runtime
registration API. Determinism and reviewability beat convenience.

NOTHING IS SPECIAL-CASED. The engine-test plugin loads through exactly
the path every future alpha strategy will use. `kind` is METADATA that
travels with an entry (surfaced in logs and API responses); the loader
branches on it nowhere. Deleting the engine-test plugin later is one
config edit and one registry line -- zero architectural work.
"""

from enum import Enum
from types import MappingProxyType
from typing import Callable, Mapping

from trading_system.strategy import Strategy


class PluginKind(Enum):
    """What a plugin IS -- never how it is loaded."""

    ALPHA = "alpha"
    """A governance-approved model. Capital may be allocated to it."""

    ENGINE_TEST = "engine_test"
    """A deterministic order generator that exists to exercise the
    pipeline. It is a unit test that happens to emit orders. It is NOT
    research: it never appears in the Alpha Library, Research Ledger, a
    campaign, the Mechanism Atlas or any scorecard, and no governance
    decision is required to enable it."""


class PluginEntry:
    """One registered plugin. Immutable."""

    __slots__ = ("name", "kind", "factory", "description", "warning")

    def __init__(self, name, kind, factory, description, warning=""):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("plugin name must be a non-empty string")
        if not isinstance(kind, PluginKind):
            raise ValueError("plugin kind must be a PluginKind")
        if not callable(factory):
            raise ValueError("plugin factory must be callable")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "factory", factory)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "warning", warning)

    def __setattr__(self, *_):
        raise AttributeError("PluginEntry is immutable")

    def build(self, params: Mapping) -> Strategy:
        strategy = self.factory(params)
        if not isinstance(strategy, Strategy):
            raise ValueError(
                f"plugin {self.name!r} factory returned {type(strategy).__name__}, "
                f"not a trading_system.strategy.Strategy"
            )
        return strategy


def _build_pipeline_validation(params: Mapping) -> Strategy:
    """The engine-test plugin: the EMA+MACD+ATR specification the research
    gate REJECTED on 2026-08-06 (hit rate 0.4353 vs a 0.55 bar, z = -3.5).

    It is used here ONLY because it emits genuine, deterministic
    TradeIntents, which is what exercising an order lifecycle requires.
    It is EXPECTED TO LOSE. Success for this plugin is zero crashes, zero
    duplicate orders, correct reconciliation and clean restart recovery --
    never PnL.

    Constructed with registry=None so governance is not involved and
    cannot be implied.
    """
    from exchange_adapter import Symbol

    from alpha_engine.candidates import trend_momentum_candidate_specification
    from alpha_engine.execution_bridge import ApprovedCandleAlphaStrategy
    from alpha_engine.watchlist import Watchlist

    symbols = tuple(Symbol(s) for s in params.get("symbols", ("BTC", "ETH", "SOL")))
    spec = trend_momentum_candidate_specification(
        version=str(params.get("version", "pipeline-validation-v1")),
        universe=symbols,
        cadence_seconds=int(params.get("cadence_seconds", 3600)),
        parameters={
            "threshold": str(params.get("threshold", "0.40")),
            "direction_convention": str(params.get("direction_convention", "momentum")),
            "atr_stop_mult": str(params.get("atr_stop_mult", "2.0")),
            "atr_t1_mult": str(params.get("atr_t1_mult", "3.0")),
            "atr_t2_mult": str(params.get("atr_t2_mult", "4.0")),
        },
        acceptance_criteria={"min_hit_rate": 0.55, "min_signaled_samples": 100},
    )
    return ApprovedCandleAlphaStrategy(
        (spec,), registry=None,
        watchlist=Watchlist(name="pipeline-validation", symbols=symbols),
    )


STRATEGY_REGISTRY = MappingProxyType({
    "pipeline_validation": PluginEntry(
        name="pipeline_validation",
        kind=PluginKind.ENGINE_TEST,
        factory=_build_pipeline_validation,
        description="Deterministic order generator that exercises the full pipeline.",
        warning="PIPELINE VALIDATION STRATEGY -- NOT FOR TRADING -- KNOWN NEGATIVE EXPECTANCY",
    ),
})


def get_plugin(name: str) -> PluginEntry:
    """The registered entry, or a KeyError naming every available plugin."""
    try:
        return STRATEGY_REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"unknown strategy plugin {name!r}; registered: "
            f"{sorted(STRATEGY_REGISTRY)}"
        ) from None
