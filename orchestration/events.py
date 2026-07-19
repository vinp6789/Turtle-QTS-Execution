"""Venue-observed facts the orchestration layer knows how to route.

A VenueEvent carries no decision -- it is exactly what the adapter
reported (a Fill, an Order's current status), tagged with the engine's
own client_order_id so dispatch() knows which OrderManager record it
belongs to. Deciding WHAT these facts mean for a position or a strategy
is out of scope here; dispatch only forwards to the frozen module that
already owns that interpretation (OrderManager).
"""

from dataclasses import dataclass
from typing import Union

from exchange_adapter import Fill, Order


@dataclass(frozen=True)
class FillObserved:
    """A fill the adapter reported (e.g. via get_fills()), to be recorded
    against the order it belongs to."""

    client_order_id: str
    fill: Fill


@dataclass(frozen=True)
class OrderStatusObserved:
    """A current order state the adapter reported (e.g. via
    get_order_status() or get_orders()), to be reconciled into
    OrderManager's own lifecycle record."""

    client_order_id: str
    order: Order


VenueEvent = Union[FillObserved, OrderStatusObserved]
