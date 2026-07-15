"""In-memory mock Exchange Adapter. No network. Used only for interface
compliance, serialization, and failure-path tests -- explicitly requested
for that purpose. Demonstrates the intended SigningBoundary usage pattern
(signs a canonical payload for every mutation) without ever touching raw
key material, which it has no way to access in the first place.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Optional, Tuple

from secrets_boundary import SigningBoundary, SigningPurpose

from .adapter import ExchangeAdapter
from .errors import (
    ExchangeAdapterError,
    ExchangeConnectionError,
    ExchangeRejectedOrderError,
    OrderUnknownError,
    SequenceGapError,
    StaleSnapshotError,
)
from .models import (
    AmendRequest,
    Balance,
    CancelAllRequest,
    CancelRequest,
    ExchangeCapabilities,
    Fill,
    FundingRate,
    HealthStatus,
    MarkPrice,
    Order,
    OrderRequest,
    OrderStatus,
    OrderType,
    Position,
    ReconciliationReport,
    Symbol,
)

DEFAULT_MOCK_CAPABILITIES = ExchangeCapabilities(
    supports_reduce_only=True,
    supports_post_only=True,
    supports_ioc=True,
    supports_fok=False,
    supports_market_orders=True,
    supports_limit_orders=True,
    supports_trigger_orders=False,
    supports_partial_fill_notifications=True,
    supports_funding_rate=True,
    supports_cross_margin=True,
    supports_isolated_margin=True,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MockExchangeAdapter(ExchangeAdapter):
    def __init__(
        self,
        signing_boundary: SigningBoundary,
        signing_key_ref: str,
        exchange_name: str = "mock",
        adapter_version: str = "1.0.0-mock",
        capabilities: ExchangeCapabilities = DEFAULT_MOCK_CAPABILITIES,
    ):
        super().__init__(signing_boundary, exchange_name, adapter_version, capabilities)
        self._signing_key_ref = signing_key_ref
        self._connected = False
        self._orders: Dict[str, Order] = {}
        self._positions: Dict[str, Position] = {}
        self._balances: Dict[str, Balance] = {}
        self._mark_prices: Dict[str, MarkPrice] = {}
        self._funding_rates: Dict[str, FundingRate] = {}
        self._fills: list = []
        self._next_order_seq = 0
        self._stale_snapshot = False
        self._sequence_gap = False
        self._fail_next: Dict[str, Exception] = {}

    # -- test-only failure injection / fixture helpers (not part of the interface) --

    def simulate_disconnect(self) -> None:
        self._connected = False

    def simulate_stale_snapshot(self, stale: bool = True) -> None:
        self._stale_snapshot = stale

    def simulate_sequence_gap(self, gap: bool = True) -> None:
        self._sequence_gap = gap

    def fail_next(self, method_name: str, exc: Exception) -> None:
        self._fail_next[method_name] = exc

    def set_position(self, position: Position) -> None:
        self._positions[position.symbol.value] = position

    def set_balance(self, balance: Balance) -> None:
        self._balances[balance.asset.value] = balance

    def set_mark_price(self, price: MarkPrice) -> None:
        self._mark_prices[price.symbol.value] = price

    def set_funding_rate(self, rate: FundingRate) -> None:
        self._funding_rates[rate.symbol.value] = rate

    def _maybe_raise(self, method_name: str) -> None:
        exc = self._fail_next.pop(method_name, None)
        if exc is not None:
            raise exc

    def _require_connected(self) -> None:
        if not self._connected:
            raise ExchangeConnectionError("adapter is not connected")

    # -- connection lifecycle --

    def connect(self) -> HealthStatus:
        self._maybe_raise("connect")
        self._signing.sign(self._signing_key_ref, SigningPurpose.AUTH, b"connect")
        self._connected = True
        return self.health()

    def disconnect(self) -> None:
        self._connected = False

    def health(self) -> HealthStatus:
        self._maybe_raise("health")
        from .models import ConnectionState

        if not self._connected:
            state = ConnectionState.DISCONNECTED
        elif self._sequence_gap or self._stale_snapshot:
            state = ConnectionState.DEGRADED
        else:
            state = ConnectionState.CONNECTED
        return HealthStatus(
            connection_state=state,
            websocket_connected=self._connected,
            rest_reachable=self._connected,
            last_message_age_ms=60_000.0 if self._stale_snapshot else 0.0,
            sequence_gap_detected=self._sequence_gap,
            checked_at_utc=_now(),
        )

    # -- reads --

    def get_positions(self) -> Tuple[Position, ...]:
        self._maybe_raise("get_positions")
        self._require_connected()
        if self._stale_snapshot:
            raise StaleSnapshotError("position snapshot exceeds freshness threshold")
        if self._sequence_gap:
            raise SequenceGapError("websocket sequence gap detected; snapshot not trustworthy")
        return tuple(self._positions.values())

    def get_orders(self) -> Tuple[Order, ...]:
        self._maybe_raise("get_orders")
        self._require_connected()
        return tuple(self._orders.values())

    def get_balances(self) -> Tuple[Balance, ...]:
        self._maybe_raise("get_balances")
        self._require_connected()
        return tuple(self._balances.values())

    def get_mark_price(self, symbol: Symbol) -> MarkPrice:
        self._maybe_raise("get_mark_price")
        self._require_connected()
        price = self._mark_prices.get(symbol.value)
        if price is None:
            raise ExchangeAdapterError(f"no mark price available for {symbol.value}")
        return price

    def get_funding_rate(self, symbol: Symbol) -> FundingRate:
        self._maybe_raise("get_funding_rate")
        self._require_connected()
        if not self._capabilities.supports_funding_rate:
            raise ExchangeAdapterError(f"{self._exchange_name} does not support funding rates")
        rate = self._funding_rates.get(symbol.value)
        if rate is None:
            raise ExchangeAdapterError(f"no funding rate available for {symbol.value}")
        return rate

    def get_order_status(self, exchange_order_id: str) -> Order:
        self._maybe_raise("get_order_status")
        self._require_connected()
        order = self._orders.get(exchange_order_id)
        if order is None:
            raise OrderUnknownError(f"no order known with exchange_order_id={exchange_order_id!r}")
        return order

    def get_fills(self, since_utc: Optional[str] = None) -> Tuple[Fill, ...]:
        self._maybe_raise("get_fills")
        self._require_connected()
        if since_utc is None:
            return tuple(self._fills)
        return tuple(f for f in self._fills if f.timestamp_utc >= since_utc)

    def reconcile(self, local_positions: Tuple[Position, ...]) -> ReconciliationReport:
        self._maybe_raise("reconcile")
        self._require_connected()
        exchange_positions = tuple(self._positions.values())
        local_by_symbol = {p.symbol.value: p for p in local_positions}
        exch_by_symbol = {p.symbol.value: p for p in exchange_positions}
        discrepancies = []
        for symbol_value in set(local_by_symbol) | set(exch_by_symbol):
            local_p = local_by_symbol.get(symbol_value)
            exch_p = exch_by_symbol.get(symbol_value)
            local_qty = local_p.quantity if local_p else Decimal("0")
            exch_qty = exch_p.quantity if exch_p else Decimal("0")
            if local_qty != exch_qty:
                discrepancies.append(f"{symbol_value}: local={local_qty} exchange={exch_qty}")
        return ReconciliationReport(
            matches=(len(discrepancies) == 0),
            local_positions=local_positions,
            exchange_positions=exchange_positions,
            discrepancies=tuple(discrepancies),
            checked_at_utc=_now(),
        )

    # -- transmission hooks (called only by the base class's audited/idempotent wrappers) --

    def _next_exchange_order_id(self) -> str:
        self._next_order_seq += 1
        return f"mock-order-{self._next_order_seq}"

    def _transmit_place_order(self, request: OrderRequest) -> Order:
        self._maybe_raise("place_order")
        self._require_connected()
        if request.order_type is OrderType.MARKET and not self._capabilities.supports_market_orders:
            raise ExchangeRejectedOrderError(f"{self._exchange_name} does not support market orders")
        if request.order_type is OrderType.LIMIT and not self._capabilities.supports_limit_orders:
            raise ExchangeRejectedOrderError(f"{self._exchange_name} does not support limit orders")
        if request.reduce_only and not self._capabilities.supports_reduce_only:
            raise ExchangeRejectedOrderError(f"{self._exchange_name} does not support reduce_only")

        payload = f"{request.client_order_id}:{request.symbol.value}:{request.side.value}:{request.quantity}"
        self._signing.sign(self._signing_key_ref, SigningPurpose.ORDER, payload.encode("utf-8"))

        now = _now()
        order = Order(
            client_order_id=request.client_order_id,
            exchange_order_id=self._next_exchange_order_id(),
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            quantity=request.quantity,
            filled_quantity=Decimal("0"),
            limit_price=request.limit_price,
            status=OrderStatus.ACKNOWLEDGED,
            time_in_force=request.time_in_force,
            reduce_only=request.reduce_only,
            created_at_utc=now,
            updated_at_utc=now,
        )
        self._orders[order.exchange_order_id] = order
        return order

    def _transmit_amend_order(self, request: AmendRequest) -> Order:
        self._maybe_raise("amend_order")
        self._require_connected()
        existing = self._orders.get(request.exchange_order_id)
        if existing is None:
            raise OrderUnknownError(f"no order known with exchange_order_id={request.exchange_order_id!r}")

        payload = f"{request.request_id}:{request.exchange_order_id}:{request.new_quantity}:{request.new_limit_price}"
        self._signing.sign(self._signing_key_ref, SigningPurpose.AMEND, payload.encode("utf-8"))

        updated = Order(
            client_order_id=existing.client_order_id,
            exchange_order_id=existing.exchange_order_id,
            symbol=existing.symbol,
            side=existing.side,
            order_type=existing.order_type,
            quantity=request.new_quantity if request.new_quantity is not None else existing.quantity,
            filled_quantity=existing.filled_quantity,
            limit_price=request.new_limit_price if request.new_limit_price is not None else existing.limit_price,
            status=existing.status,
            time_in_force=existing.time_in_force,
            reduce_only=existing.reduce_only,
            created_at_utc=existing.created_at_utc,
            updated_at_utc=_now(),
        )
        self._orders[existing.exchange_order_id] = updated
        return updated

    def _transmit_cancel_order(self, request: CancelRequest) -> Order:
        self._maybe_raise("cancel_order")
        self._require_connected()
        existing = self._orders.get(request.exchange_order_id)
        if existing is None:
            raise OrderUnknownError(f"no order known with exchange_order_id={request.exchange_order_id!r}")

        payload = f"{request.request_id}:{request.exchange_order_id}"
        self._signing.sign(self._signing_key_ref, SigningPurpose.CANCEL, payload.encode("utf-8"))

        cancelled = Order(
            client_order_id=existing.client_order_id,
            exchange_order_id=existing.exchange_order_id,
            symbol=existing.symbol,
            side=existing.side,
            order_type=existing.order_type,
            quantity=existing.quantity,
            filled_quantity=existing.filled_quantity,
            limit_price=existing.limit_price,
            status=OrderStatus.CANCELLED,
            time_in_force=existing.time_in_force,
            reduce_only=existing.reduce_only,
            created_at_utc=existing.created_at_utc,
            updated_at_utc=_now(),
        )
        self._orders[existing.exchange_order_id] = cancelled
        return cancelled

    def _transmit_cancel_all(self, request: CancelAllRequest) -> Tuple[Order, ...]:
        self._maybe_raise("cancel_all")
        self._require_connected()

        payload = f"{request.request_id}:{request.symbol.value if request.symbol else '*'}"
        self._signing.sign(self._signing_key_ref, SigningPurpose.CANCEL, payload.encode("utf-8"))

        cancelled = []
        for order_id, order in list(self._orders.items()):
            if order.status in (OrderStatus.CANCELLED, OrderStatus.FILLED, OrderStatus.REJECTED):
                continue
            if request.symbol is not None and order.symbol.value != request.symbol.value:
                continue
            updated = Order(
                client_order_id=order.client_order_id,
                exchange_order_id=order.exchange_order_id,
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                quantity=order.quantity,
                filled_quantity=order.filled_quantity,
                limit_price=order.limit_price,
                status=OrderStatus.CANCELLED,
                time_in_force=order.time_in_force,
                reduce_only=order.reduce_only,
                created_at_utc=order.created_at_utc,
                updated_at_utc=_now(),
            )
            self._orders[order_id] = updated
            cancelled.append(updated)
        return tuple(cancelled)

    # -- fixture helper for simulating a fill (test-only, not part of the interface) --

    def simulate_fill(self, exchange_order_id: str, fill_quantity: Decimal, fill_price: Decimal) -> Order:
        existing = self._orders.get(exchange_order_id)
        if existing is None:
            raise OrderUnknownError(f"no order known with exchange_order_id={exchange_order_id!r}")
        new_filled = existing.filled_quantity + fill_quantity
        status = OrderStatus.FILLED if new_filled >= existing.quantity else OrderStatus.PARTIALLY_FILLED
        updated = Order(
            client_order_id=existing.client_order_id,
            exchange_order_id=existing.exchange_order_id,
            symbol=existing.symbol,
            side=existing.side,
            order_type=existing.order_type,
            quantity=existing.quantity,
            filled_quantity=new_filled,
            limit_price=existing.limit_price,
            status=status,
            time_in_force=existing.time_in_force,
            reduce_only=existing.reduce_only,
            created_at_utc=existing.created_at_utc,
            updated_at_utc=_now(),
        )
        self._orders[exchange_order_id] = updated
        self._fills.append(
            Fill(
                fill_id=f"mock-fill-{len(self._fills) + 1}",
                client_order_id=existing.client_order_id,
                exchange_order_id=exchange_order_id,
                symbol=existing.symbol,
                side=existing.side,
                price=fill_price,
                quantity=fill_quantity,
                fee=Decimal("0"),
                timestamp_utc=_now(),
            )
        )
        return updated
