"""Product platform: how a Strategy gets from configuration into the engine.

Deliberately separate from alpha_engine.candidates. That catalog names
RESEARCH candidate families (feature + evaluate_fn + specification
factory). This names RUNTIME plugins (trading_system.strategy.Strategy
instances). Same design philosophy -- explicit, enumerable, registered in
source -- different objects and different lifecycles.
"""

from .loader import StrategyLoadError, describe, load_strategies
from .registry import STRATEGY_REGISTRY, PluginEntry, PluginKind, get_plugin

__all__ = [
    "STRATEGY_REGISTRY", "PluginEntry", "PluginKind", "get_plugin",
    "load_strategies", "StrategyLoadError", "describe",
]
