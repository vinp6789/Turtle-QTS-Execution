"""Tests for DEFAULT_HYPERLIQUID_CAPABILITIES (Module 10, WP-1).

Each value is pinned to the decision recorded in ADR-22. These are not
cosmetic assertions: Risk Manager vetoes a trade whose requested feature
is not declared (risk_manager/manager.py::_capability_violation), so a
silent flip of any flag below changes trading outcomes.
"""

import dataclasses
import unittest

from exchange_adapter import ExchangeCapabilities

import hyperliquid_adapter
from hyperliquid_adapter import DEFAULT_HYPERLIQUID_CAPABILITIES


class CapabilityType(unittest.TestCase):
    def test_is_an_exchange_capabilities_instance(self):
        self.assertIsInstance(DEFAULT_HYPERLIQUID_CAPABILITIES, ExchangeCapabilities)

    def test_is_frozen(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            DEFAULT_HYPERLIQUID_CAPABILITIES.supports_market_orders = True

    def test_extra_is_empty_and_not_mutable(self):
        self.assertEqual(dict(DEFAULT_HYPERLIQUID_CAPABILITIES.extra), {})
        with self.assertRaises(TypeError):
            DEFAULT_HYPERLIQUID_CAPABILITIES.extra["supports_twap"] = True


class CapabilityValues(unittest.TestCase):
    """One test per field, pinned to ADR-22."""

    def test_supports_reduce_only_true(self):
        # Hyperliquid order schema carries "r" (reduceOnly) on every order.
        self.assertTrue(DEFAULT_HYPERLIQUID_CAPABILITIES.supports_reduce_only)

    def test_supports_post_only_true(self):
        # tif "Alo" (Add Liquidity Only) is post-only.
        self.assertTrue(DEFAULT_HYPERLIQUID_CAPABILITIES.supports_post_only)

    def test_supports_ioc_true(self):
        self.assertTrue(DEFAULT_HYPERLIQUID_CAPABILITIES.supports_ioc)

    def test_supports_fok_false(self):
        # tif enum is exactly Alo|Ioc|Gtc -- no FOK exists on Hyperliquid.
        self.assertFalse(DEFAULT_HYPERLIQUID_CAPABILITIES.supports_fok)

    def test_supports_market_orders_false(self):
        # ADR-22: no native market order; this adapter declines to emulate
        # with an adapter-internal slippage bound invisible to Risk Manager.
        self.assertFalse(DEFAULT_HYPERLIQUID_CAPABILITIES.supports_market_orders)

    def test_supports_limit_orders_true(self):
        self.assertTrue(DEFAULT_HYPERLIQUID_CAPABILITIES.supports_limit_orders)

    def test_supports_trigger_orders_false(self):
        # Unexpressible through the frozen interface (OrderType is only
        # MARKET|LIMIT; OrderRequest has no trigger price).
        self.assertFalse(DEFAULT_HYPERLIQUID_CAPABILITIES.supports_trigger_orders)

    def test_supports_partial_fill_notifications_false(self):
        # Push notifications require the websocket; this build is REST-only.
        self.assertFalse(DEFAULT_HYPERLIQUID_CAPABILITIES.supports_partial_fill_notifications)

    def test_supports_funding_rate_true(self):
        self.assertTrue(DEFAULT_HYPERLIQUID_CAPABILITIES.supports_funding_rate)

    def test_supports_cross_margin_true(self):
        self.assertTrue(DEFAULT_HYPERLIQUID_CAPABILITIES.supports_cross_margin)

    def test_supports_isolated_margin_true(self):
        self.assertTrue(DEFAULT_HYPERLIQUID_CAPABILITIES.supports_isolated_margin)


class PackageSurface(unittest.TestCase):
    def test_all_declares_exactly_the_public_names(self):
        self.assertEqual(hyperliquid_adapter.__all__, ["DEFAULT_HYPERLIQUID_CAPABILITIES"])

    def test_every_all_name_resolves(self):
        for name in hyperliquid_adapter.__all__:
            self.assertTrue(hasattr(hyperliquid_adapter, name), f"{name} in __all__ but not importable")


if __name__ == "__main__":
    unittest.main()
