"""Coordinates order-state synchronization after a restart or a suspected
gap, using OrderManager's own in-doubt/resync primitives.

All synchronization LOGIC already lives inside order_manager/manager.py:
in_doubt_client_order_ids identifies which orders this OrderManager cannot
currently vouch for (e.g. a crash between transmit and confirmation), and
resync_order() already re-queries the adapter (via find_order/
get_order_status) and reconciles the result into the durable lifecycle
record -- see order_manager/manager.py. This module does not re-implement
any of that; it only iterates the ids OrderManager already flags and
calls the method OrderManager already exposes for exactly this purpose.
"""

from typing import Tuple

from composition_root import Engine
from order_manager import OrderSnapshot


def synchronize(engine: Engine) -> Tuple[OrderSnapshot, ...]:
    """Resync every order OrderManager currently considers in doubt.
    Returns the resulting OrderSnapshots (empty if none were in doubt)."""
    order_manager = engine.order_manager
    return tuple(
        order_manager.resync_order(client_order_id)
        for client_order_id in order_manager.in_doubt_client_order_ids
    )
