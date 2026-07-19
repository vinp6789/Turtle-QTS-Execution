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
from risk_manager import RiskManagerLimits

from composition_root import Engine, build_engine, load_deployment_settings

from .settings import AppSettings


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
) -> Tuple[Engine, Tuple[Symbol, ...], RiskProfileParams]:
    """Returns (engine, universe, active_risk_profile). Universe and the
    active RiskProfileParams (from the loaded EngineConfig) are surfaced
    here because the cycle worker needs both and it is cheaper to read the
    config once at build time than repeatedly."""
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
    return engine, universe, config.risk.active_profile_params
