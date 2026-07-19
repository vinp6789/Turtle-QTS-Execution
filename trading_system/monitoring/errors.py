"""Errors for the monitoring layer."""

from ..errors import TradingSystemError


class MonitoringError(TradingSystemError):
    """Base for every monitoring failure raised BY THIS MODULE itself (a
    wrong-type argument). Monitoring never catches or reinterprets a
    failure from anything it reads -- it propagates as-is. Monitoring
    itself never mutates anything and never raises to report "bad" engine
    state (e.g. disconnected, kill-switched) -- that is surfaced as data
    on EngineSnapshot, not as an exception."""
