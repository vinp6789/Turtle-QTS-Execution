"""Errors for portfolio signal selection."""


class PortfolioError(Exception):
    """Base for portfolio-layer failures (caller-error validation only;
    selection itself never raises for a signal's content -- conflicting
    or duplicate signals are resolved by policy, not by exception)."""
