"""HyperliquidAdapter: concrete ExchangeAdapter for Hyperliquid (Module
10, WP-5). READ-ONLY BUILD.

Implements all 11 abstract read/lifecycle methods against Hyperliquid's
public /info endpoint (no authentication required -- verified: any
address can be queried, per Hyperliquid's Info endpoint docs). The four
mutation hooks are FAIL-CLOSED: each raises immediately, before any
network call and before any signing capability is invoked, since no
signing implementation exists yet (deferred to a future work package
under its own ADR -- see ADR-20/21's finding that SigningBoundary cannot
itself produce venue-verifiable signatures).

find_order() is NOT overridden -- WP-2's default (scan get_orders() for a
matching client_order_id) is inherited unchanged; nothing about this
adapter's order representation requires a different attribution strategy.

Design notes on two constructor decisions that were flagged, but not
separately re-litigated, in the WP-5 roadmap entry:
  - account_address is a REQUIRED constructor argument. This is not a
    design choice with alternatives: Hyperliquid's info requests take a
    wallet address as a mandatory parameter ("user": "0x...") and there is
    no way to query positions/orders/fills without one. It is public data
    (what the private key controls, never the key itself) -- no different
    in kind from the existing signing_key_ref pattern of naming, not
    holding, sensitive material.
  - Only connect() gates on SigningBoundary.sign(..., AUTH, ...); reads do
    not. This matches MockExchangeAdapter's own established, frozen
    pattern exactly (verified: none of its get_* methods call
    self._signing.sign(); only connect() and the four mutations do) --
    not a new decision, just following existing precedent.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Tuple

from secrets_boundary import SigningBoundary, SigningPurpose

from exchange_adapter import (
    AmendRequest,
    Balance,
    CancelAllRequest,
    CancelRequest,
    ConnectionState,
    ExchangeAdapter,
    ExchangeAdapterError,
    ExchangeConnectionError,
    ExchangeCapabilities,
    Fill,
    FundingRate,
    HealthStatus,
    MarkPrice,
    Order,
    OrderRequest,
    Position,
    ReconciliationReport,
    Symbol,
)

from . import codec
from .capabilities import DEFAULT_HYPERLIQUID_CAPABILITIES
from .errors import map_unknown_oid
from .transport import DEFAULT_BASE_URL, TransportFn, post_json

_ADAPTER_VERSION = "1.0.0-wp5-readonly"
_DEFAULT_TIMEOUT_SECONDS = 10.0

_READ_ONLY_BUILD_MESSAGE = (
    "HyperliquidAdapter (WP-5, read-only build) does not support {action} -- "
    "no signing capability is implemented yet. This is a deliberate, "
    "fail-closed limitation, not a venue rejection: no network call and no "
    "signing was attempted."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class HyperliquidAdapter(ExchangeAdapter):
    def __init__(
        self,
        signing_boundary: SigningBoundary,
        signing_key_ref: str,
        account_address: str,
        exchange_name: str = "hyperliquid",
        adapter_version: str = _ADAPTER_VERSION,
        capabilities: ExchangeCapabilities = DEFAULT_HYPERLIQUID_CAPABILITIES,
        base_url: str = DEFAULT_BASE_URL,
        transport: TransportFn = post_json,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ):
        super().__init__(signing_boundary, exchange_name, adapter_version, capabilities)
        if not isinstance(account_address, str) or not account_address.strip():
            raise ValueError("account_address must be a non-empty string")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._signing_key_ref = signing_key_ref
        self._account_address = account_address
        self._base_url = base_url
        self._transport = transport
        self._timeout_seconds = timeout_seconds
        self._connected = False
        self._last_checked_at: Optional[str] = None

    # -- internal helpers --

    def _require_connected(self) -> None:
        if not self._connected:
            raise ExchangeConnectionError("adapter is not connected")

    def _info(self, request_type: str, **extra_fields) -> object:
        """POST {"type": request_type, **extra_fields} to /info and
        return the parsed body. All HTTP-status and connection-level
        failures are already mapped into the closed hierarchy by
        transport.post_json; this method adds nothing beyond URL/payload
        construction."""
        response = self._transport(
            f"{self._base_url}/info", {"type": request_type, **extra_fields}, self._timeout_seconds
        )
        return response.body

    # -- connection lifecycle --

    def connect(self) -> HealthStatus:
        self._signing.sign(self._signing_key_ref, SigningPurpose.AUTH, b"connect")
        self._info("allMids")  # lightweight connectivity probe; raises on failure
        self._connected = True
        self._last_checked_at = _now()
        return self.health()

    def disconnect(self) -> None:
        self._connected = False

    def health(self) -> HealthStatus:
        state = ConnectionState.CONNECTED if self._connected else ConnectionState.DISCONNECTED
        return HealthStatus(
            connection_state=state,
            websocket_connected=False,  # no websocket in this (REST-only) build
            rest_reachable=self._connected,
            last_message_age_ms=0.0 if self._connected else None,
            sequence_gap_detected=False,  # no websocket sequence to have gaps
            checked_at_utc=_now(),
        )

    # -- reads --

    def get_positions(self) -> Tuple[Position, ...]:
        self._require_connected()
        body = self._info("clearinghouseState", user=self._account_address)
        return codec.parse_positions(body)

    def get_orders(self) -> Tuple[Order, ...]:
        self._require_connected()
        body = self._info("frontendOpenOrders", user=self._account_address)
        return codec.parse_open_orders(body)

    def get_balances(self) -> Tuple[Balance, ...]:
        self._require_connected()
        body = self._info("clearinghouseState", user=self._account_address)
        return codec.parse_balances(body)

    def get_mark_price(self, symbol: Symbol) -> MarkPrice:
        self._require_connected()
        body = self._info("allMids")
        return codec.parse_mark_price(body, symbol, _now())

    def get_funding_rate(self, symbol: Symbol) -> FundingRate:
        self._require_connected()
        body = self._info("metaAndAssetCtxs")
        return codec.parse_funding_rate(body, symbol, _now())

    def get_order_status(self, exchange_order_id: str) -> Order:
        self._require_connected()
        try:
            oid = int(exchange_order_id)
        except (TypeError, ValueError) as exc:
            raise ExchangeAdapterError(f"exchange_order_id is not a valid Hyperliquid oid: {exchange_order_id!r}") from exc
        body = self._info("orderStatus", user=self._account_address, oid=oid)
        order = codec.parse_order_status(body)
        if order is None:
            raise map_unknown_oid(exchange_order_id)
        return order

    def get_fills(self, since_utc: Optional[str] = None) -> Tuple[Fill, ...]:
        self._require_connected()
        body = self._info("userFills", user=self._account_address)
        fills = codec.parse_user_fills(body)
        if since_utc is None:
            return fills
        return tuple(f for f in fills if f.timestamp_utc >= since_utc)

    def reconcile(self, local_positions: Tuple[Position, ...]) -> ReconciliationReport:
        self._require_connected()
        exchange_positions = self.get_positions()
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

    # -- mutations: FAIL-CLOSED (WP-5 scope; no signing capability exists yet) --

    def _transmit_place_order(self, request: OrderRequest) -> Order:
        raise ExchangeAdapterError(_READ_ONLY_BUILD_MESSAGE.format(action="order placement"))

    def _transmit_amend_order(self, request: AmendRequest) -> Order:
        raise ExchangeAdapterError(_READ_ONLY_BUILD_MESSAGE.format(action="order amendment"))

    def _transmit_cancel_order(self, request: CancelRequest) -> Order:
        raise ExchangeAdapterError(_READ_ONLY_BUILD_MESSAGE.format(action="order cancellation"))

    def _transmit_cancel_all(self, request: CancelAllRequest) -> Tuple[Order, ...]:
        raise ExchangeAdapterError(_READ_ONLY_BUILD_MESSAGE.format(action="cancel-all"))
