"""Errors for the reporting layer."""

from ..errors import TradingSystemError


class ReportingError(TradingSystemError):
    """Base for every reporting failure -- raised only for a wrong-type
    argument. Reporting performs no computation of its own beyond string
    formatting, so there is no other failure mode to represent."""
