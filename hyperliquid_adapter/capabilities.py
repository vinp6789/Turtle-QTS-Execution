"""Default capability declaration for the Hyperliquid adapter.

Per ADR-22, ExchangeCapabilities describes THIS ADAPTER's effective
contract with callers -- what a caller may rely on succeeding when sent
through this adapter -- not the venue's feature list in the abstract. It
is the intersection of venue support, what this implementation actually
does, and deployment policy. That reading follows from the frozen
contract: `capabilities` is an injectable constructor parameter with a
default (exchange_adapter/adapter.py), and an adapter polices itself
against its own declaration (exchange_adapter/mock_adapter.py).

Callers branch on these fields, never on exchange_name. Risk Manager
vetoes a trade whose requested feature is not declared here
(risk_manager/manager.py::_capability_violation -> reason code
EXCHANGE_CAPABILITY_UNSUPPORTED), so a wrong value here changes trading
outcomes -- these are not cosmetic.

Values are justified against Hyperliquid's documented order schema:

    "t": {"limit":   {"tif": "Alo" | "Ioc" | "Gtc"}}
       | {"trigger": {"isMarket": bool, "triggerPx": str, "tpsl": "tp"|"sl"}}
    "r": bool   (reduceOnly)
"""

from exchange_adapter import ExchangeCapabilities

DEFAULT_HYPERLIQUID_CAPABILITIES = ExchangeCapabilities(
    # "r" (reduceOnly) is a first-class field on every Hyperliquid order.
    supports_reduce_only=True,
    # tif "Alo" (Add Liquidity Only) is Hyperliquid's post-only mode.
    supports_post_only=True,
    # tif "Ioc".
    supports_ioc=True,
    # The tif enum is exactly Alo|Ioc|Gtc -- Hyperliquid has no FOK. False
    # produces a clean upfront veto instead of the adapter silently
    # substituting IOC, which would turn an all-or-nothing intent into a
    # partial fill (a capital-relevant semantic change).
    supports_fok=False,
    # Hyperliquid has no native market order; the documented approach is an
    # aggressive IOC limit. Per ADR-22 this adapter declines that emulation:
    # the slippage bound would be an adapter-internal constant invisible to
    # Risk Manager, which approves against TradeRequest.entry_price and
    # derives notional, margin, and the liquidation buffer from it -- so a
    # fill outside that price would silently invalidate the checks that
    # authorized the trade. Callers wanting market-like execution send
    # LIMIT + IOC with their own aggressive limit_price, keeping the
    # worst-case fill bounded by a price the risk layer can see.
    supports_market_orders=False,
    # tif "Gtc" limit orders are the primary order type.
    supports_limit_orders=True,
    # The venue supports trigger orders, but they are unexpressible through
    # the frozen interface: OrderType is only MARKET|LIMIT and OrderRequest
    # carries no trigger price. Unreachable through this contract, so not
    # supported by this adapter.
    supports_trigger_orders=False,
    # The venue reports partial fills, but "notifications" means push, which
    # requires the websocket. This build is REST-only; revisit if WS lands.
    supports_partial_fill_notifications=False,
    # Perpetuals charge funding and the public info endpoint exposes it.
    supports_funding_rate=True,
    # Cross margin is the venue default and isolated margin is also
    # supported; this adapter constrains neither. Descriptive only --
    # OrderRequest carries no margin-mode field, so neither is reachable
    # through the frozen interface.
    supports_cross_margin=True,
    supports_isolated_margin=True,
)
