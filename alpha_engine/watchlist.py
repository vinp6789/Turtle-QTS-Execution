"""Watchlist: the configurable symbol universe the Alpha Engine operates
on (Alpha Engine R4; system objective "generate alpha only from a
configurable watchlist").

A Watchlist is a named, immutable, ordered tuple of unique Symbols,
loadable from a small JSON file:

    {"name": "core-perps", "symbols": ["BTC", "ETH", "SOL"]}

Design points:
  - Ordered and duplicate-free, preserving file order: deterministic
    iteration for every consumer (research batching, spec construction).
  - The watchlist constrains WHAT gets researched/traded: candidate
    specifications are built with universe = watchlist symbols (or a
    subset), so nothing downstream ever scans arbitrary assets. This
    module does not itself fetch anything.
  - Plain stdlib json + explicit validation; a malformed file fails
    loudly at load time (configuration error), never silently truncates
    or coerces.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple, Union

from exchange_adapter import Symbol


class WatchlistError(Exception):
    """Raised for an invalid Watchlist construction or a malformed
    watchlist file."""


@dataclass(frozen=True)
class Watchlist:
    name: str
    symbols: Tuple[Symbol, ...]

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise WatchlistError("Watchlist.name must be a non-empty string")
        if not isinstance(self.symbols, tuple) or len(self.symbols) == 0:
            raise WatchlistError("Watchlist.symbols must be a non-empty tuple")
        if not all(isinstance(s, Symbol) for s in self.symbols):
            raise WatchlistError("Watchlist.symbols must contain only Symbol instances")
        values = [s.value for s in self.symbols]
        if len(set(values)) != len(values):
            duplicates = sorted({v for v in values if values.count(v) > 1})
            raise WatchlistError(f"Watchlist.symbols contains duplicates: {duplicates}")

    def __contains__(self, symbol: Symbol) -> bool:
        return isinstance(symbol, Symbol) and any(s.value == symbol.value for s in self.symbols)

    def __len__(self) -> int:
        return len(self.symbols)


def load_watchlist(path: Union[str, Path]) -> Watchlist:
    """Loads and validates a watchlist JSON file. Raises WatchlistError
    on a missing file, invalid JSON, or a shape/content violation."""
    file_path = Path(path)
    if not file_path.is_file():
        raise WatchlistError(f"watchlist file not found: {file_path}")
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WatchlistError(f"watchlist file {file_path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise WatchlistError(f"watchlist file {file_path} must contain a JSON object")
    name = raw.get("name")
    symbols_raw = raw.get("symbols")
    if not isinstance(name, str) or not name.strip():
        raise WatchlistError(f"watchlist file {file_path}: 'name' must be a non-empty string")
    if not isinstance(symbols_raw, list) or len(symbols_raw) == 0:
        raise WatchlistError(f"watchlist file {file_path}: 'symbols' must be a non-empty list")
    if not all(isinstance(s, str) and s.strip() for s in symbols_raw):
        raise WatchlistError(f"watchlist file {file_path}: every symbol must be a non-empty string")
    return Watchlist(name=name, symbols=tuple(Symbol(s) for s in symbols_raw))
