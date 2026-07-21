"""Builds a composition_root.Engine from AppSettings + environment.

Thin glue only: it validates/loads the engine TOML via the frozen
config.load_config, derives DeploymentSettings and RiskManagerLimits, and
delegates entirely to composition_root.build_engine. No engine behavior
lives here -- this module exists so the app layer has a single, testable
"settings -> Engine" entry point.
"""

from pathlib import Path
from typing import Mapping, Optional, Tuple

import os

from config import RiskProfileParams, load_config
from exchange_adapter import Symbol
from hyperliquid_adapter.transport import MAINNET_BASE_URL, TESTNET_BASE_URL
from risk_manager import RiskManagerLimits

from composition_root import Engine, build_engine, load_deployment_settings
from trading_system.execution import QuantizationRules

from .settings import AppSettings
from .venue_rules import fetch_hyperliquid_rules


def _risk_limits(settings: AppSettings) -> RiskManagerLimits:
    return RiskManagerLimits(
        max_leverage=settings.risk_max_leverage,
        min_liquidation_buffer_pct=settings.risk_min_liquidation_buffer_pct,
        max_funding_rate_abs=settings.risk_max_funding_rate_abs,
        max_correlated_positions=settings.risk_max_correlated_positions,
        max_stale_data_seconds=settings.risk_max_stale_data_seconds,
    )


def build_engine_from_settings(
    settings: AppSettings, env: Optional[Mapping[str, str]] = None
) -> Tuple[Engine, Tuple[Symbol, ...], RiskProfileParams, Optional[QuantizationRules]]:
    """Returns (engine, universe, active_risk_profile, quantization_rules).
    Universe and the active RiskProfileParams (from the loaded EngineConfig)
    are surfaced here because the cycle worker needs both and it is cheaper
    to read the config once at build time than repeatedly.

    quantization_rules (C2): for a LIVE engine, per-asset szDecimals rules
    fetched fail-fast from the venue's meta endpoint -- a live engine must
    never trade without them. None for paper mode (MockExchangeAdapter has
    no quantization constraints; None preserves prior behavior exactly)."""
    e = os.environ if env is None else env
    config = load_config(settings.engine_config_path, env=e)
    deployment = load_deployment_settings(e)

    # Ensure the event-store parent directory exists (EventStore also does
    # this, but creating it here surfaces a bad path at build time).
    store_path = Path(settings.event_store_path)
    store_path.parent.mkdir(parents=True, exist_ok=True)

    engine = build_engine(
        config=config,
        deployment=deployment,
        risk_limits=_risk_limits(settings),
        event_store_path=store_path,
        env=e,
    )
    universe = tuple(Symbol(s) for s in config.universe.symbols)

    quantization_rules: Optional[QuantizationRules] = None
    if config.environment == "live":
        base_url = MAINNET_BASE_URL if config.exchange.network == "mainnet" else TESTNET_BASE_URL
        try:
            quantization_rules = fetch_hyperliquid_rules(base_url)
        except Exception:
            # Fail fast -- but never leak the event-store lock on the way out.
            engine.event_store.close()
            raise
    return engine, universe, config.risk.active_profile_params, quantization_rules
