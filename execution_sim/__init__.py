"""Simulated execution: real market data, deterministic local fills.

PERMANENT PLATFORM INFRASTRUCTURE (Track B, Product). Deliberately a
TOP-LEVEL package and NOT part of alpha_engine: it imports the frozen
hyperliquid_adapter transport, which Constitution Section 4 forbids the
Alpha Engine from doing. tests/test_alpha_engine_scaffold.py enforces
that boundary, and it caught this module in the wrong package -- the
guardrail working exactly as intended.

The separation is also correct on the merits. Alpha Engine answers "is
this hypothesis supported?". This package answers "what would the venue
have done?". Different question, different lifecycle, different track.
"""

from .transport import MAKER_FEE_RATE, TAKER_FEE_RATE, SimulatedTransport

__all__ = ["SimulatedTransport", "TAKER_FEE_RATE", "MAKER_FEE_RATE"]
