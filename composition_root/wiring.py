"""Dependency construction and injection for the Turtle Execution Engine.

build_engine() is the ONLY place that constructs the frozen modules'
public objects and wires them together into one Engine. It performs
configuration validation and dependency injection ONLY -- it never runs a
loop, never polls, never schedules, and never generates a trading
decision. See docs/ROADMAP.md's "Integration rules for any future
module": additive-only, depend only on already-frozen lower-numbered
modules via their __all__, no frozen-module modification, no dependency
cycles.

Construction order follows docs/DEPENDENCY_GRAPH.md's DAG exactly:

    config(1) + secrets_boundary(2) + event_store(3)
        -> execution_state_machine(4)
        -> exchange_adapter(5) concrete adapter [hyperliquid_adapter(10)
           for 'live', MockExchangeAdapter for 'paper']
        -> order_manager(6), position_manager(7), portfolio_manager(8)
        -> risk_manager(9)

Exactly one EventStore is opened per build_engine() call and passed BY
REFERENCE into every component that needs one (execution_state_machine,
the adapter's own durable order-id mapping when live, order_manager,
position_manager, portfolio_manager) -- never re-opened. A second
EventStore(path) against the same file would fail loudly with
EventStoreLockError (exclusive, non-blocking OS lock), which is itself a
structural, not conventional, guarantee against two engines silently
sharing -- or worse, silently NOT sharing -- state.

Note on import surface: HyperliquidWalletSigner and the mainnet/testnet
base-URL constants are not re-exported in hyperliquid_adapter/__init__.py's
__all__, but HyperliquidAdapter's own constructor docstring documents
wallet_signer as caller-supplied and deliberately NOT imported by
adapter.py itself ("Duck-typed and NOT imported here, so adapter.py stays
eth-account-free on the read-only path") -- there is no other way for any
caller to ever construct a real venue signer. This module therefore
imports those two names directly from their submodules
(hyperliquid_adapter.signing, hyperliquid_adapter.transport), which is a
plain Python import of non-underscore-prefixed names, not a modification
of hyperliquid_adapter.
"""

from pathlib import Path
from typing import FrozenSet, Mapping, Optional, Union

from config import EngineConfig
from event_store import EventStore
from exchange_adapter import ExchangeAdapter, MockExchangeAdapter
from execution_state_machine import ExecutionStateMachine
from hyperliquid_adapter import HyperliquidAdapter, TransportFn
from hyperliquid_adapter.signing import HyperliquidWalletSigner
from hyperliquid_adapter.transport import MAINNET_BASE_URL, TESTNET_BASE_URL
from order_manager import OrderManager
from portfolio_manager import PortfolioManager
from position_manager import PositionManager
from risk_manager import RiskManager, RiskManagerLimits
from secrets_boundary import SigningBoundary

from .deployment import DeploymentSettings
from .engine import Engine
from .errors import (
    CompositionRootTypeError,
    MissingDeploymentSettingError,
    UnsupportedEnvironmentError,
    UnsupportedExchangeError,
)

# Declared independently of config.schema's private SUPPORTED_* sets
# (which are not part of config.__all__): mirrors the same
# independently-declare-the-same-allowed-names pattern config/schema.py
# itself uses for SUPPORTED_RISK_PROFILE_NAMES, so this composition root
# never reaches past a frozen module's public API surface.
_SUPPORTED_ENVIRONMENTS: FrozenSet[str] = frozenset({"paper", "live"})
_SUPPORTED_EXCHANGES: FrozenSet[str] = frozenset({"hyperliquid"})

_ACCOUNT_ADDRESS_HINT = "TURTLE_DEPLOYMENT_ACCOUNT_ADDRESS"


def build_engine(
    config: EngineConfig,
    deployment: DeploymentSettings,
    risk_limits: RiskManagerLimits,
    event_store_path: Union[str, Path],
    *,
    env: Optional[Mapping[str, str]] = None,
    transport: Optional[TransportFn] = None,
) -> Engine:
    """Validate configuration, construct every component, and inject
    shared dependencies. Raises a CompositionRootError subclass (never a
    wired module's own exception) if configuration is insufficient to
    wire safely -- no component is constructed until all checks pass.

    config: an already-validated EngineConfig (config.load_config()'s
        loader already enforces environment/exchange/network against its
        own SUPPORTED_* sets; the checks below are this composition
        root's OWN defense, since EngineConfig can also be constructed
        directly, e.g. in tests, bypassing the loader).
    deployment: venue account address + engine version (see deployment.py
        for why these are not in EngineConfig).
    risk_limits: supplied explicitly by the caller -- RiskManagerLimits
        covers dimensions config.RiskConfig was never scoped to include
        (see risk_manager/models.py), so this composition root does not
        attempt to derive it from config.
    event_store_path: filesystem path for the single shared EventStore.
    env: optional environment-variable mapping override, threaded through
        to SigningBoundary/HyperliquidWalletSigner (testing only; None
        uses the real process environment).
    transport: optional TransportFn override for the live adapter
        (testing only; None uses hyperliquid_adapter's default transport).
    """
    if not isinstance(config, EngineConfig):
        raise CompositionRootTypeError(f"config must be an EngineConfig, got {type(config).__name__}")
    if not isinstance(deployment, DeploymentSettings):
        raise CompositionRootTypeError(f"deployment must be a DeploymentSettings, got {type(deployment).__name__}")
    if not isinstance(risk_limits, RiskManagerLimits):
        raise CompositionRootTypeError(f"risk_limits must be a RiskManagerLimits, got {type(risk_limits).__name__}")

    if config.environment not in _SUPPORTED_ENVIRONMENTS:
        raise UnsupportedEnvironmentError(
            f"composition root does not know how to wire environment={config.environment!r} "
            f"(supported: {sorted(_SUPPORTED_ENVIRONMENTS)})"
        )
    if config.exchange.name not in _SUPPORTED_EXCHANGES:
        raise UnsupportedExchangeError(
            f"composition root has no concrete adapter for exchange={config.exchange.name!r} "
            f"(supported: {sorted(_SUPPORTED_EXCHANGES)})"
        )

    is_live = config.environment == "live"
    if is_live and not deployment.account_address:
        raise MissingDeploymentSettingError(
            "environment='live' requires deployment.account_address (the venue "
            f"wallet address) -- set {_ACCOUNT_ADDRESS_HINT} or pass it explicitly "
            "via DeploymentSettings; refusing to construct a live adapter with no "
            "venue account to trade"
        )

    # -- Layer 0: foundational, zero internal dependencies --
    # EventStore holds an exclusive, non-blocking OS lock on
    # event_store_path from the moment it opens (event_store/store.py). If
    # any later construction step below raises, that lock must not leak --
    # otherwise a corrected retry could never open this same path again.
    # Everything from here on is wrapped so any exception closes the store
    # before propagating.
    event_store = EventStore(Path(event_store_path))
    try:
        signing_boundary = SigningBoundary(
            refs=[config.secrets.signing_key_ref],
            engine_version=deployment.engine_version,
            exchange_name=config.exchange.name,
            env=env,
        )

        # -- Layer 1: depends only on layer 0 --
        execution_state_machine = ExecutionStateMachine(store=event_store)
        adapter, wallet_signer = _build_adapter(
            config=config,
            deployment=deployment,
            signing_boundary=signing_boundary,
            event_store=event_store,
            is_live=is_live,
            env=env,
            transport=transport,
        )

        # -- Layer 2: depends on layer 0/1 --
        order_manager = OrderManager(adapter, event_store, execution_state_machine)
        position_manager = PositionManager(event_store)
        portfolio_manager = PortfolioManager(event_store)

        # -- Layer 3: top consumer, pure (no store/adapter) --
        risk_manager = RiskManager(risk_limits)
    except BaseException:
        event_store.close()
        raise

    return Engine(
        event_store=event_store,
        signing_boundary=signing_boundary,
        execution_state_machine=execution_state_machine,
        adapter=adapter,
        order_manager=order_manager,
        position_manager=position_manager,
        portfolio_manager=portfolio_manager,
        risk_manager=risk_manager,
        wallet_signer=wallet_signer,
    )


def _build_adapter(
    *,
    config: EngineConfig,
    deployment: DeploymentSettings,
    signing_boundary: SigningBoundary,
    event_store: EventStore,
    is_live: bool,
    env: Optional[Mapping[str, str]],
    transport: Optional[TransportFn],
) -> "tuple[ExchangeAdapter, Optional[HyperliquidWalletSigner]]":
    """paper -> MockExchangeAdapter (no network, no event_store, no wallet
    signer -- it never transmits anywhere and has no durable order-id
    mapping to maintain). live -> HyperliquidAdapter bound to the SAME
    event_store (INV-16) and, when a wallet_key_ref is configured, a
    HyperliquidWalletSigner whose is_mainnet is DERIVED from
    config.exchange.network -- so a base_url/signer network mismatch is
    structurally impossible here, not just checked (HyperliquidAdapter's
    own constructor additionally re-verifies this; see adapter.py's
    base_url/wallet_signer.is_mainnet check)."""
    if not is_live:
        return (
            MockExchangeAdapter(
                signing_boundary=signing_boundary,
                signing_key_ref=config.secrets.signing_key_ref,
            ),
            None,
        )

    is_mainnet = config.exchange.network == "mainnet"
    base_url = MAINNET_BASE_URL if is_mainnet else TESTNET_BASE_URL

    wallet_signer: Optional[HyperliquidWalletSigner] = None
    if config.secrets.wallet_key_ref:
        wallet_signer = HyperliquidWalletSigner(
            wallet_key_ref=config.secrets.wallet_key_ref,
            is_mainnet=is_mainnet,
            env=env,
        )

    kwargs = dict(
        signing_boundary=signing_boundary,
        signing_key_ref=config.secrets.signing_key_ref,
        account_address=deployment.account_address,
        exchange_name=config.exchange.name,
        base_url=base_url,
        event_store=event_store,
        wallet_signer=wallet_signer,
    )
    if transport is not None:
        kwargs["transport"] = transport

    return HyperliquidAdapter(**kwargs), wallet_signer
