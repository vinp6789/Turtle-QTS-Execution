"""Hyperliquid JSON <-> Module 5 typed-model translation (Module 10, M1).

Pure functions only: no network, no signing, no state. Every money/
quantity field is parsed through Decimal (never float) before crossing
into a frozen model, per exchange_adapter/models.py's own requirement.

Schema sources (Hyperliquid /info endpoint, verified against official
GitBook docs and the hyperliquid-python-sdk during this work package):
  clearinghouseState, allMids, openOrders/frontendOpenOrders, userFills,
  orderStatus, metaAndAssetCtxs.

ATTRIBUTION (M1 / invariant catalogue): Order.client_order_id and
Fill.client_order_id on the frozen models always carry the ENGINE's id,
never a venue token (INV-1). The venue returns only its cloid, so every
order/fill parser takes a `resolve` callable (venue token -> engine id,
or None) supplied by the adapter's durable OrderIdMapping. Entries whose
token does not resolve -- foreign orders, orders from another engine, or
entries carrying no cloid at all -- are EXCLUDED, never mislabeled and
never given a fabricated id (INV-3, INV-4). Exclusion is the deliberate
safe direction: returning fewer entries than the venue holds can only
under-report, never mis-attribute.

ASSUMPTION (flagged, not independently verified): orderStatus's nested
order object is assumed to share openOrders/frontendOpenOrders' field
shape (coin, limitPx, oid, side, sz, origSz, reduceOnly, orderType) --
Hyperliquid's own docs redacted this nested object's fields in every
example available during this work package. Parsing is defensive
(dict.get with explicit failure) so a wrong assumption raises a closed-
hierarchy error rather than silently fabricating a model.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Callable, Optional, Tuple

# venue token -> engine client_order_id, or None when unattributable.
Resolver = Callable[[str], Optional[str]]

from exchange_adapter import (
    Balance,
    ExchangeAdapterError,
    Fill,
    FundingRate,
    MarkPrice,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    Symbol,
    TimeInForce,
)

# "A" = Ask (sell), "B" = Bid (buy). Verified against openOrders/userFills docs.
_SIDE_MAP = {"A": OrderSide.SELL, "B": OrderSide.BUY}

# OrderType is only MARKET|LIMIT on the frozen model, and
# hyperliquid_adapter.capabilities declares supports_market_orders=False
# (ADR-22). Every order this adapter can ever see -- placed by this
# engine or read back from the venue -- is therefore a limit order by
# construction; there is no venue orderType string to branch on.
_ORDER_TYPE = OrderType.LIMIT
_TIME_IN_FORCE_DEFAULT = TimeInForce.GTC

# orderStatus's documented status enum, mapped to the frozen OrderStatus.
# Every *Rejected/*Canceled variant collapses to the two frozen states
# that best describe "did not end up live/filled" -- Module 5 has no
# closed-vs-rejected-reason enum of its own to preserve the venue's finer
# distinctions, and it is not this codec's place to invent one.
_ORDER_STATUS_MAP = {
    "open": OrderStatus.ACKNOWLEDGED,
    "filled": OrderStatus.FILLED,
    "canceled": OrderStatus.CANCELLED,
    "triggered": OrderStatus.ACKNOWLEDGED,
    "marginCanceled": OrderStatus.CANCELLED,
    "vaultWithdrawalCanceled": OrderStatus.CANCELLED,
    "openInterestCapCanceled": OrderStatus.CANCELLED,
    "selfTradeCanceled": OrderStatus.CANCELLED,
    "reduceOnlyCanceled": OrderStatus.CANCELLED,
    "siblingFilledCanceled": OrderStatus.CANCELLED,
    "delistedCanceled": OrderStatus.CANCELLED,
    "liquidatedCanceled": OrderStatus.CANCELLED,
    "scheduledCancel": OrderStatus.CANCELLED,
    "tickRejected": OrderStatus.REJECTED,
    "minTradeNtlRejected": OrderStatus.REJECTED,
    "perpMarginRejected": OrderStatus.REJECTED,
    "reduceOnlyRejected": OrderStatus.REJECTED,
    "badAloPxRejected": OrderStatus.REJECTED,
    "iocCancelRejected": OrderStatus.REJECTED,
    "badTriggerPxRejected": OrderStatus.REJECTED,
    "marketOrderNoLiquidityRejected": OrderStatus.REJECTED,
    "positionIncreaseAtOpenInterestCapRejected": OrderStatus.REJECTED,
    "positionFlipAtOpenInterestCapRejected": OrderStatus.REJECTED,
    "tooAggressiveAtOpenInterestCapRejected": OrderStatus.REJECTED,
    "openInterestIncreaseRejected": OrderStatus.REJECTED,
    "insufficientSpotBalanceRejected": OrderStatus.REJECTED,
    "oracleRejected": OrderStatus.REJECTED,
    "perpMaxPositionRejected": OrderStatus.REJECTED,
}


def _decimal(value, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ExchangeAdapterError(f"Hyperliquid response field {field_name!r} is not a valid number: {value!r}") from exc


def _optional_decimal(value, field_name: str) -> Optional[Decimal]:
    return None if value is None else _decimal(value, field_name)


def _iso(timestamp_ms) -> str:
    try:
        return datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError) as exc:
        raise ExchangeAdapterError(f"Hyperliquid response timestamp is not valid: {timestamp_ms!r}") from exc


def parse_mark_price(all_mids_body: dict, symbol: Symbol, checked_at_utc: str) -> MarkPrice:
    raw = all_mids_body.get(symbol.value)
    if raw is None:
        raise ExchangeAdapterError(f"no mark price available for {symbol.value}")
    return MarkPrice(symbol=symbol, price=_decimal(raw, "allMids price"), timestamp_utc=checked_at_utc)


def parse_positions(clearinghouse_state_body: dict) -> Tuple[Position, ...]:
    positions = []
    for entry in clearinghouse_state_body.get("assetPositions", []):
        pos = entry.get("position", {})
        coin = pos.get("coin")
        if not coin:
            continue
        szi = _decimal(pos.get("szi"), "position.szi")
        position_value = _decimal(pos.get("positionValue"), "position.positionValue")
        # positionValue is the position's notional value (|szi| * markPx);
        # deriving markPx from it avoids relying on any field not actually
        # present on a clearinghouseState position object.
        mark_price = position_value / abs(szi) if szi != 0 else Decimal("0")
        liq_px = pos.get("liquidationPx")
        positions.append(
            Position(
                symbol=Symbol(coin),
                quantity=szi,
                entry_price=_decimal(pos.get("entryPx"), "position.entryPx"),
                mark_price=mark_price,
                unrealized_pnl=_decimal(pos.get("unrealizedPnl"), "position.unrealizedPnl"),
                liquidation_price=_optional_decimal(liq_px, "position.liquidationPx"),
            )
        )
    return tuple(positions)


def parse_balances(clearinghouse_state_body: dict) -> Tuple[Balance, ...]:
    """Hyperliquid perps margin is a single USDC-denominated account, not
    a per-asset balance sheet -- there is no venue-native "balances" list
    to translate. This maps marginSummary.accountValue / withdrawable onto
    a single synthetic USDC Balance, the standard interpretation for a
    USDC-margined perpetuals account. Documented as an explicit
    translation choice, not a directly-observed venue shape."""
    margin = clearinghouse_state_body.get("marginSummary", {})
    total = _decimal(margin.get("accountValue"), "marginSummary.accountValue")
    available = _decimal(clearinghouse_state_body.get("withdrawable"), "withdrawable")
    reserved = total - available
    return (Balance(asset=Symbol("USDC"), total=total, available=available, reserved=reserved),)


def parse_open_orders(frontend_open_orders_body: list, resolve: Resolver) -> Tuple[Order, ...]:
    """Returns only engine-owned orders (INV-3): each entry's cloid must
    resolve to an engine client_order_id via `resolve`, and the returned
    Order carries that engine id (INV-1) -- never the venue token.
    Unresolvable entries (foreign, no cloid) are excluded (INV-4). Uses
    frontendOpenOrders (not plain openOrders) since it additionally
    carries origSz/reduceOnly, needed to populate filled_quantity and
    reduce_only correctly."""
    orders = []
    for entry in frontend_open_orders_body:
        cloid = entry.get("cloid")
        if not cloid:
            continue
        engine_id = resolve(cloid)
        if engine_id is None:
            continue
        coin = entry.get("coin")
        side = _SIDE_MAP.get(entry.get("side"))
        if not coin or side is None:
            continue
        sz = _decimal(entry.get("sz"), "order.sz")
        orig_sz = _decimal(entry.get("origSz"), "order.origSz") if entry.get("origSz") is not None else sz
        filled = orig_sz - sz
        timestamp_iso = _iso(entry.get("timestamp"))
        orders.append(
            Order(
                client_order_id=engine_id,
                exchange_order_id=str(entry.get("oid")) if entry.get("oid") is not None else None,
                symbol=Symbol(coin),
                side=side,
                order_type=_ORDER_TYPE,
                quantity=orig_sz,
                filled_quantity=filled if filled >= 0 else Decimal("0"),
                limit_price=_optional_decimal(entry.get("limitPx"), "order.limitPx"),
                status=OrderStatus.PARTIALLY_FILLED if filled > 0 else OrderStatus.ACKNOWLEDGED,
                time_in_force=_TIME_IN_FORCE_DEFAULT,
                reduce_only=bool(entry.get("reduceOnly", False)),
                created_at_utc=timestamp_iso,
                updated_at_utc=timestamp_iso,
            )
        )
    return tuple(orders)


def parse_user_fills(user_fills_body: list, resolve: Resolver) -> Tuple[Fill, ...]:
    """Returns only engine-attributable fills, labeled with the ENGINE id
    (INV-1) via `resolve`; unresolvable entries are excluded (INV-3/4).
    Note: whether Hyperliquid echoes cloid on userFills at all is
    unconfirmed (the official SDK's Fill type has no cloid field), so
    this may under-report -- the deliberately safe direction. Fill
    attribution via oid remains available to orchestration through
    OrderSnapshot.exchange_order_id."""
    fills = []
    for entry in user_fills_body:
        cloid = entry.get("cloid")
        if not cloid:
            continue
        engine_id = resolve(cloid)
        if engine_id is None:
            continue
        coin = entry.get("coin")
        side = _SIDE_MAP.get(entry.get("side"))
        if not coin or side is None:
            continue
        oid = entry.get("oid")
        if oid is None:
            # oid is documented as always-present on a fill; its absence
            # indicates a genuine schema violation worth surfacing loudly
            # rather than silently fabricating an id (same discipline as
            # the cloid handling above).
            raise ExchangeAdapterError(f"Hyperliquid userFills entry is missing oid: {entry!r}")
        fills.append(
            Fill(
                fill_id=str(entry.get("tid")),
                client_order_id=engine_id,
                exchange_order_id=str(oid),
                symbol=Symbol(coin),
                side=side,
                price=_decimal(entry.get("px"), "fill.px"),
                quantity=_decimal(entry.get("sz"), "fill.sz"),
                fee=_decimal(entry.get("fee"), "fill.fee"),
                timestamp_utc=_iso(entry.get("time")),
            )
        )
    return tuple(fills)


def parse_order_status(
    order_status_body: dict,
    resolve: Resolver,
    assume_client_order_id: Optional[str] = None,
) -> Optional[Order]:
    """Returns None for {"status": "unknownOid"}. Mapping that absence to
    OrderUnknownError (via hyperliquid_adapter.errors.map_unknown_oid) is
    the caller's responsibility -- this stays a pure translator.

    Attribution (INV-1/INV-4): the returned Order's client_order_id is the
    ENGINE id, obtained either from `assume_client_order_id` -- used when
    the caller queried the venue BY this order's own token, so identity is
    guaranteed by the query itself and does not depend on the venue
    echoing cloid back (the find_order path, INV-19) -- or by resolving
    the echoed cloid via `resolve`. If neither yields an engine id, this
    raises rather than fabricating or mislabeling: the order exists at the
    venue but cannot be attributed to this engine."""
    if order_status_body.get("status") != "order":
        return None
    wrapper = order_status_body.get("order", {})
    venue_status = wrapper.get("status")
    order_obj = wrapper.get("order", {})
    coin = order_obj.get("coin")
    side = _SIDE_MAP.get(order_obj.get("side"))
    oid = order_obj.get("oid")
    if not coin or side is None or oid is None:
        raise ExchangeAdapterError(f"Hyperliquid orderStatus response is missing required fields: {order_status_body!r}")

    if assume_client_order_id is not None:
        engine_id = assume_client_order_id
    else:
        cloid = order_obj.get("cloid")
        engine_id = resolve(cloid) if cloid else None
    if engine_id is None:
        raise ExchangeAdapterError(
            f"Hyperliquid order oid={oid} exists but cannot be attributed to an "
            "engine client_order_id -- refusing to mislabel it (INV-4)"
        )

    sz = _decimal(order_obj.get("sz"), "order.sz")
    orig_sz = _decimal(order_obj.get("origSz"), "order.origSz") if order_obj.get("origSz") is not None else sz
    filled = orig_sz - sz
    timestamp_source = order_obj.get("timestamp") if order_obj.get("timestamp") is not None else wrapper.get("statusTimestamp")
    timestamp_iso = _iso(timestamp_source)
    return Order(
        client_order_id=engine_id,
        exchange_order_id=str(oid),
        symbol=Symbol(coin),
        side=side,
        order_type=_ORDER_TYPE,
        quantity=orig_sz,
        filled_quantity=filled if filled >= 0 else Decimal("0"),
        limit_price=_optional_decimal(order_obj.get("limitPx"), "order.limitPx"),
        status=_ORDER_STATUS_MAP.get(venue_status, OrderStatus.UNKNOWN),
        time_in_force=_TIME_IN_FORCE_DEFAULT,
        reduce_only=bool(order_obj.get("reduceOnly", False)),
        created_at_utc=timestamp_iso,
        updated_at_utc=timestamp_iso,
    )


def parse_funding_rate(meta_and_asset_ctxs_body: list, symbol: Symbol, checked_at_utc: str) -> FundingRate:
    """meta_and_asset_ctxs_body is [metadata, asset_contexts], parallel-
    indexed by metadata["universe"][i]["name"] <-> asset_contexts[i].
    next_funding_time_utc is computed, not read from the response:
    Hyperliquid's funding interval is documented as a fixed hourly
    settlement at the top of each UTC hour, not a per-asset value the API
    returns."""
    if not isinstance(meta_and_asset_ctxs_body, list) or len(meta_and_asset_ctxs_body) != 2:
        raise ExchangeAdapterError("Hyperliquid metaAndAssetCtxs response has unexpected shape")
    metadata, asset_ctxs = meta_and_asset_ctxs_body
    universe = metadata.get("universe", [])
    index = next((i for i, a in enumerate(universe) if a.get("name") == symbol.value), None)
    if index is None or index >= len(asset_ctxs):
        raise ExchangeAdapterError(f"no funding rate available for {symbol.value}")
    ctx = asset_ctxs[index]
    now = datetime.now(timezone.utc)
    next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return FundingRate(
        symbol=symbol,
        rate=_decimal(ctx.get("funding"), "assetCtx.funding"),
        next_funding_time_utc=next_hour.isoformat(),
        timestamp_utc=checked_at_utc,
    )
