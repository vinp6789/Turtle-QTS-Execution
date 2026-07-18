"""Hyperliquid /exchange action construction + hashing (Module 10, WP-8).

Builds the venue-native action dicts (order, cancel, modify), serializes
them with msgpack in the EXACT field order Hyperliquid's server re-encodes,
and computes the connectionId = keccak(msgpack(action) + nonce + vault)
that the phantom-agent EIP-712 signature is taken over.

Correctness is capital-critical: the server independently recomputes the
hash from the action it receives, so the msgpack field order and value
types here must match the venue's expectation byte-for-byte, or a valid
signature will not correspond to the transmitted action. The construction
mirrors the official hyperliquid-python-sdk (utils/signing.py); the test
suite validates the produced bytes/hash against a reconstruction of it.

DEPENDENCIES: msgpack + keccak (via eth_hash, bundled with eth-account),
both mutation-only. This module is imported only from the adapter's
_transmit_* hooks, never at package/read-only import time.
"""

from decimal import Decimal
from typing import List, Optional, Sequence, Tuple

from exchange_adapter import ExchangeAdapterError, ExchangeRejectedOrderError, TimeInForce

try:
    import msgpack as _msgpack
    from eth_utils import keccak as _keccak
    _IMPORT_ERROR = None
except ImportError as _exc:  # pragma: no cover
    _msgpack = None
    _keccak = None
    _IMPORT_ERROR = _exc

# frozen TimeInForce -> Hyperliquid tif. FOK has no Hyperliquid equivalent
# (capabilities declares supports_fok=False), so it is rejected upfront.
_TIF_WIRE = {
    TimeInForce.GTC: "Gtc",
    TimeInForce.IOC: "Ioc",
    TimeInForce.POST_ONLY: "Alo",
}


def _require_deps() -> None:
    if _msgpack is None or _keccak is None:
        raise ExchangeAdapterError(
            f"msgpack and eth-account are required for Hyperliquid mutation signing "
            f"but are not both installed ({_IMPORT_ERROR})."
        )


def tif_wire(time_in_force: TimeInForce) -> str:
    wire = _TIF_WIRE.get(time_in_force)
    if wire is None:
        raise ExchangeRejectedOrderError(
            f"Hyperliquid does not support time_in_force={time_in_force.value} "
            "(see DEFAULT_HYPERLIQUID_CAPABILITIES)"
        )
    return wire


def to_wire(value: Decimal) -> str:
    """Format a Decimal as Hyperliquid's wire string: fixed-point, no
    exponent, no trailing zeros (matches the SDK's float_to_wire output for
    equal values). Because the frozen models carry exact Decimals, this is
    exact -- no float round-trip."""
    if not isinstance(value, Decimal):
        raise ExchangeAdapterError(f"wire value must be Decimal, got {type(value).__name__}")
    normalized = value.normalize()
    # Decimal.normalize() can yield exponent form (e.g. 5E+4); 'f' forces
    # plain fixed-point notation ("50000").
    text = format(normalized, "f")
    # Guard against "-0" for a zero value.
    return "0" if text in ("-0", "-0.0") else text


def build_order_wire(
    asset_index: int,
    is_buy: bool,
    price: Decimal,
    size: Decimal,
    reduce_only: bool,
    tif: str,
    cloid: Optional[str] = None,
) -> dict:
    wire = {
        "a": asset_index,
        "b": is_buy,
        "p": to_wire(price),
        "s": to_wire(size),
        "r": reduce_only,
        "t": {"limit": {"tif": tif}},
    }
    if cloid is not None:
        wire["c"] = cloid
    return wire


def build_order_action(order_wires: Sequence[dict]) -> dict:
    return {"type": "order", "orders": list(order_wires), "grouping": "na"}


def build_cancel_action(cancels: Sequence[Tuple[int, int]]) -> dict:
    """cancels: sequence of (asset_index, oid)."""
    return {"type": "cancel", "cancels": [{"a": a, "o": o} for a, o in cancels]}


def build_modify_action(oid: int, order_wire: dict) -> dict:
    return {"type": "modify", "oid": oid, "order": order_wire}


def connection_id(action: dict, nonce: int, vault_address: Optional[str] = None) -> bytes:
    """keccak(msgpack(action) + nonce(8 bytes big-endian) + vault marker).
    This is the 32-byte hash the phantom-agent EIP-712 signature is over."""
    _require_deps()
    if not isinstance(nonce, int) or isinstance(nonce, bool) or nonce <= 0:
        raise ExchangeAdapterError("nonce must be a positive int")
    data = _msgpack.packb(action)
    data += nonce.to_bytes(8, "big")
    if vault_address is None:
        data += b"\x00"
    else:
        hexpart = vault_address[2:] if vault_address.startswith("0x") else vault_address
        data += b"\x01" + bytes.fromhex(hexpart)
    return _keccak(data)
