"""Phase 2 tests: base_url<->is_mainnet consistency enforcement, and
asset-index cache invalidation. Requires eth-account (signer); the cache
tests use a fake transport only.
"""

import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from event_store import EventStore
from secrets_boundary import EnvironmentHmacBackend, SigningBoundary

from exchange_adapter import (
    ExchangeRejectedOrderError,
    OrderRequest,
    OrderSide,
    OrderType,
    Symbol,
    TimeInForce,
)

from hyperliquid_adapter import HttpResponse, HyperliquidAdapter
from hyperliquid_adapter.transport import MAINNET_BASE_URL, TESTNET_BASE_URL

try:
    from hyperliquid_adapter.signing import HyperliquidWalletSigner
    _HAVE = True
except ImportError:
    _HAVE = False

SIGNING_REF = "hyperliquid_signing_key_v1"
WALLET_REF = "hyperliquid_wallet_key_v1"
ACCOUNT = "0x1111111111111111111111111111111111111111"
WALLET_ENV = {"TURTLE_SECRET_HYPERLIQUID_WALLET_KEY_V1": "0x" + "55" * 32}


def _boundary():
    return SigningBoundary([SIGNING_REF], "1.0.0", "hyperliquid",
                           backend=EnvironmentHmacBackend(env={"TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1": "m"}))


def _signer(is_mainnet):
    return HyperliquidWalletSigner(WALLET_REF, is_mainnet=is_mainnet, env=WALLET_ENV)


@unittest.skipUnless(_HAVE, "eth-account not installed")
class NetworkConsistency(unittest.TestCase):
    def test_mainnet_signer_with_mainnet_url_ok(self):
        HyperliquidAdapter(_boundary(), SIGNING_REF, ACCOUNT, wallet_signer=_signer(True), base_url=MAINNET_BASE_URL)

    def test_testnet_signer_with_testnet_url_ok(self):
        HyperliquidAdapter(_boundary(), SIGNING_REF, ACCOUNT, wallet_signer=_signer(False), base_url=TESTNET_BASE_URL)

    def test_testnet_signer_with_mainnet_url_rejected(self):
        with self.assertRaises(ValueError):
            HyperliquidAdapter(_boundary(), SIGNING_REF, ACCOUNT, wallet_signer=_signer(False), base_url=MAINNET_BASE_URL)

    def test_mainnet_signer_with_testnet_url_rejected(self):
        with self.assertRaises(ValueError):
            HyperliquidAdapter(_boundary(), SIGNING_REF, ACCOUNT, wallet_signer=_signer(True), base_url=TESTNET_BASE_URL)

    def test_custom_url_is_not_enforced(self):
        # An unrecognized base_url cannot be inferred; construction is allowed.
        HyperliquidAdapter(_boundary(), SIGNING_REF, ACCOUNT, wallet_signer=_signer(False),
                           base_url="https://my-proxy.example")

    def test_no_signer_no_enforcement(self):
        # Read-only adapter (no signer) is unaffected by network checks.
        HyperliquidAdapter(_boundary(), SIGNING_REF, ACCOUNT, base_url=MAINNET_BASE_URL)


class _CountingTransport:
    """Serves /info; counts how many times `meta` was fetched, and lets the
    served universe be swapped to simulate a newly-listed asset."""

    def __init__(self, universe):
        self.universe = universe
        self.meta_fetches = 0

    def __call__(self, url, payload, timeout):
        t = payload["type"]
        if t == "meta":
            self.meta_fetches += 1
            return HttpResponse(200, {"universe": self.universe})
        if t == "allMids":
            return HttpResponse(200, {"BTC": "50000"})
        raise AssertionError(f"unexpected info type {t}")


@unittest.skipUnless(_HAVE, "eth-account not installed")
class AssetIndexCacheInvalidation(unittest.TestCase):
    def _adapter(self, transport):
        a = HyperliquidAdapter(_boundary(), SIGNING_REF, ACCOUNT, transport=transport,
                               wallet_signer=_signer(False), base_url=TESTNET_BASE_URL)
        a.connect()
        return a

    def test_index_is_cached_after_first_lookup(self):
        t = _CountingTransport([{"name": "BTC"}, {"name": "ETH"}])
        a = self._adapter(t)
        self.assertEqual(a._asset_index(Symbol("BTC")), 0)
        self.assertEqual(a._asset_index(Symbol("ETH")), 1)
        self.assertEqual(t.meta_fetches, 1)  # one fetch served both

    def test_unknown_symbol_triggers_one_refresh_then_resolves(self):
        # SOL is not in the initial universe; it appears after listing. The
        # stale-cache auto-refresh must pick it up without an adapter restart.
        t = _CountingTransport([{"name": "BTC"}])
        a = self._adapter(t)
        self.assertEqual(a._asset_index(Symbol("BTC")), 0)  # fetch #1
        t.universe = [{"name": "BTC"}, {"name": "SOL"}]      # venue lists SOL
        self.assertEqual(a._asset_index(Symbol("SOL")), 1)  # miss -> refresh (fetch #2) -> resolves
        self.assertEqual(t.meta_fetches, 2)

    def test_truly_unknown_symbol_raises_after_refresh(self):
        t = _CountingTransport([{"name": "BTC"}])
        a = self._adapter(t)
        with self.assertRaises(ExchangeRejectedOrderError):
            a._asset_index(Symbol("NOPE"))
        self.assertEqual(t.meta_fetches, 1 + 1)  # initial + one refresh attempt

    def test_manual_refresh_forces_refetch(self):
        t = _CountingTransport([{"name": "BTC"}])
        a = self._adapter(t)
        a._asset_index(Symbol("BTC"))       # fetch #1
        a.refresh_asset_index()
        a._asset_index(Symbol("BTC"))       # fetch #2 (cache was cleared)
        self.assertEqual(t.meta_fetches, 2)


if __name__ == "__main__":
    unittest.main()
