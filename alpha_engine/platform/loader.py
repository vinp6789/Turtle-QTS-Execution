"""config/strategies.toml -> Tuple[Strategy, ...].

REUSES the tomllib idiom config/loader.py already uses. It does NOT reuse
load_config(): that returns a frozen EngineConfig (Module 1) which has no
strategy section and must not grow one. Strategy selection is a PRODUCT
concern and lives in its own file, outside the frozen boundary.

DISABLED IS THE DEFAULT-SAFE READING. A malformed or absent `enabled`
flag loads nothing; a strategy trades only because someone wrote
enabled = true.

FAILS LOUDLY, NEVER PARTIALLY. An unknown plugin name or a factory that
raises aborts the whole load. A half-loaded strategy set would mean the
engine silently trades a different book than the operator configured.
"""

import tomllib
from pathlib import Path
from typing import List, Mapping, Optional, Tuple

from trading_system.strategy import Strategy

from .registry import PluginEntry, get_plugin


class StrategyLoadError(Exception):
    """Configuration names a plugin that cannot be built. Never partial."""


def load_strategies(
    path="config/strategies.toml", *, required: bool = False,
) -> Tuple[Tuple[Strategy, ...], Tuple[PluginEntry, ...]]:
    """Returns (strategies, entries) for every ENABLED plugin, in file order.

    `entries` is returned alongside so a caller can log or expose each
    plugin's kind and warning without re-reading the registry.

    A missing file yields an empty tuple unless `required` -- booting with
    no strategies is a legitimate state (it is what the engine did before
    this module existed), not an error.
    """
    p = Path(path)
    if not p.is_file():
        if required:
            raise StrategyLoadError(f"strategy configuration not found: {p}")
        return (), ()

    try:
        with p.open("rb") as fh:
            raw = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise StrategyLoadError(f"{p} is not valid TOML: {exc}") from exc

    blocks = raw.get("strategies", [])
    if not isinstance(blocks, list):
        raise StrategyLoadError(
            f"{p}: [[strategies]] must be an array of tables, got {type(blocks).__name__}")

    strategies: List[Strategy] = []
    entries: List[PluginEntry] = []
    seen = set()
    for i, block in enumerate(blocks):
        if not isinstance(block, dict):
            raise StrategyLoadError(f"{p}: strategies[{i}] must be a table")
        name = block.get("name")
        if not isinstance(name, str) or not name.strip():
            raise StrategyLoadError(f"{p}: strategies[{i}] has no valid 'name'")
        if name in seen:
            raise StrategyLoadError(
                f"{p}: strategy {name!r} is configured twice -- one entry per plugin")
        seen.add(name)
        if block.get("enabled") is not True:      # default-safe: only literal true enables
            continue
        try:
            entry = get_plugin(name)
        except KeyError as exc:
            raise StrategyLoadError(str(exc)) from None
        params: Mapping = block.get("params", {}) or {}
        if not isinstance(params, dict):
            raise StrategyLoadError(f"{p}: strategies[{i}].params must be a table")
        try:
            strategies.append(entry.build(params))
        except StrategyLoadError:
            raise
        except Exception as exc:
            raise StrategyLoadError(
                f"{p}: plugin {name!r} failed to build: {type(exc).__name__}: {exc}"
            ) from exc
        entries.append(entry)

    return tuple(strategies), tuple(entries)


def describe(entries: Tuple[PluginEntry, ...]) -> str:
    """One human-readable line per loaded plugin, warnings included."""
    if not entries:
        return "no strategies enabled -- the engine will run cycles and trade nothing"
    return "\n".join(
        f"  {e.name}  [{e.kind.value}]  {e.warning or e.description}" for e in entries)
