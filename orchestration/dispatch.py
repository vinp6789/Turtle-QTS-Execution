"""Routes a VenueEvent to the frozen module that owns processing it.

This is the entire "dispatch events" responsibility: given a fact the
adapter already reported, forward it to OrderManager's own report_fill()/
report_order_update(). Every byte of fill/order-lifecycle processing logic
lives in order_manager/manager.py; this function decides nothing about
WHAT the fact means, only WHERE it goes.
"""

from composition_root import Engine
from order_manager import OrderSnapshot

from .errors import UnknownVenueEventError
from .events import FillObserved, OrderStatusObserved, VenueEvent


def dispatch(engine: Engine, event: VenueEvent) -> OrderSnapshot:
    if isinstance(event, FillObserved):
        return engine.order_manager.report_fill(event.client_order_id, event.fill)
    if isinstance(event, OrderStatusObserved):
        return engine.order_manager.report_order_update(event.client_order_id, event.order)
    raise UnknownVenueEventError(
        f"no dispatch route for event type {type(event).__name__} -- "
        "expected FillObserved or OrderStatusObserved"
    )
