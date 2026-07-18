"""HyperliquidAdapter: concrete ExchangeAdapter for Hyperliquid (Module 10).

Implements all 11 abstract read/lifecycle methods against Hyperliquid's
public /info endpoint (no authentication required) and, since WP-8, the
four authenticated mutation hooks against /exchange.

MUTATIONS (WP-8) are authenticated and gated:
  - A wallet_signer (hyperliquid_adapter.signing) must be configured, or
    every mutation fails closed with no network call.
  - Each _transmit_* exercises the SigningBoundary authorization gate FIRST
    (Emergency Kill: a revoked signing_key_ref raises before anything is
    signed or sent), then produces the venue phantom-agent EIP-712
    signature with the wallet signer (also revocable), then transmits.
  - place_order persists the engine_id -> venue-token mapping durably
    BEFORE transmission (INV-5) and transmits exactly the recorded token
    (INV-6).
  - Mutations remain UNSAFE_NEVER_AUTO_RETRY at the RetryPolicy level; an
    ambiguous timeout surfaces as ExchangeTimeoutError and is never
    auto-retried. Any signing/build/venue error fails safe (raises), never
    proceeds.
See ADR-20/24: SigningBoundary cannot itself produce venue-verifiable
signatures, so it stays the authorization gate while the wallet signer
(keyed on wallet_key_ref) produces the venue signature.

IDENTIFIER ATTRIBUTION (M1, corrects the WP-5 build's false claim that no
find_order override was needed): Hyperliquid's cloid is a 16-byte token
that cannot carry the engine's client_order_id, so this adapter maintains
a durable engine-id <-> venue-token mapping (hyperliquid_adapter/mapping.py)
persisted through the shared canonical EventStore, and:
  - find_order() IS overridden (INV-19): it derives the order's venue
    token and queries the venue's order status BY that token, which finds
    the order in ANY state -- open, filled, cancelled, or rejected -- not
    merely open; the returned Order is stamped with the caller's own
    client_order_id (identity is guaranteed by the query itself). The
    inherited default (open-orders scan) would miss an in-doubt order
    that filled before a crash. Strictly read-only: never records a
    mapping, never appends, never transmits.
  - get_orders()/get_fills() return only engine-owned entries, labeled
    with engine ids resolved through the mapping (INV-1/INV-3); anything
    unresolvable is excluded, never mislabeled (INV-4).
  - A future mutation implementation MUST transmit only tokens returned
    by OrderIdMapping.record(), which appends fsync-durably before
    returning (INV-5/INV-6). record() refuses to run without a durable
    store, so this ordering is structural, not conventional.

WIRING INVARIANTS the composition root must honor (INV-16, currently
unowned by any module -- future orchestration inherits these):
  - `event_store` must be THE SAME EventStore instance used by
    OrderManager/ExecutionStateMachine/etc. (the single-writer lock makes
    a second open on the same path fail loudly).
  - One engine deployment per venue account: two engines sharing one
    Hyperliquid account would each treat the other's orders as foreign,
    and identical engine ids across deployments would mint identical
    tokens. Mapping events are adapter-private (INV-11): no other module
    may consume them.

Design notes on constructor decisions:
  - account_address is REQUIRED: Hyperliquid info requests take a wallet
    address ("user": "0x...") as a mandatory parameter. It is public data
    (what the private key controls, never the key itself).
  - event_store is OPTIONAL only because a storeless adapter is still a
    valid read-only instrument (public market data; no own orders exist,
    so engine-owned reads correctly return empty). It can never place
    orders: OrderIdMapping.record() raises without a store.
  - Only connect() gates on SigningBoundary.sign(..., AUTH, ...); reads do
    not. This matches MockExchangeAdapter's established, frozen pattern
    (none of its get_* methods call sign(); only connect() and the four
    mutations do).
"""

import threading
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Tuple

from event_store import EventStore
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
    ExchangeRejectedOrderError,
    Fill,
    FundingRate,
    HealthStatus,
    MarkPrice,
    Order,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    ReconciliationReport,
    Symbol,
)

from . import codec
from .capabilities import DEFAULT_HYPERLIQUID_CAPABILITIES
from .errors import map_order_status_error, map_request_error, map_unknown_oid
from .exchange import EXCHANGE_PATH, NonceSource, build_exchange_request
from .mapping import OrderIdMapping, mint_venue_token
from .transport import DEFAULT_BASE_URL, MAINNET_BASE_URL, TESTNET_BASE_URL, TransportFn, post_json

# action_codec (msgpack + keccak) is imported LAZILY inside the _transmit_*
# hooks so the read-only path stays free of the mutation dependencies.

_ADAPTER_VERSION = "1.0.0-wp8"
_DEFAULT_TIMEOUT_SECONDS = 10.0


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
        event_store: Optional[EventStore] = None,
        wallet_signer: Optional[object] = None,
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
        # Rebuilds the engine-id <-> venue-token map from this adapter's
        # own source-tagged events (INV-10/INV-13); empty if store is None.
        self._mapping = OrderIdMapping(account_address, event_store)
        # Optional venue signer (hyperliquid_adapter.signing.HyperliquidWalletSigner).
        # Duck-typed and NOT imported here, so adapter.py stays eth-account-free
        # on the read-only path. Its presence does not enable mutations in this
        # build: the four _transmit_* hooks remain fail-closed because ACTION
        # construction (msgpack action-hash) is WP-8, not WP-6/7. WP-8 will wire
        # this signer into the mutation path behind the SigningBoundary
        # authorization gate.
        self._wallet_signer = wallet_signer
        # Reject a signer whose network contradicts the base_url: the network
        # source ("a"/"b") is bound into every signature, so a mismatch makes
        # every signed action rejected. Only enforced for the two recognized
        # Hyperliquid endpoints; a custom base_url cannot be inferred and is
        # left to the operator.
        if wallet_signer is not None and hasattr(wallet_signer, "is_mainnet"):
            expected = {MAINNET_BASE_URL: True, TESTNET_BASE_URL: False}.get(base_url.rstrip("/"))
            if expected is not None and expected != bool(wallet_signer.is_mainnet):
                net = "mainnet" if wallet_signer.is_mainnet else "testnet"
                raise ValueError(
                    f"wallet signer is configured for {net} but base_url is {base_url!r}; "
                    "a network mismatch would make every signed action rejected"
                )
        self._nonce = NonceSource()
        self._asset_index_cache: Optional[dict] = None
        self._asset_lock = threading.Lock()

    @property
    def wallet_address(self) -> Optional[str]:
        """The venue wallet address, if a signer is configured -- public,
        safe to audit/log; never the key. None when no signer is present."""
        return self._wallet_signer.wallet_address if self._wallet_signer is not None else None

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
        return codec.parse_open_orders(body, self._mapping.resolve)

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
        order = codec.parse_order_status(body, self._mapping.resolve)
        if order is None:
            raise map_unknown_oid(exchange_order_id)
        return order

    def get_fills(self, since_utc: Optional[str] = None) -> Tuple[Fill, ...]:
        self._require_connected()
        body = self._info("userFills", user=self._account_address)
        fills = codec.parse_user_fills(body, self._mapping.resolve)
        if since_utc is None:
            return fills
        return tuple(f for f in fills if f.timestamp_utc >= since_utc)

    # -- attribution: forward-recompute override (INV-19) --

    def find_order(self, request: OrderRequest) -> Optional[Order]:
        """Locate this engine's order at the venue by its venue token,
        covering ANY venue state (open, filled, cancelled, rejected) --
        the inherited open-orders scan would miss an in-doubt order that
        filled before a crash (INV-19).

        Strictly read-only (never records a mapping, never appends, never
        transmits an order). The durably recorded token is preferred when
        one exists; otherwise the deterministic mint of the caller's id is
        used -- for any transmitted order these are identical (INV-6), and
        for a never-transmitted order the venue simply reports unknown,
        which returns None ("still unresolved", the fail-safe outcome).
        The returned Order is stamped with the caller's own
        client_order_id: identity is guaranteed by querying BY the token,
        independent of whether the venue echoes cloid back (INV-1)."""
        self._require_connected()
        token = self._mapping.known_token(request.client_order_id) or mint_venue_token(request.client_order_id)
        body = self._info("orderStatus", user=self._account_address, oid=token)
        return codec.parse_order_status(
            body, self._mapping.resolve, assume_client_order_id=request.client_order_id
        )

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

    # -- mutation-path helpers (WP-8) --

    def _fetch_asset_index_map(self) -> dict:
        body = self._info("meta")
        universe = body.get("universe", []) if isinstance(body, dict) else []
        return {a.get("name"): i for i, a in enumerate(universe) if a.get("name")}

    def refresh_asset_index(self) -> None:
        """Discard the cached coin->index map so the next resolution re-fetches
        `meta`. Read-only and replay-neutral (no EventStore, no venue mutation);
        thread-safe. Call after the venue lists a new asset if you don't want
        to wait for the automatic stale-cache refresh."""
        with self._asset_lock:
            self._asset_index_cache = None

    def _asset_index(self, symbol: Symbol) -> int:
        """Resolve a coin name to its Hyperliquid asset index via the
        unauthenticated `meta` endpoint (cached). On a cache miss the map may
        be stale (a newly-listed asset), so it is refreshed once and retried
        before the symbol is declared unknown -- so a new asset becomes
        tradeable without an adapter restart."""
        with self._asset_lock:
            if self._asset_index_cache is None:
                self._asset_index_cache = self._fetch_asset_index_map()
            idx = self._asset_index_cache.get(symbol.value)
            if idx is None:
                # Possible stale cache -> refresh once and retry.
                self._asset_index_cache = self._fetch_asset_index_map()
                idx = self._asset_index_cache.get(symbol.value)
        if idx is None:
            raise ExchangeRejectedOrderError(f"unknown Hyperliquid asset: {symbol.value}")
        return idx

    def _require_signer(self):
        """Fail-closed if no wallet signer is configured -- a mutation must
        never proceed without the capability to authenticate it."""
        if self._wallet_signer is None:
            raise ExchangeAdapterError(
                "HyperliquidAdapter has no wallet signer configured -- refusing to "
                "attempt a mutation (fail-closed; no network call was made)"
            )

    def _authorization_gate(self, purpose: SigningPurpose, context: bytes) -> None:
        """Emergency-Kill gate: exercise SigningBoundary BEFORE any venue
        signing or transmission. If signing_key_ref has been revoked this
        raises SecretRevokedError and nothing is sent."""
        self._signing.sign(self._signing_key_ref, purpose, context)

    def _sign_and_post(self, action: dict) -> dict:
        """Produce the phantom-agent signature over the action's connectionId
        (wallet signer -- raises if revoked) and POST the authenticated
        request to /exchange. Returns the parsed response body."""
        from . import action_codec

        nonce = self._nonce.next()
        connection_id = action_codec.connection_id(action, nonce)
        signature = self._wallet_signer.sign_connection_id(connection_id)
        body = build_exchange_request(action, nonce, signature)
        response = self._transport(f"{self._base_url}{EXCHANGE_PATH}", body, self._timeout_seconds)
        return response.body

    @staticmethod
    def _check_ok(body: dict) -> None:
        if not isinstance(body, dict):
            raise ExchangeAdapterError("Hyperliquid /exchange returned a non-object response")
        if body.get("status") == "err":
            raise map_request_error(str(body.get("response")))
        if body.get("status") != "ok":
            raise ExchangeAdapterError(f"unexpected Hyperliquid /exchange status: {body.get('status')!r}")

    @staticmethod
    def _statuses(body: dict) -> list:
        response = body.get("response", {})
        data = response.get("data", {}) if isinstance(response, dict) else {}
        return data.get("statuses", []) if isinstance(data, dict) else []

    # -- mutations: authenticated (WP-8). Each gates on SigningBoundary
    #    (Emergency Kill) before any venue signing/transmission, and stays
    #    UNSAFE_NEVER_AUTO_RETRY at the RetryPolicy level (unchanged). --

    def _transmit_place_order(self, request: OrderRequest) -> Order:
        self._require_connected()
        self._require_signer()
        if request.order_type is not OrderType.LIMIT:
            raise ExchangeRejectedOrderError("Hyperliquid supports limit orders only (see capabilities)")
        if request.limit_price is None:
            raise ExchangeRejectedOrderError("a limit order requires a limit_price")
        from . import action_codec

        tif = action_codec.tif_wire(request.time_in_force)  # rejects FOK upfront
        self._authorization_gate(SigningPurpose.ORDER, request.client_order_id.encode("utf-8"))
        # Persist-before-transmit (INV-5): durably record engine_id -> cloid
        # BEFORE the order can reach the venue. The returned cloid is the one
        # that MUST be transmitted (INV-6).
        cloid = self._mapping.record(request.client_order_id)
        asset = self._asset_index(request.symbol)
        wire = action_codec.build_order_wire(
            asset, request.side is OrderSide.BUY, request.limit_price, request.quantity,
            request.reduce_only, tif, cloid,
        )
        body = self._sign_and_post(action_codec.build_order_action([wire]))
        self._check_ok(body)
        return self._parse_place_result(self._statuses(body), request)

    def _parse_place_result(self, statuses: list, request: OrderRequest) -> Order:
        if not statuses:
            raise ExchangeAdapterError("Hyperliquid order response contained no status")
        entry = statuses[0]
        if isinstance(entry, dict) and "error" in entry:
            raise map_order_status_error(str(entry["error"]))
        now = _now()
        # The returned Order carries the ENGINE client_order_id (INV-1): the
        # caller supplied it, so identity is not dependent on any venue echo.
        common = dict(
            client_order_id=request.client_order_id, symbol=request.symbol, side=request.side,
            order_type=request.order_type, quantity=request.quantity, limit_price=request.limit_price,
            time_in_force=request.time_in_force, reduce_only=request.reduce_only,
            created_at_utc=now, updated_at_utc=now,
        )
        if isinstance(entry, dict) and "resting" in entry:
            oid = entry["resting"].get("oid")
            return Order(exchange_order_id=str(oid), filled_quantity=Decimal("0"),
                         status=OrderStatus.ACKNOWLEDGED, **common)
        if isinstance(entry, dict) and "filled" in entry:
            filled = entry["filled"]
            return Order(exchange_order_id=str(filled.get("oid")),
                         filled_quantity=Decimal(str(filled.get("totalSz"))),
                         status=OrderStatus.FILLED, **common)
        raise ExchangeAdapterError(f"unexpected Hyperliquid order status entry: {entry!r}")

    def _transmit_cancel_order(self, request: CancelRequest) -> Order:
        self._require_connected()
        self._require_signer()
        self._authorization_gate(SigningPurpose.CANCEL, request.exchange_order_id.encode("utf-8"))
        # CancelRequest carries no symbol; recover the order (and its asset)
        # via an unauthenticated status read. Raises OrderUnknownError if gone.
        order = self.get_order_status(request.exchange_order_id)
        from . import action_codec

        asset = self._asset_index(order.symbol)
        body = self._sign_and_post(action_codec.build_cancel_action([(asset, int(request.exchange_order_id))]))
        self._check_ok(body)
        statuses = self._statuses(body)
        if statuses and isinstance(statuses[0], dict) and "error" in statuses[0]:
            raise map_order_status_error(str(statuses[0]["error"]))
        return self._as_cancelled(order)

    def _transmit_cancel_all(self, request: CancelAllRequest) -> Tuple[Order, ...]:
        self._require_connected()
        self._require_signer()
        self._authorization_gate(SigningPurpose.CANCEL, b"cancel_all")
        orders = self.get_orders()  # engine-owned, engine-id-labeled (INV-1/INV-3)
        if request.symbol is not None:
            orders = tuple(o for o in orders if o.symbol.value == request.symbol.value)
        cancellable = tuple(o for o in orders if o.exchange_order_id is not None)
        if not cancellable:
            return ()
        from . import action_codec

        cancels = [(self._asset_index(o.symbol), int(o.exchange_order_id)) for o in cancellable]
        body = self._sign_and_post(action_codec.build_cancel_action(cancels))
        self._check_ok(body)
        statuses = self._statuses(body)
        # Report an order cancelled ONLY on the venue's affirmative success
        # marker. Hyperliquid returns the string "success" per successful
        # cancel, or {"error": ...} on rejection. Anything else -- a missing
        # status (partial/truncated response), an error, or an
        # unrecognized/malformed entry -- is NOT confirmation and is skipped,
        # so a possibly-live order is never silently reported as cancelled
        # (fail-safe: report only what the venue affirmatively confirmed).
        result = []
        for i, o in enumerate(cancellable):
            entry = statuses[i] if i < len(statuses) else None
            if entry == "success":
                result.append(self._as_cancelled(o))
        return tuple(result)

    def _transmit_amend_order(self, request: AmendRequest) -> Order:
        self._require_connected()
        self._require_signer()
        self._authorization_gate(SigningPurpose.AMEND, request.exchange_order_id.encode("utf-8"))
        # AmendRequest lacks symbol/side/tif and the unchanged fields; recover
        # the current order to build a complete modify order-wire.
        order = self.get_order_status(request.exchange_order_id)
        from . import action_codec

        asset = self._asset_index(order.symbol)
        new_price = request.new_limit_price if request.new_limit_price is not None else order.limit_price
        new_size = request.new_quantity if request.new_quantity is not None else order.quantity
        if new_price is None:
            raise ExchangeRejectedOrderError("amend: order has no limit price to modify")
        tif = action_codec.tif_wire(order.time_in_force)
        cloid = self._mapping.known_token(order.client_order_id)
        wire = action_codec.build_order_wire(
            asset, order.side is OrderSide.BUY, new_price, new_size, order.reduce_only, tif, cloid,
        )
        body = self._sign_and_post(action_codec.build_modify_action(int(request.exchange_order_id), wire))
        self._check_ok(body)
        # Hyperliquid `modify` is cancel-and-replace: on success the venue
        # RETIRES request.exchange_order_id and allocates a NEW oid, while the
        # replacement keeps the SAME cloid. The pre-modify oid is now obsolete;
        # returning it would break any later cancel()/get_order_status().
        #
        # Resolve the replacement via OPEN ORDERS (frontendOpenOrders), NOT via
        # orderStatus-by-cloid. Live-testnet evidence: after a modify,
        # orderStatus(cloid) still resolves the reused cloid to the now-CANCELLED
        # ORIGINAL oid, whereas frontendOpenOrders shows the LIVE replacement
        # under the same cloid with the new oid. get_orders() reads
        # frontendOpenOrders and resolves cloid->engine-id (INV-1), so matching
        # on the engine id yields the live replacement. This mirrors cancel_all,
        # which already resolves live oids this way (and was never affected by
        # the oid change). Because always_place is false (the `a` flag is omitted
        # from build_modify_action), a successful modify is guaranteed to REST
        # (non-executable/ALO), so the replacement always appears here -- no fill
        # race. One deterministic read; no polling, retry, sleep, or
        # EventStore/mapping/signing change (the cloid<->engine-id mapping is
        # oid-agnostic and unchanged by a modify).
        replacement = next(
            (o for o in self.get_orders() if o.client_order_id == order.client_order_id),
            None,
        )
        if replacement is None:
            raise ExchangeAdapterError(
                "amend succeeded at the venue but no open order for "
                f"{order.client_order_id!r} was found to resolve the replacement oid -- "
                "re-query before operating on it (never returning the obsolete oid)"
            )
        return replacement

    @staticmethod
    def _as_cancelled(order: Order) -> Order:
        return Order(
            client_order_id=order.client_order_id, exchange_order_id=order.exchange_order_id,
            symbol=order.symbol, side=order.side, order_type=order.order_type, quantity=order.quantity,
            filled_quantity=order.filled_quantity, limit_price=order.limit_price,
            status=OrderStatus.CANCELLED, time_in_force=order.time_in_force,
            reduce_only=order.reduce_only, created_at_utc=order.created_at_utc, updated_at_utc=_now(),
        )
