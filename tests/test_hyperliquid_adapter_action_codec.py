"""Tests for hyperliquid_adapter.action_codec (WP-8).

Validates action construction, Decimal->wire formatting, and msgpack/hash
byte-for-byte against a reconstruction of the official hyperliquid-python-sdk
signing construction. Requires msgpack + eth-account (skipped if absent).
"""

import unittest
from decimal import Decimal

try:
    import msgpack
    from eth_utils import keccak
    _HAVE = True
except ImportError:
    _HAVE = False

from exchange_adapter import ExchangeRejectedOrderError, TimeInForce

if _HAVE:
    from hyperliquid_adapter import action_codec


# ---- official SDK reconstruction (utils/signing.py) ----
def _sdk_float_to_wire(x):
    rounded = "%.8f" % x
    n = Decimal(rounded).normalize()
    return f"{n:f}"


def _sdk_order_wire(asset, is_buy, px, sz, ro, tif, cloid=None):
    w = {"a": asset, "b": is_buy, "p": _sdk_float_to_wire(px), "s": _sdk_float_to_wire(sz),
         "r": ro, "t": {"limit": {"tif": tif}}}
    if cloid is not None:
        w["c"] = cloid
    return w


def _sdk_hash(action, nonce, vault=None):
    data = msgpack.packb(action) + nonce.to_bytes(8, "big") + (b"\x00" if vault is None else b"\x01" + bytes.fromhex(vault[2:]))
    return keccak(data)


@unittest.skipUnless(_HAVE, "msgpack/eth-account not installed")
class WireFormatting(unittest.TestCase):
    def test_strips_trailing_zeros_and_exponent(self):
        self.assertEqual(action_codec.to_wire(Decimal("50000.0")), "50000")
        self.assertEqual(action_codec.to_wire(Decimal("0.0335")), "0.0335")
        self.assertEqual(action_codec.to_wire(Decimal("1.10")), "1.1")
        self.assertEqual(action_codec.to_wire(Decimal("1E+2")), "100")

    def test_matches_sdk_for_representable_values(self):
        for v in ["29792.0", "5.0", "0.001", "12345", "0.5"]:
            self.assertEqual(action_codec.to_wire(Decimal(v)), _sdk_float_to_wire(float(v)))


@unittest.skipUnless(_HAVE, "msgpack/eth-account not installed")
class TifMapping(unittest.TestCase):
    def test_gtc_ioc_alo(self):
        self.assertEqual(action_codec.tif_wire(TimeInForce.GTC), "Gtc")
        self.assertEqual(action_codec.tif_wire(TimeInForce.IOC), "Ioc")
        self.assertEqual(action_codec.tif_wire(TimeInForce.POST_ONLY), "Alo")

    def test_fok_rejected(self):
        with self.assertRaises(ExchangeRejectedOrderError):
            action_codec.tif_wire(TimeInForce.FOK)


@unittest.skipUnless(_HAVE, "msgpack/eth-account not installed")
class ByteForByteVsSdk(unittest.TestCase):
    def test_order_action_msgpack_and_hash_match_sdk(self):
        cloid = "0x" + "ab" * 16
        mine_wire = action_codec.build_order_wire(3, True, Decimal("29792.0"), Decimal("5.0"), False, "Gtc", cloid)
        mine_action = action_codec.build_order_action([mine_wire])
        sdk_action = {"type": "order", "orders": [_sdk_order_wire(3, True, 29792.0, 5.0, False, "Gtc", cloid)], "grouping": "na"}
        self.assertEqual(msgpack.packb(mine_action), msgpack.packb(sdk_action))
        self.assertEqual(action_codec.connection_id(mine_action, 1700000000000),
                         _sdk_hash(sdk_action, 1700000000000))

    def test_cancel_action_hash_matches_sdk(self):
        mine = action_codec.build_cancel_action([(1, 999), (2, 1000)])
        sdk = {"type": "cancel", "cancels": [{"a": 1, "o": 999}, {"a": 2, "o": 1000}]}
        self.assertEqual(msgpack.packb(mine), msgpack.packb(sdk))
        self.assertEqual(action_codec.connection_id(mine, 42), _sdk_hash(sdk, 42))

    def test_wire_field_order_is_exact(self):
        w = action_codec.build_order_wire(0, False, Decimal("1"), Decimal("2"), True, "Ioc", "0x" + "00" * 16)
        self.assertEqual(list(w.keys()), ["a", "b", "p", "s", "r", "t", "c"])

    def test_cloid_omitted_when_none(self):
        w = action_codec.build_order_wire(0, True, Decimal("1"), Decimal("2"), False, "Gtc", None)
        self.assertNotIn("c", w)


@unittest.skipUnless(_HAVE, "msgpack/eth-account not installed")
class ConnectionId(unittest.TestCase):
    def test_vault_marker_changes_hash(self):
        action = action_codec.build_cancel_action([(0, 1)])
        no_vault = action_codec.connection_id(action, 5, vault_address=None)
        with_vault = action_codec.connection_id(action, 5, vault_address="0x" + "11" * 20)
        self.assertNotEqual(no_vault, with_vault)

    def test_nonce_changes_hash(self):
        action = action_codec.build_cancel_action([(0, 1)])
        self.assertNotEqual(action_codec.connection_id(action, 1), action_codec.connection_id(action, 2))

    def test_non_positive_nonce_rejected(self):
        with self.assertRaises(Exception):
            action_codec.connection_id(action_codec.build_cancel_action([(0, 1)]), 0)


if __name__ == "__main__":
    unittest.main()
