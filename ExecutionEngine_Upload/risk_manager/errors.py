"""Exceptions raised by the Risk Manager.

Reserved exclusively for programmer or configuration errors -- a
malformed RiskManagerLimits, a wrong-typed argument, an internal
inconsistency. Ordinary business-rule failures (heat exceeded,
insufficient margin, kill switch active, missing market data, ...) are
never exceptions; they are RiskDecision outcomes (REJECTED / BLOCKED /
FAIL_SAFE), returned normally.
"""


class RiskManagerError(Exception):
    """Base exception for all Risk Manager programmer/configuration errors."""


class RiskManagerConfigurationError(RiskManagerError):
    """Raised when RiskManagerLimits or another configuration input is
    malformed -- negative limits, out-of-range fractions, wrong types.
    Never raised for a trade that simply fails a valid limit."""
