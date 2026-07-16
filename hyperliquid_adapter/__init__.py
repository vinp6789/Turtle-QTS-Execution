"""Concrete Hyperliquid Exchange Adapter (Module 10).

Implements the frozen Module 5 ExchangeAdapter contract for the
Hyperliquid venue. A concrete adapter owns venue transport, translation
of native venue shapes into Module 5's typed models, venue error mapping
into Module 5's closed error hierarchy, and venue request signing (via
Module 2's SigningBoundary only -- never raw key material). It owns no
business logic: it never decides whether, when, or how much to trade.

Depends only on lower-numbered frozen modules: exchange_adapter (5) and,
once the adapter class lands, secrets_boundary (2).

Build state: capability declaration only. The adapter class, codec,
transport, and signing are not present yet.

Public API:
    DEFAULT_HYPERLIQUID_CAPABILITIES -- vetted default capability set
"""

from .capabilities import DEFAULT_HYPERLIQUID_CAPABILITIES

__all__ = [
    "DEFAULT_HYPERLIQUID_CAPABILITIES",
]
