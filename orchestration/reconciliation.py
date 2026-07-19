"""Coordinates local-vs-venue position reconciliation, using
PortfolioManager/PositionManager's own state and the adapter's own
reconcile() contract.

All reconciliation-COMPARISON logic already lives in the adapter
(exchange_adapter.adapter.ExchangeAdapter.reconcile / each concrete
adapter's implementation, e.g. hyperliquid_adapter.adapter.
HyperliquidAdapter.reconcile). This module's only job is to translate
PortfolioManager/PositionManager's already-computed local state into the
Position shape reconcile() already expects -- it introduces no new
comparison, tolerance, or PnL arithmetic:

  - open_position_ids comes from PortfolioManager's own PortfolioSnapshot
    (portfolio_manager/snapshot.py: "the set of open positions" is
    already that module's stated responsibility).
  - Each position's symbol/side/quantity/avg_entry_price comes from
    PositionManager's own PositionSnapshot.
  - unrealized_pnl is computed by calling PositionManager's own
    unrealized_pnl(position_id, mark_price) -- never recomputed here.
  - mark_price comes from the adapter's own get_mark_price(symbol).
  - liquidation_price is left None: no frozen module tracks one locally,
    and reconcile() does not read this field for its comparison (it
    compares by symbol/quantity only -- see adapter.py's own
    local_by_symbol/exch_by_symbol construction), so fabricating a value
    here would only manufacture false precision.

A position whose remaining_quantity is already zero is skipped: it is
locally flat and reconcile() naturally reports zero for any symbol with
no local entry, so omitting it changes nothing about the comparison.
"""

from typing import Tuple

from composition_root import Engine
from exchange_adapter import OrderSide, Position, ReconciliationReport


def _local_positions(engine: Engine) -> Tuple[Position, ...]:
    portfolio_snapshot = engine.portfolio_manager.get_snapshot()
    positions = []
    for position_id in portfolio_snapshot.open_position_ids:
        snapshot = engine.position_manager.get_position(position_id)
        if snapshot.remaining_quantity == 0:
            continue
        mark_price = engine.adapter.get_mark_price(snapshot.symbol).price
        entry_price = snapshot.avg_entry_price if snapshot.avg_entry_price is not None else mark_price
        signed_quantity = (
            snapshot.remaining_quantity if snapshot.side is OrderSide.BUY else -snapshot.remaining_quantity
        )
        positions.append(
            Position(
                symbol=snapshot.symbol,
                quantity=signed_quantity,
                entry_price=entry_price,
                mark_price=mark_price,
                unrealized_pnl=engine.position_manager.unrealized_pnl(position_id, mark_price),
                liquidation_price=None,
            )
        )
    return tuple(positions)


def reconcile(engine: Engine) -> ReconciliationReport:
    """Builds the local-position view from PortfolioManager/
    PositionManager and hands it to the adapter's own reconcile()."""
    return engine.adapter.reconcile(_local_positions(engine))
