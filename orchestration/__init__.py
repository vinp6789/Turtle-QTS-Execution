"""Runtime Orchestration Layer for the Turtle Execution Engine.

Sits ABOVE composition_root, consuming an already-built Engine (never
constructing one itself -- that separation from dependency injection is
structural, not conventional: nothing in this package imports config,
secrets_boundary, event_store, or any adapter constructor). Coordinates
four things, each by calling methods the frozen modules (and
composition_root's Engine) already expose:

    1. Lifecycle    -- startup()/shutdown(): sequences Engine.start()/
                       stop() with an initial order resync and
                       reconciliation check. One-shot; not a loop.
    2. Synchronization -- synchronize(): resyncs whatever OrderManager's
                       own in_doubt_client_order_ids/resync_order already
                       flags and knows how to fix.
    3. Reconciliation  -- reconcile(): translates PortfolioManager's/
                       PositionManager's already-computed local state
                       into the adapter's own reconcile() contract.
    4. Dispatch        -- dispatch(event): routes a venue-observed Fill/
                       Order to OrderManager's own report_fill()/
                       report_order_update().

Deliberately NOT in scope (see the Milestone 3 constraints this package
was built under): no trading strategy, no signal generation, no position
sizing, no exchange-specific branching (every function here operates only
through the abstract ExchangeAdapter/Position/Fill/Order contracts), and
no re-implementation of logic that already lives in a frozen module. In
particular, this package never constructs a risk_manager.TradeRequest or
calls RiskManager.evaluate() -- deciding to propose a trade is a
strategy-layer concern this milestone does not build.

No loop, timer, or scheduler is included. Every function here runs once
and returns; a future scheduler (explicitly out of scope, per
docs/ROADMAP.md's "Live orchestration / engine entrypoint" gap) decides
WHEN to call these, not this package.

Public API:
    Orchestrator          -- ergonomic wrapper over an Engine
    startup, shutdown     -- lifecycle.py's free functions
    synchronize           -- synchronization.py's free function
    reconcile             -- reconciliation.py's free function
    dispatch              -- dispatch.py's free function
    StartupReport         -- bundles one startup sequence's outcomes
    FillObserved, OrderStatusObserved, VenueEvent -- dispatch's event types
    OrchestrationError, UnknownVenueEventError    -- this package's errors
"""

from .dispatch import dispatch
from .errors import OrchestrationError, UnknownVenueEventError
from .events import FillObserved, OrderStatusObserved, VenueEvent
from .lifecycle import StartupReport, shutdown, startup
from .orchestrator import Orchestrator
from .reconciliation import reconcile
from .synchronization import synchronize

__all__ = [
    "Orchestrator",
    "startup",
    "shutdown",
    "synchronize",
    "reconcile",
    "dispatch",
    "StartupReport",
    "FillObserved",
    "OrderStatusObserved",
    "VenueEvent",
    "OrchestrationError",
    "UnknownVenueEventError",
]
