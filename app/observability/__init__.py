"""Observability: structured logging + Prometheus-format metrics.

Public API:
    configure_logging(level, fmt) -- set up stdout JSON/text logging
    log_event(logger, level, msg, **fields) -- structured log record
    render_metrics(state) -- Prometheus text exposition for GET /metrics
"""

from .logging import configure_logging, log_event
from .metrics import render_metrics

__all__ = ["configure_logging", "log_event", "render_metrics"]
