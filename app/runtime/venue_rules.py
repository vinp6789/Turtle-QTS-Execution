"""Fetches Hyperliquid per-asset quantization rules (szDecimals) from the
venue's public `meta` endpoint (C2 fix).

Uses ONLY public seams of the frozen hyperliquid_adapter package: the
TransportFn callable type and its default `post_json` (both exported by
hyperliquid_adapter/__init__), against the same base URLs composition_root
already selects by network. No frozen module is modified and no private
attribute of any adapter instance is read.

Fail-fast contract: malformed metadata raises immediately with a clear
error. A live engine must NEVER trade without complete quantization rules
-- transmitting unquantized orders is a guaranteed venue rejection for
arbitrary sizes (audit finding C2) -- so a metadata problem is a startup
configuration failure, not something to paper over. Refresh is a plain
re-call of fetch_hyperliquid_rules(): the returned mapping is immutable
(MappingProxyType), so swapping to a freshly fetched mapping is a single
atomic rebind that concurrent readers can never observe half-updated.
"""

from types import MappingProxyType
from typing import Optional

from hyperliquid_adapter import TransportFn, post_json

from trading_system.execution import PRICE_MAX_DECIMALS, QuantizationRules, SymbolRules

_DEFAULT_TIMEOUT_SECONDS = 10.0


def fetch_hyperliquid_rules(
    base_url: str,
    transport: Optional[TransportFn] = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
) -> QuantizationRules:
    """Returns an immutable mapping of symbol -> SymbolRules for every
    asset in the venue universe (delisted entries included -- rules for a
    symbol nobody trades are harmless; a MISSING symbol fails closed at
    execution time instead). Raises ValueError on any malformed metadata."""
    send = post_json if transport is None else transport
    response = send(f"{base_url}/info", {"type": "meta"}, timeout_seconds)
    body = response.body
    if not isinstance(body, dict) or not isinstance(body.get("universe"), list) or not body["universe"]:
        raise ValueError(
            f"malformed Hyperliquid meta response from {base_url!r}: expected a "
            "non-empty 'universe' list -- refusing to build quantization rules"
        )

    rules = {}
    for index, asset in enumerate(body["universe"]):
        if not isinstance(asset, dict):
            raise ValueError(f"malformed meta universe entry #{index}: not an object")
        name = asset.get("name")
        sz_decimals = asset.get("szDecimals")
        if not isinstance(name, str) or not name:
            raise ValueError(f"malformed meta universe entry #{index}: missing asset name")
        if not isinstance(sz_decimals, int) or isinstance(sz_decimals, bool) \
                or not (0 <= sz_decimals <= PRICE_MAX_DECIMALS):
            raise ValueError(
                f"malformed meta universe entry #{index} ({name!r}): szDecimals={sz_decimals!r} "
                f"is not an int in [0, {PRICE_MAX_DECIMALS}]"
            )
        rules[name] = SymbolRules(sz_decimals=sz_decimals)
    return MappingProxyType(rules)
