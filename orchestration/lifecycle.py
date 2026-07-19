"""Coordinates engine startup/shutdown as a sequence of already-existing
operations -- distinct from composition_root.Engine.start()/stop(), which
perform the narrow one-time connect/disconnect handshake only (see
composition_root/engine.py). This module SEQUENCES that handshake with
the other coordination steps a live process needs immediately after
connecting (catch up any in-doubt orders, check local state against the
venue) and, on shutdown, simply disconnects -- it adds no new capability
beyond calling what composition_root and the two sibling coordination
modules already provide.
"""

from dataclasses import dataclass

from composition_root import Engine
from exchange_adapter import HealthStatus, ReconciliationReport
from order_manager import OrderSnapshot

from .reconciliation import reconcile
from .synchronization import synchronize


@dataclass(frozen=True)
class StartupReport:
    """Bundles the three outcomes of one startup sequence. Not persisted
    anywhere -- purely the caller's return value for logging/inspection."""

    health: HealthStatus
    resynced_orders: "tuple[OrderSnapshot, ...]"
    reconciliation: ReconciliationReport


def startup(engine: Engine) -> StartupReport:
    """Connects the adapter (Engine.start(), which exercises the
    SigningBoundary gate), then resyncs any in-doubt orders, then checks
    local state against the venue. Runs once; call this at process start,
    not on a timer."""
    health = engine.start()
    resynced_orders = synchronize(engine)
    reconciliation = reconcile(engine)
    return StartupReport(health=health, resynced_orders=resynced_orders, reconciliation=reconciliation)


def shutdown(engine: Engine) -> None:
    """Disconnects the adapter and releases the EventStore lock (Engine.
    stop()). No additional coordination is needed on the way down."""
    engine.stop()
