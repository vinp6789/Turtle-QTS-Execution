"""SimulatedTransport: real market data, simulated execution.

PERMANENT PLATFORM INFRASTRUCTURE, not scaffolding. This is the standard
execution environment for research, paper trading, validation, business
metrics and approval -- everything up to testnet. Only the transport
changes between environments; the strategy, adapter, order lifecycle,
position tracking, event store and accounting are byte-identical.

WHY A TRANSPORT AND NOT AN ADAPTER. HyperliquidAdapter routes BOTH
directions through one injectable primitive
(TransportFn = Callable[[str, dict, float], HttpResponse]): /info reads at
adapter.py:197, /exchange writes at adapter.py:406. Simulating the
transport therefore reuses the real adapter -- real CandleSource, real
order lifecycle, real codec, real idempotency and cloid mapping -- and
supplies only the venue's answers. Nothing frozen is touched, and nothing
is reimplemented.

WHAT IS SIMULATED, AND WHY THAT BOUNDARY. "Intercept only /exchange" is
insufficient and would fail on the first cycle: account-scoped /info
reads describe OUR account, so passing them through would report an empty
real account while the engine holds simulated positions -- reconciliation
would diverge immediately. Therefore:

    MARKET-scoped  -> PASSED THROUGH to the real venue, unmodified
                      (candleSnapshot, meta, metaAndAssetCtxs, allMids)
    ACCOUNT-scoped -> ANSWERED FROM SIMULATED STATE
                      (userFills, clearinghouseState, frontendOpenOrders,
                       orderStatus)
    /exchange      -> ANSWERED FROM SIMULATED STATE (order, cancel)

PHASE 1 SCOPE, deliberately minimal. Deterministic fills at the order's
own limit price, measured taker fees, order lifecycle, fills, positions.
NO slippage, NO latency, NO partial fills, NO order book, NO market
impact -- each is a later phase, and each would be a guess today, since
this project has never measured its own slippage.

DETERMINISM IS A HARD REQUIREMENT. No RNG and no wall clock participates
in any fill decision; order ids are a monotonic per-instance counter. Two
runs over identical market data produce identical fills.
"""

from decimal import Decimal
from typing import Callable, Dict, List, Optional

from hyperliquid_adapter.transport import HttpResponse, post_json

# Measured live from /info userFees on 2026-08-06 (base tier, no discounts).
TAKER_FEE_RATE = Decimal("0.00045")
MAKER_FEE_RATE = Decimal("0.00015")

# /info request types describing THE MARKET -- always passed through.
_MARKET_TYPES = frozenset({
    "candleSnapshot", "meta", "metaAndAssetCtxs", "allMids", "l2Book",
    "fundingHistory", "spotMeta", "spotMetaAndAssetCtxs", "userFees",
})
# /info request types describing OUR ACCOUNT -- always simulated.
_ACCOUNT_TYPES = frozenset({
    "userFills", "userFillsByTime", "clearinghouseState",
    "frontendOpenOrders", "openOrders", "orderStatus",
})


class SimulatedTransport:
    """A TransportFn. Construct, then pass as `transport=` to build_engine."""

    def __init__(
        self,
        *,
        base_url: str,
        passthrough: Callable[[str, dict, float], HttpResponse] = post_json,
        starting_equity: Decimal = Decimal("10000"),
        clock: Optional[Callable[[], int]] = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._passthrough = passthrough
        self._equity = Decimal(starting_equity)
        # Deterministic: a counter, never a clock or an RNG.
        self._next_oid = 1000
        self._next_tid = 1
        self._orders: Dict[int, dict] = {}
        self._fills: List[dict] = []
        self._positions: Dict[str, Decimal] = {}
        self._entry_px: Dict[str, Decimal] = {}
        self._realized = Decimal("0")
        self._fees_paid = Decimal("0")
        # Stamps fills only; never participates in a fill DECISION.
        self._clock = clock or (lambda: 0)
        self._seq = 0

    # ---------------------------------------------------------- TransportFn

    def __call__(self, url: str, payload: dict, timeout_seconds: float) -> HttpResponse:
        if url.endswith("/exchange"):
            return self._exchange(payload)
        if payload.get("type") in _ACCOUNT_TYPES:
            return self._account(payload)
        # Market types and anything unrecognised pass through: a wrong
        # simulated answer is worse than a real one we did not anticipate.
        return self._passthrough(url, payload, timeout_seconds)

    # ---------------------------------------------------------- market reads

    def _info(self, payload: dict) -> dict:
        return self._passthrough(f"{self._base_url}/info", payload, 10.0).body

    def _mark(self, coin: str) -> Decimal:
        """Real mid from the real venue -- market data is never simulated."""
        mids = self._info({"type": "allMids"}) or {}
        px = mids.get(coin)
        if px is None:
            raise KeyError("no mid price for " + repr(coin) + " from the venue")
        return Decimal(str(px))

    def _coin_for_asset(self, asset: int) -> str:
        universe = (self._info({"type": "meta"}) or {}).get("universe", [])
        if asset < 0 or asset >= len(universe):
            raise KeyError("unknown asset index " + str(asset))
        return universe[asset]["name"]

    # ------------------------------------------------------------ execution

    def _exchange(self, body: dict) -> HttpResponse:
        action = body.get("action", {})
        kind = action.get("type")
        if kind == "order":
            return self._place(action)
        if kind in ("cancel", "cancelByCloid"):
            return self._cancel(action)
        return HttpResponse(status_code=200, body={
            "status": "err",
            "response": "SimulatedTransport does not implement action " + repr(kind),
        })

    def _place(self, action: dict) -> HttpResponse:
        statuses = []
        for wire in action.get("orders", []):
            coin = self._coin_for_asset(int(wire["a"]))
            is_buy = bool(wire["b"])
            px = Decimal(str(wire["p"]))
            sz = Decimal(str(wire["s"]))
            reduce_only = bool(wire.get("r", False))
            oid = self._next_oid
            self._next_oid += 1

            # REDUCE-ONLY IS ENFORCED, NOT MERELY RECORDED. The flag was
            # previously parsed into _orders and never consulted again, so
            # an over-asked close filled in full and FLIPPED the position:
            # measured 2026-08-10, a reduce-only SELL of 0.01042 against a
            # +0.00256 long left a -0.00786 short open while the engine
            # recorded POSITION_CLOSED. Over-asking is the deliberate,
            # correct way to request a full close (lifecycle_probe.py:47),
            # and the real venue clamps it -- measured on Hyperliquid
            # testnet in lifecycle #2, 0.00104 -> 0.00025. The simulator
            # must therefore clamp too, or "everything up to testnet"
            # validates against semantics the venue does not have.
            if reduce_only:
                sz = self._reducible(coin, is_buy, sz)
                if sz == 0:
                    # Nothing to reduce. A reduce-only order must never
                    # OPEN a position, so it is rejected rather than
                    # filled -- {"error": ...} is the shape the adapter
                    # already parses (adapter.py:456).
                    statuses.append({"error":
                        "Order would increase position: reduce-only order "
                        "with no reducible " + coin + " position"})
                    continue

            # PHASE 1 FILL RULE -- deterministic and total: every accepted
            # order fills immediately, in full, at its own limit price.
            # No book, no slippage, no partials (see module docstring).
            # A reduce-only clamp is NOT a partial-fill model: the quantity
            # is decided before the fill, and the fill is still total.
            # Taker fee, because an immediate fill is a taking fill.
            fee = px * sz * TAKER_FEE_RATE
            self._apply_fill(coin, is_buy, px, sz, fee)
            self._seq += 1
            self._fills.append({
                "coin": coin, "px": str(px), "sz": str(sz),
                "side": "B" if is_buy else "A", "time": self._clock(),
                "startPosition": "0",
                "dir": "Open Long" if is_buy else "Open Short",
                "closedPnl": "0", "hash": "0x" + format(self._seq, "064x"),
                "oid": oid, "crossed": True, "fee": str(fee),
                "tid": self._next_tid, "cloid": wire.get("c"),
            })
            self._next_tid += 1
            self._orders[oid] = {
                "coin": coin, "side": "B" if is_buy else "A",
                "limitPx": str(px), "sz": "0", "origSz": str(sz), "oid": oid,
                "timestamp": self._clock(), "cloid": wire.get("c"),
                "reduceOnly": reduce_only,
            }
            statuses.append({"filled": {
                "totalSz": str(sz), "avgPx": str(px), "oid": oid}})
        return HttpResponse(status_code=200, body={
            "status": "ok",
            "response": {"type": "order", "data": {"statuses": statuses}}})

    def _cancel(self, action: dict) -> HttpResponse:
        n = len(action.get("cancels", [])) or 1
        return HttpResponse(status_code=200, body={
            "status": "ok",
            "response": {"type": "cancel", "data": {"statuses": ["success"] * n}}})

    def _reducible(self, coin, is_buy, sz) -> Decimal:
        """How much of `sz` this side may actually close, clamped to the
        open position. Reuses _apply_fill's side convention exactly --
        a BUY is +signed and therefore reduces a SHORT; a SELL is -signed
        and reduces a LONG -- so there is one side semantics in this
        module, not two. Returns 0 when the order would open or add,
        which is the case a reduce-only order must never reach.

        Clamping to abs(prev) is also what makes a flip unreachable:
        |signed| <= |prev| means _apply_fill's new position can only
        shrink toward zero, never cross it."""
        prev = self._positions.get(coin, Decimal("0"))
        if prev == 0:
            return Decimal("0")
        opposes = (prev < 0) if is_buy else (prev > 0)
        return min(sz, abs(prev)) if opposes else Decimal("0")

    def _apply_fill(self, coin, is_buy, px, sz, fee) -> None:
        signed = sz if is_buy else -sz
        prev = self._positions.get(coin, Decimal("0"))
        new = prev + signed
        if prev == 0 or (prev > 0) == (signed > 0):
            # Opening or adding: volume-weighted average entry.
            total = abs(prev) + abs(signed)
            prev_entry = self._entry_px.get(coin, px)
            self._entry_px[coin] = (
                (prev_entry * abs(prev) + px * abs(signed)) / total if total else px)
        else:
            # Reducing or flipping: realise against the existing entry.
            closed = min(abs(prev), abs(signed))
            entry = self._entry_px.get(coin, px)
            self._realized += (px - entry) * closed * (1 if prev > 0 else -1)
            if new != 0 and (new > 0) != (prev > 0):
                self._entry_px[coin] = px          # flipped: new entry
        self._positions[coin] = new
        if new == 0:
            self._entry_px.pop(coin, None)
        self._fees_paid += fee

    # -------------------------------------------------------- account state

    def _account(self, payload: dict) -> HttpResponse:
        t = payload["type"]
        if t in ("userFills", "userFillsByTime"):
            return HttpResponse(status_code=200, body=list(self._fills))
        if t in ("frontendOpenOrders", "openOrders"):
            return HttpResponse(status_code=200, body=[])   # phase 1: nothing rests
        if t == "orderStatus":
            oid = payload.get("oid")
            order = self._orders.get(int(oid)) if oid is not None else None
            if order is None:
                return HttpResponse(status_code=200, body={"status": "unknownOid"})
            return HttpResponse(status_code=200, body={
                "status": "order",
                "order": {"order": order, "status": "filled",
                          "statusTimestamp": self._clock()}})
        if t == "clearinghouseState":
            return HttpResponse(status_code=200, body=self._clearinghouse())
        return HttpResponse(status_code=200, body={})

    def _clearinghouse(self) -> dict:
        positions = []
        unrealized = Decimal("0")
        notional = Decimal("0")
        for coin, size in self._positions.items():
            if size == 0:
                continue
            entry = self._entry_px.get(coin, Decimal("0"))
            mark = self._mark(coin)
            pnl = (mark - entry) * size
            unrealized += pnl
            notional += abs(size) * mark
            positions.append({"position": {
                "coin": coin, "szi": str(size), "entryPx": str(entry),
                "positionValue": str(abs(size) * mark),
                "unrealizedPnl": str(pnl), "returnOnEquity": "0",
                "leverage": {"type": "cross", "value": 1},
                "liquidationPx": None, "marginUsed": str(abs(size) * mark),
                "maxLeverage": 50,
            }, "type": "oneWay"})
        equity = self._equity + self._realized - self._fees_paid + unrealized
        summary = {
            "accountValue": str(equity), "totalNtlPos": str(notional),
            "totalRawUsd": str(equity), "totalMarginUsed": "0",
        }
        return {
            "assetPositions": positions,
            "marginSummary": summary,
            "crossMarginSummary": dict(summary),
            "withdrawable": str(equity), "time": self._clock(),
        }

    # ----------------------------------------------------------- inspection

    def snapshot(self) -> dict:
        """Read-only simulator state, for equity persistence and metrics."""
        unrealized = Decimal("0")
        for coin, size in self._positions.items():
            if size:
                entry = self._entry_px.get(coin, Decimal("0"))
                unrealized += (self._mark(coin) - entry) * size
        equity = self._equity + self._realized - self._fees_paid + unrealized
        return {
            "starting_equity": str(self._equity),
            "realized_pnl": str(self._realized),
            "fees_paid": str(self._fees_paid),
            "unrealized_pnl": str(unrealized),
            "equity": str(equity),
            "open_positions": {c: str(s) for c, s in self._positions.items() if s},
            "fill_count": len(self._fills),
        }
