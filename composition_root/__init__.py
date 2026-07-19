"""Composition Root for the Turtle Execution Engine.

Wires the frozen modules (config(1) .. risk_manager(9)) and the frozen
Hyperliquid concrete adapter (hyperliquid_adapter, Module 10) into one
Engine. Responsible for exactly four things:

    1. Configuration validation  -- rejects an unwireable EngineConfig
       with a clear composition_root.errors exception before
       constructing anything.
    2. Dependency construction   -- builds exactly one instance of every
       component, in dependency order.
    3. Dependency injection      -- shares the single EventStore across
       every component that needs one; derives adapter network selection
       from config so it cannot mismatch.
    4. Lifecycle management      -- Engine.start()/stop() only: a
       one-time connect handshake and a clean shutdown.

Deliberately NOT in scope (see docs/ROADMAP.md's "Live orchestration /
engine entrypoint" -- an acknowledged, unbuilt future gap, not something
this package fills): no trading loop, no polling, no strategy/signal
logic, no order sizing, no scheduling. This module builds the machine; it
does not run it.

No frozen module (1-10) is modified by this package. Every dependency
below is imported through the target module's own __all__, except
HyperliquidWalletSigner and the mainnet/testnet base-URL constants (see
composition_root/wiring.py's module docstring for why those two specific
names are imported one level below hyperliquid_adapter's package __init__).

Public API:
    build_engine(config, deployment, risk_limits, event_store_path, ...)
    Engine                    -- the wired component graph + start()/stop()
    DeploymentSettings        -- account_address + engine_version (not
                                 carried by config.EngineConfig)
    load_deployment_settings  -- reads DeploymentSettings from the
                                 environment
    CompositionRootError      -- base of this package's closed error
                                 hierarchy, and its subclasses
"""

from .deployment import DeploymentSettings, load_deployment_settings
from .engine import Engine
from .errors import (
    CompositionRootError,
    CompositionRootTypeError,
    MissingDeploymentSettingError,
    UnsupportedEnvironmentError,
    UnsupportedExchangeError,
)
from .wiring import build_engine

__all__ = [
    "build_engine",
    "Engine",
    "DeploymentSettings",
    "load_deployment_settings",
    "CompositionRootError",
    "CompositionRootTypeError",
    "UnsupportedExchangeError",
    "UnsupportedEnvironmentError",
    "MissingDeploymentSettingError",
]
